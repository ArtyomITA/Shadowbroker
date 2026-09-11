/**
 * MapLibre basemap styles backed by CARTO raster tiles.
 *
 * CARTO now requires an API key for its basemap tiles; unkeyed requests
 * return tiles stamped with an "API KEY REQUIRED" watermark. The key is
 * read at request time by /api/basemap-config (CARTO_API_KEY on the
 * frontend container) and threaded in here via `buildBasemapStyle`, so
 * prebuilt Docker images pick it up without a rebuild.
 *
 * With no key configured the styles are unchanged from before, so existing
 * deployments keep working exactly as they did (watermark included).
 */

export type BasemapTheme = 'dark' | 'light';

const CARTO_SUBDOMAINS = ['a', 'b', 'c', 'd'] as const;
const CARTO_RASTER_STYLE: Record<BasemapTheme, string> = {
  dark: 'dark_all',
  light: 'light_all',
};
const GLYPHS_URL = 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf';

/** Tile URL templates for a CARTO raster style, keyed when a key is supplied. */
export function cartoTileUrls(theme: BasemapTheme, cartoApiKey?: string | null): string[] {
  const style = CARTO_RASTER_STYLE[theme];
  const key = (cartoApiKey || '').trim();
  const query = key ? `?key=${encodeURIComponent(key)}` : '';
  return CARTO_SUBDOMAINS.map(
    (s) => `https://${s}.basemaps.cartocdn.com/rastertiles/${style}/{z}/{x}/{y}@2x.png${query}`,
  );
}

export function buildBasemapStyle(theme: BasemapTheme, cartoApiKey?: string | null) {
  const sourceId = `carto-${theme}`;
  return {
    version: 8,
    glyphs: GLYPHS_URL,
    sources: {
      [sourceId]: {
        type: 'raster',
        tiles: cartoTileUrls(theme, cartoApiKey),
        tileSize: 256,
      },
    },
    layers: [
      { id: `${sourceId}-layer`, type: 'raster', source: sourceId, minzoom: 0, maxzoom: 22 },
      { id: 'imagery-ceiling', type: 'background', paint: { 'background-opacity': 0 } },
    ],
  };
}

// Key-less defaults, kept for callers that do not need a CARTO key.
export const darkStyle = buildBasemapStyle('dark');
export const lightStyle = buildBasemapStyle('light');
