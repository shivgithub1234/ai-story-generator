import { forward } from "@/lib/proxy";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 360;
type Context = { params: Promise<{ path: string[] }> };
async function handler(request: Request, context: Context) {
  return forward(request, (await context.params).path);
}
export { handler as GET, handler as POST, handler as PATCH };
