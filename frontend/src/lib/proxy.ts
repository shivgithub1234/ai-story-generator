const uuid =
  "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
export function allowedRoute(path: string, method: string): boolean {
  if (path === "auth/me") return method === "GET";
  if (path === "stories") return method === "GET" || method === "POST";
  if (new RegExp(`^stories/${uuid}$`).test(path))
    return method === "GET" || method === "PATCH";
  if (new RegExp(`^stories/${uuid}/runs$`).test(path))
    return method === "GET" || method === "POST";
  return false;
}

// Forward only explicit bearer credentials. FastAPI verifies them on every call.
// No cookies, arbitrary hosts, redirects, or cached private responses cross this boundary.
export async function forward(
  request: Request,
  segments: string[],
): Promise<Response> {
  const path = segments.join("/");
  if (!allowedRoute(path, request.method))
    return Response.json({ detail: "Not found." }, { status: 404 });
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ") || authorization.length > 16400)
    return Response.json({ detail: "Sign-in required." }, { status: 401 });
  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin)
    return Response.json({ detail: "Origin not allowed." }, { status: 403 });
  const upstream = new URL(
    process.env.STORY_API_URL || "http://127.0.0.1:8000",
  );
  if (
    !["http:", "https:"].includes(upstream.protocol) ||
    upstream.username ||
    upstream.password
  )
    return Response.json(
      { detail: "Invalid API configuration." },
      { status: 503 },
    );
  upstream.pathname = `/api/${path}`;
  upstream.search = "";
  const query = new URL(request.url).searchParams;
  for (const name of ["limit", "offset"])
    if (query.has(name)) upstream.searchParams.set(name, query.get(name)!);
  try {
    const body = ["POST", "PATCH"].includes(request.method)
      ? await request.text()
      : undefined;
    if (body && new TextEncoder().encode(body).length > 500000)
      return Response.json(
        { detail: "Request is too large." },
        { status: 413 },
      );
    const response = await fetch(upstream, {
      method: request.method,
      body,
      redirect: "error",
      cache: "no-store",
      headers: {
        Authorization: authorization,
        "Content-Type": "application/json",
      },
      signal: AbortSignal.timeout(350000),
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "private, no-store",
        Vary: "Authorization",
      },
    });
  } catch {
    return Response.json(
      {
        detail:
          "The story service is unavailable or took too long. Refresh your library before retrying; a story may have been saved.",
      },
      { status: 503 },
    );
  }
}
