export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public storyId?: string,
  ) {
    super(message);
  }
}

export function errorMessage(status: number, body: unknown): string {
  if (status === 401)
    return "Your session could not be verified. Sign in again. If this continues, check the Clerk session audience setting.";
  if (status === 404)
    return "This story is unavailable or does not belong to your account.";
  if (status === 409)
    return "This story changed in another tab. Reload it before saving. Your text is still here to copy.";
  if (status === 422)
    return "Check your brief: use 10–2,000 characters and a target of 200–3,000 words.";
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  const nested = detail as
    { message?: string; error?: { message?: string } } | undefined;
  return (
    nested?.message ||
    nested?.error?.message ||
    "We couldn’t reach your story service. Try again in a moment."
  );
}

export async function api<T>(
  path: string,
  token: string | null,
  options: RequestInit = {},
): Promise<T> {
  if (!token) throw new ApiError("Please sign in to open your stories.", 401);
  const response = await fetch(`/api/backend/${path}`, {
    ...options,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
      Authorization: `Bearer ${token}`,
    },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      errorMessage(response.status, body),
      response.status,
      body?.detail?.story_id,
    );
  return body as T;
}
