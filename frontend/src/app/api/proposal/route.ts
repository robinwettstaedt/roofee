import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json(
      { error: "Expected multipart/form-data body." },
      { status: 400 },
    );
  }

  try {
    const upstream = await fetch(`${BACKEND_URL}/api/proposal`, {
      method: "POST",
      body: formData,
      cache: "no-store",
    });
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ?? "application/json",
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
