import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, sessionApi } from "../src/lib/api";

test("expired cached token gets one fresh-token retry for reads", async (t) => {
  const tokens: unknown[] = [];
  const headers: string[] = [];
  t.mock.method(
    globalThis,
    "fetch",
    async (_url: unknown, options: RequestInit) => {
      headers.push((options.headers as Record<string, string>).Authorization);
      return Response.json(headers.length === 1 ? {} : { id: "saved-story" }, {
        status: headers.length === 1 ? 401 : 200,
      });
    },
  );
  const value = await sessionApi("stories/id", async (options) => {
    tokens.push(options);
    return options?.skipCache ? "fresh" : "cached";
  });
  assert.deepEqual(value, { id: "saved-story" });
  assert.deepEqual(tokens, [undefined, { skipCache: true }]);
  assert.deepEqual(headers, ["Bearer cached", "Bearer fresh"]);
});

test("authentication failures do not replay generation or retry reads forever", async (t) => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls += 1;
    return Response.json({}, { status: 401 });
  });
  await assert.rejects(
    sessionApi("stories", async () => "token", { method: "POST" }),
    ApiError,
  );
  assert.equal(calls, 1);
  await assert.rejects(
    sessionApi("stories", async () => "token"),
    ApiError,
  );
  assert.equal(calls, 3);
});
