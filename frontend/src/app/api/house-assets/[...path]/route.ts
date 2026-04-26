import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ path: string[] }> },
) {
  const { path } = await ctx.params;
  const upstreamUrl = `${BACKEND_URL}/api/house-assets/${path
    .map(encodeURIComponent)
    .join("/")}`;

  try {
    const upstream = await fetch(upstreamUrl, { cache: "no-store" });
    if (!upstream.ok) {
      return NextResponse.json(
        { error: `backend returned ${upstream.status}` },
        { status: upstream.status },
      );
    }
    const arrayBuffer = await upstream.arrayBuffer();
    return new Response(arrayBuffer, {
      status: 200,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ?? "application/octet-stream",
        "cache-control": upstream.headers.get("cache-control") ?? "no-store",
      },
    });
  } catch (err) {
    return NextResponse.json(
      {
        error: "backend unreachable",
        detail: err instanceof Error ? err.message : String(err),
      },
      { status: 503 },
    );
  }
}
