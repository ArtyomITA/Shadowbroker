/**
 * Runtime basemap configuration for the browser map.
 *
 * CARTO_API_KEY is a plain server-side env var on the frontend container
 * (see docker-compose.yml). Like BACKEND_URL it is read at request time, so
 * operators running the prebuilt GHCR image can set it in .env without a
 * rebuild. A NEXT_PUBLIC_ var would be baked in at image build time and
 * therefore always empty for them.
 *
 * The key is not a secret in the usual sense — the browser sends it to
 * CARTO on every tile request — but it is only returned to same-origin
 * callers of this Next.js server, never proxied to the backend.
 */

import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const NO_STORE_HEADERS = {
  'Cache-Control': 'no-store, max-age=0',
  Pragma: 'no-cache',
};

export type BasemapConfigResponse = {
  carto: {
    configured: boolean;
    key: string;
  };
};

export function readCartoApiKey(): string {
  return String(process.env.CARTO_API_KEY || '').trim();
}

export async function GET() {
  const key = readCartoApiKey();
  const body: BasemapConfigResponse = {
    carto: { configured: key.length > 0, key },
  };
  return NextResponse.json(body, { headers: NO_STORE_HEADERS });
}
