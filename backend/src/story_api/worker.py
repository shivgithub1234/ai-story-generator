"""Run separately from HTTP: python -m story_api.worker. Ctrl+C stops this worker."""

import asyncio
import logging
import signal

from starlette.concurrency import run_in_threadpool

from story_api.database import get_engine
from story_api.jobs import JobQueue
from story_api.preflight import validate_runtime
from story_api.providers import GenerationError, create_provider
from story_api.storage import RunExpired, StoryStore
from story_api.workflow import generate_story

log = logging.getLogger("story_worker")


async def execute(queue, job, provider_factory=create_provider):
    provider = None
    try:
        provider = provider_factory()

        async def progress(stage):
            await run_in_threadpool(queue.progress, job, stage)

        async with asyncio.timeout(330):
            result = await generate_story(job.request, provider, progress=progress)
        await run_in_threadpool(queue.progress, job, "saving")
        await run_in_threadpool(
            StoryStore(queue.engine, job.owner_id).finish,
            job.run_id,
            result,
            lease_token=job.token,
        )
        log.info("run=%s attempt=%s completed", job.run_id, job.attempt)
    except GenerationError as exc:
        await run_in_threadpool(queue.fail, job, exc.code)
        log.warning("run=%s code=%s", job.run_id, exc.code)
    except TimeoutError:
        await run_in_threadpool(queue.fail, job, "workflow_timeout")
    except RunExpired:
        log.warning("run=%s lease lost; output discarded", job.run_id)
    except Exception:
        # No raw provider exception, prompt, credentials, or database URL in logs.
        await run_in_threadpool(queue.fail, job, "generation_failed")
        log.error("run=%s failed", job.run_id)
    finally:
        if provider is not None:
            await provider.close()


async def process_one(queue, provider_factory=create_provider):
    job = await run_in_threadpool(queue.claim)
    if job is None:
        return False

    async def renew():
        while True:
            await asyncio.sleep(15)
            await run_in_threadpool(queue.heartbeat, job)

    task = asyncio.create_task(execute(queue, job, provider_factory))
    heartbeat = asyncio.create_task(renew())
    try:
        done, _ = await asyncio.wait({task, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
        for completed in done:
            completed.result()
    finally:
        # On shutdown or lost heartbeat, stop model work. The lease permits recovery.
        task.cancel()
        heartbeat.cancel()
        await asyncio.gather(task, heartbeat, return_exceptions=True)
    return True


async def serve():
    validate_runtime()
    # Containers send SIGTERM. Cancel cleanly and let the saved lease recover the job.
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    try:
        loop.add_signal_handler(signal.SIGTERM, task.cancel)
    except NotImplementedError:
        pass  # Windows' event loop uses Ctrl+C instead.
    queue = JobQueue(get_engine())
    log.info("Worker started; waiting for queued stories")
    while True:
        try:
            if not await process_one(queue):
                await asyncio.sleep(2)
        except Exception:
            log.error("Queue unavailable or lease lost; retrying in five seconds")
            await asyncio.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    try:
        asyncio.run(serve())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
