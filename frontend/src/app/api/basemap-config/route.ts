/**
 * Serves CARTO_API_KEY to the browser map. Read from the frontend container's
 * environment at request time (like BACKEND_URL) so the prebuilt image needs
 * no rebuild. Consumed by useBasemapConfig().
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
