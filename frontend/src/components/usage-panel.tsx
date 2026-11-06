"use client";

import { useEffect, useState } from "react";

type Usage = {
  limit: number;
  used: number;
  remaining: number;
  active_jobs: number;
  active_limit: number;
  next_credit_at: string | null;
};

type Props = {
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
  refreshKey: string;
};

export default function UsagePanel({ request, refreshKey }: Props) {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await request<Usage>("stories/usage", {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setUsage(value);
          setError(false);
        }
      } catch {
        if (!controller.signal.aborted) setError(true);
      }
      if (!controller.signal.aborted) timer = setTimeout(load, 15000);
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [request, refreshKey]);

  return (
    <aside className="usage-panel" aria-label="Your generation allowance">
      {error ? (
        <p role="status">
          Allowance could not be refreshed. Limits are still checked when you
          submit.
        </p>
      ) : usage ? (
        <>
          <p>
            <strong>
              {usage.remaining} of {usage.limit} requests remaining
            </strong>{" "}
            in the rolling 24-hour window
            <span>
              {" "}
              · {usage.active_jobs}/{usage.active_limit} active jobs
            </span>
          </p>
          {usage.remaining === 0 && usage.next_credit_at ? (
            <p role="status">
              Next request available after{" "}
              {new Date(usage.next_credit_at).toLocaleString()}.
            </p>
          ) : null}
          {usage.active_jobs >= usage.active_limit ? (
            <p role="status">
              Wait for an active job to finish before starting another.
            </p>
          ) : null}
          <p className="fine-print">
            New stories and regenerations count once. Failed requests count;
            automatic retries and revisions do not count again.
          </p>
        </>
      ) : (
        <p role="status">Checking your allowance…</p>
      )}
    </aside>
  );
}
