import type { NextConfig } from 'next';

// /api/* requests are proxied to the backend by the catch-all route handler at
// src/app/api/[...path]/route.ts, which reads BACKEND_URL at request time.
// Do NOT add rewrites for /api/* here — next.config is evaluated at build time,
// so any URL baked in here ignores the runtime BACKEND_URL env var.

const skipTypecheck = process.env.NEXT_SKIP_TYPECHECK === '1';

// Desktop packaging: set NEXT_OUTPUT=export to produce a static export
// (frontend/out/) suitable for Tauri bundling and companion server hosting.
// This disables API routes, proxy, and server-side image optimization —
// all handled by the Tauri shell and companion server in packaged mode.
// Default remains 'standalone' for the web deployment (Docker/Vercel).
const isDesktopExport = process.env.NEXT_OUTPUT === 'export';

// CSP is now emitted dynamically by src/proxy.ts (Phase 5F-A) so that
// each document response carries a unique per-request nonce.  Non-CSP
// security headers remain here because they are static and benefit from
// next.config's catch-all source matcher.
// Vergilius: the dashboard is embedded in Odysseus as an iframe, so framing has
// to be permitted for exactly one origin. `X-Frame-Options` cannot express that
// — its `ALLOW-FROM` variant was removed from every current browser, leaving
// only DENY/SAMEORIGIN — and when both headers are present the legacy one wins
// in some engines. So when an allow-list is configured we drop X-Frame-Options
// and let the CSP `frame-ancestors` directive in src/proxy.ts do the gating,
// which is the modern replacement and does take an origin list.
//
// Unset => unchanged upstream behaviour (DENY, frame-ancestors 'none').
const frameAncestors = (process.env.SHADOWBROKER_FRAME_ANCESTORS || '').trim();

const securityHeaders = [
  {
    key: 'Referrer-Policy',
    value: 'no-referrer',
  },
  {
    key: 'X-Content-Type-Options',
    value: 'nosniff',
  },
  ...(frameAncestors
    ? []
    : [
        {
          key: 'X-Frame-Options',
          value: 'DENY',
        },
      ]),
];

const nextConfig: NextConfig = {
  // Vergilius: in dev, Next.js tratta `127.0.0.1` e `localhost` come origini
  // diverse e blocca le proprie risorse interne (font, WebSocket HMR) quando la
  // pagina e' stata aperta con l'altra forma. Il chunk della mappa non arriva
  // mai e resta "PRIORITIZING MAP FEEDS" per sempre — senza nessun errore
  // visibile in pagina.
  //
  // Riguarda noi in pieno: Odysseus incorpora il cruscotto in un iframe e
  // l'indirizzo puo' essere l'una o l'altra forma a seconda di come si e'
  // arrivati su Odysseus.
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
  transpilePackages: ['react-map-gl', 'maplibre-gl'],
  output: isDesktopExport ? 'export' : 'standalone',
  devIndicators: false,
  experimental: isDesktopExport
    ? {
        webpackBuildWorker: false,
        parallelServerCompiles: false,
        parallelServerBuildTraces: false,
        workerThreads: false,
      }
    : undefined,
  images: {
    unoptimized: isDesktopExport,
    remotePatterns: [
      { protocol: 'https', hostname: 'upload.wikimedia.org' },
      { protocol: 'https', hostname: 'via.placeholder.com' },
      { protocol: 'https', hostname: 'services.sentinel-hub.com' },
      { protocol: 'https', hostname: 'data.sentinel-hub.com' },
      { protocol: 'https', hostname: 'sentinel-hub.com' },
      { protocol: 'https', hostname: 'dataspace.copernicus.eu' },
    ],
  },
  typescript: {
    ignoreBuildErrors: skipTypecheck,
  },
  ...(!isDesktopExport
    ? {
        async headers() {
          return [
            {
              source: '/:path*',
              headers: securityHeaders,
            },
          ];
        },
      }
    : {}),
};

export default nextConfig;
