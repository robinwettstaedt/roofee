import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { error: "Body must be JSON." },
      { status: 400 },
    );
  }

  try {
    const upstream = await fetch(`${BACKEND_URL}/api/location/tile-glb`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });

    if (!upstream.ok) {
      const text = await upstream.text();
      return new Response(text, {
        status: upstream.status,
        headers: {
          "content-type":
            upstream.headers.get("content-type") ?? "application/json",
        },
      });
    }

    const arrayBuffer = await upstream.arrayBuffer();
    const headers: Record<string, string> = {
      "content-type":
        upstream.headers.get("content-type") ?? "model/gltf-binary",
    };
    const meta = upstream.headers.get("Roofee-Metadata");
    if (meta) headers["Roofee-Metadata"] = meta;

    return new Response(arrayBuffer, { status: 200, headers });
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
