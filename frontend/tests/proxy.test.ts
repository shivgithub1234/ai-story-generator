import test from "node:test";
import assert from "node:assert/strict";
import { allowedRoute, forward } from "../src/lib/proxy";
import { errorMessage } from "../src/lib/api";

test("proxy only permits supported story operations", () => {
  const id = "12345678-1234-1234-1234-123456789012";
  assert.equal(allowedRoute("stories", "POST"), true);
  assert.equal(allowedRoute("stories/usage", "GET"), true);
  assert.equal(allowedRoute("stories/usage", "POST"), false);
  assert.equal(allowedRoute(`stories/${id}/runs`, "POST"), true);
  for (const path of [
    "https://evil.invalid",
    "../health",
    "stories/../../health",
    "stories/generate",
    "auth/login",
  ])
    assert.equal(allowedRoute(path, "GET"), false);
  assert.equal(allowedRoute(`stories/${id}`, "DELETE"), false);
});
test("missing bearer and cross-origin mutation fail before fetch", async () => {
  assert.equal(
    (
      await forward(new Request("http://localhost:3000/api/backend/stories"), [
        "stories",
      ])
    ).status,
    401,
  );
  assert.equal(
    (
      await forward(
        new Request("http://localhost:3000/api/backend/stories", {
          method: "POST",
          headers: {
            Authorization: "Bearer test",
            Origin: "https://evil.invalid",
          },
        }),
        ["stories"],
      )
    ).status,
    403,
  );
});
test("proxy passes only bearer, safe query and uncached response", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async (input, options) => {
    const url = new URL(String(input));
    assert.equal(url.pathname, "/api/stories");
    assert.equal(url.search, "?limit=12");
    const headers = new Headers(options?.headers);
    assert.equal(headers.get("authorization"), "Bearer test");
    assert.equal(headers.has("cookie"), false);
    assert.equal(options?.cache, "no-store");
    assert.equal(options?.redirect, "error");
    return Response.json([]);
  };
  try {
    const response = await forward(
      new Request(
        "http://localhost:3000/api/backend/stories?limit=12&owner_id=another-user",
        { headers: { Authorization: "Bearer test", Cookie: "private=secret" } },
      ),
      ["stories"],
    );
    assert.equal(response.headers.get("cache-control"), "private, no-store");
    assert.deepEqual(await response.json(), []);
  } finally {
    globalThis.fetch = original;
  }
});
test("conflicts and nested generation errors are actionable", () => {
  assert.match(errorMessage(409, null), /another tab/);
  assert.equal(
    errorMessage(502, { detail: { error: { message: "Model unavailable" } } }),
    "Model unavailable",
  );
});
