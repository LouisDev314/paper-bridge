import type { NextRequest } from 'next/server';
import crypto from 'crypto';

import { getServerEnv } from '@/lib/env';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]);

// Headers that commonly trigger browser decoding failures when proxying through Vercel
const STRIP_RESPONSE_HEADERS = new Set(['content-encoding', 'content-length', 'transfer-encoding']);

type ProxyContext = {
  params: Promise<{ path?: string[] }> | { path?: string[] };
};

function stripTrailingSlashes(value: string): string {
  return value.replace(/\/+$/, '');
}

function makeTargetUrl(path: string[], search: string): URL {
  const { NEXT_PUBLIC_API_BASE_URL } = getServerEnv();
  const base = stripTrailingSlashes(NEXT_PUBLIC_API_BASE_URL);

  // Keep original behavior: encode each segment safely
  const target = new URL(`${base}/${path.map((segment) => encodeURIComponent(segment)).join('/')}`);
  target.search = search;
  return target;
}

function copyRequestHeaders(request: NextRequest): Headers {
  const headers = new Headers(request.headers);

  // Don't forward host/content-length; let fetch compute it
  headers.delete('host');
  headers.delete('content-length');
  headers.delete('connection');

  // Prevent upstream compression to avoid Vercel/body decoding mismatches
  headers.set('accept-encoding', 'identity');

  if (!headers.has('x-request-id')) {
    headers.set('x-request-id', crypto.randomUUID());
  }

  return headers;
}

function copyResponseHeaders(upstream: Response): Headers {
  const headers = new Headers();

  upstream.headers.forEach((value, key) => {
    const lower = key.toLowerCase();

    // Remove hop-by-hop headers
    if (HOP_BY_HOP_HEADERS.has(lower)) return;

    // Remove headers that can cause ERR_CONTENT_DECODING_FAILED
    if (STRIP_RESPONSE_HEADERS.has(lower)) return;

    headers.set(key, value);
  });

  return headers;
}

async function proxyRequest(request: NextRequest, context: ProxyContext): Promise<Response> {
  const params = await context.params;
  const path = params.path ?? [];

  if (path.length === 0) {
    return Response.json(
      {
        error: {
          code: 'INVALID_PROXY_PATH',
          message: 'Missing backend path for proxy request.',
        },
      },
      { status: 400 },
    );
  }

  const targetUrl = makeTargetUrl(path, request.nextUrl.search);
  const requestHeaders = copyRequestHeaders(request);

  const init: RequestInit & { duplex?: 'half' } = {
    method: request.method,
    headers: requestHeaders,
    redirect: 'manual',
  };

  const method = request.method.toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') {
    // Stream body through (supports multipart uploads)
    init.body = request.body;
    init.duplex = 'half';
  }

  try {
    const upstream = await fetch(targetUrl, init);

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: copyResponseHeaders(upstream),
    });
  } catch {
    return Response.json(
      {
        error: {
          code: 'UPSTREAM_UNAVAILABLE',
          message: 'Unable to reach backend API from proxy route.',
        },
      },
      { status: 502 },
    );
  }
}

const handler = (request: NextRequest, context: ProxyContext) => proxyRequest(request, context);

export {
  handler as GET,
  handler as POST,
  handler as PUT,
  handler as PATCH,
  handler as DELETE,
  handler as OPTIONS,
  handler as HEAD,
};
