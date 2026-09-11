'use client';

import { useEffect, useState } from 'react';
import { API_BASE } from '@/lib/api';
import type { BasemapConfigResponse } from '@/app/api/basemap-config/route';

export type BasemapConfig = {
  /** CARTO basemap API key, or null when none is configured / not yet loaded. */
  cartoApiKey: string | null;
  /** True once the config request has settled (success or failure). */
  loaded: boolean;
};

const UNCONFIGURED: BasemapConfig = { cartoApiKey: null, loaded: true };

// One request per page load, shared by every map instance.
let configPromise: Promise<BasemapConfig> | null = null;

async function fetchBasemapConfig(): Promise<BasemapConfig> {
  try {
    const res = await fetch(`${API_BASE}/api/basemap-config`, { cache: 'no-store' });
    if (!res.ok) return UNCONFIGURED;
    const body = (await res.json()) as Partial<BasemapConfigResponse>;
    const key = String(body?.carto?.key || '').trim();
    return { cartoApiKey: key || null, loaded: true };
  } catch {
    // Static/desktop exports have no API routes; fall back to unkeyed tiles.
    return UNCONFIGURED;
  }
}

/** Reset the shared request cache (tests only). */
export function __resetBasemapConfigCache(): void {
  configPromise = null;
}

export function useBasemapConfig(): BasemapConfig {
  const [config, setConfig] = useState<BasemapConfig>({ cartoApiKey: null, loaded: false });

  useEffect(() => {
    let cancelled = false;
    if (!configPromise) configPromise = fetchBasemapConfig();
    void configPromise.then((resolved) => {
      if (!cancelled) setConfig(resolved);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return config;
}
