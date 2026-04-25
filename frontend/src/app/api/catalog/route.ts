import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const kind = url.searchParams.get("kind");
  const target = new URL(`${BACKEND_URL}/api/catalog/components`);
  if (kind) target.searchParams.set("kind", kind);

  try {
    const res = await fetch(target.toString(), { cache: "no-store" });
    if (!res.ok) {
      return NextResponse.json(
        { error: `backend returned ${res.status}` },
        { status: res.status },
      );
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      {
        error: "backend unreachable",
        detail: err instanceof Error ? err.message : String(err),
        summary: { component_count: 0 },
        components: [],
      },
      { status: 503 },
    );
  }
}
