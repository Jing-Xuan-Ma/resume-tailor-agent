import { NextRequest, NextResponse } from "next/server";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

async function proxy(req: NextRequest, pathParts: string[] | undefined) {
  const parts = (pathParts || []).filter(Boolean);
  const sub = parts.join("/");
  // Mounted FastAPI app requires the trailing slash on the collection root.
  const targetPath = sub ? `/intern-list/${sub}` : "/intern-list/";
  const target = new URL(`${API_BASE}${targetPath}`);
  target.search = req.nextUrl.search;

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers: {
        accept: req.headers.get("accept") || "*/*",
        "content-type": req.headers.get("content-type") || "",
      },
      body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer(),
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    return new NextResponse(
      `<!doctype html><html><body style="font-family:sans-serif;padding:2rem">
        <h1>Intern-list 后端未启动</h1>
        <p>请先启动 Resume Agent API（默认 <code>127.0.0.1:8000</code>），然后刷新本页。</p>
        <p>目标：<code>${target.toString()}</code></p>
      </body></html>`,
      { status: 502, headers: { "content-type": "text/html; charset=utf-8" } }
    );
  }

  // Follow one trailing-slash redirect from the mounted FastAPI app.
  if (upstream.status >= 300 && upstream.status < 400) {
    const loc = upstream.headers.get("location");
    if (loc) {
      const nextUrl = new URL(loc, target);
      upstream = await fetch(nextUrl, { redirect: "follow", cache: "no-store" });
    }
  }

  const headers = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  headers.set("cache-control", "no-store");
  // Same-origin embed in /jobs — allow framing by this app.
  headers.set("content-security-policy", "frame-ancestors 'self' http://127.0.0.1:3000 http://localhost:3000");

  return new NextResponse(await upstream.arrayBuffer(), {
    status: upstream.status,
    headers,
  });
}

export async function GET(
  req: NextRequest,
  ctx: { params: { path?: string[] } }
) {
  return proxy(req, ctx.params.path);
}

export async function POST(
  req: NextRequest,
  ctx: { params: { path?: string[] } }
) {
  return proxy(req, ctx.params.path);
}
