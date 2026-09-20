/**
 * MapLibre basemap styles on CARTO raster tiles. CARTO requires an API key
 * (unkeyed tiles are watermarked); MaplibreViewer passes one from
 * useBasemapConfig() via buildBasemapStyle(). The key is served by the
 * backend at GET /api/basemap-config.
 */

export type BasemapTheme = 'dark' | 'light';

const CARTO_SUBDOMAINS = ['a', 'b', 'c', 'd'] as const;
const CARTO_RASTER_STYLE: Record<BasemapTheme, string> = {
  dark: 'dark_all',
  light: 'light_all',
};
const GLYPHS_URL = 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf';

// Declared on the raster source so MapLibre's AttributionControl shows it
// even without the custom list in MaplibreViewer. Same markup as that list so
// the control de-duplicates instead of showing both.
export const OSM_ATTRIBUTION_HTML =
  '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors</a>';
export const CARTO_ATTRIBUTION_HTML =
  '<a href="https://carto.com/attribution" target="_blank" rel="noopener">CARTO</a>';

// Vergilius: senza chiave CARTO ogni tassello arriva timbrato "API KEY
// REQUIRED". Qui non si spediscono chiavi e non si aprono account, quindi
// senza chiave si passa a un fondo scuro SENZA chiave: Esri World Dark Gray
// (base + riferimenti), stesso aspetto notturno di CARTO dark_all.
const ESRI_BASE = 'https://services.arcgisonline.com/ArcGIS/rest/services/Canvas';
const ESRI_TILES: Record<BasemapTheme, { base: string; ref: string }> = {
  dark: { base: 'World_Dark_Gray_Base', ref: 'World_Dark_Gray_Reference' },
  light: { base: 'World_Light_Gray_Base', ref: 'World_Light_Gray_Reference' },
};
export const ESRI_ATTRIBUTION_HTML =
  '<a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a>, HERE, Garmin';

/** Tasselli Esri Canvas (nessuna chiave) per un tema. */
export function esriCanvasTileUrls(theme: BasemapTheme, variante: 'base' | 'ref'): string[] {
  const servizio = ESRI_TILES[theme][variante];
  return [`${ESRI_BASE}/${servizio}/MapServer/tile/{z}/{y}/{x}`];
}

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
  // L'identificativo della sorgente resta `carto-<tema>` anche col fondo Esri:
  // e' l'id del fondo mappa, usato altrove per l'ordine dei livelli.
  const sourceId = `carto-${theme}`;
  const chiave = (cartoApiKey || '').trim();
  const soffitto = { id: 'imagery-ceiling', type: 'background', paint: { 'background-opacity': 0 } };

  // Vergilius: nessuna chiave CARTO -> fondo Esri Canvas, senza filigrana.
  if (!chiave) {
    const refId = `${sourceId}-ref`;
    return {
      version: 8,
      glyphs: GLYPHS_URL,
      sources: {
        [sourceId]: {
          type: 'raster',
          tiles: esriCanvasTileUrls(theme, 'base'),
          tileSize: 256,
          maxzoom: 16,
          attribution: `${ESRI_ATTRIBUTION_HTML} ${OSM_ATTRIBUTION_HTML}`,
        },
        [refId]: {
          type: 'raster',
          tiles: esriCanvasTileUrls(theme, 'ref'),
          tileSize: 256,
          maxzoom: 16,
        },
      },
      layers: [
        { id: `${sourceId}-layer`, type: 'raster', source: sourceId, minzoom: 0, maxzoom: 22 },
        { id: `${refId}-layer`, type: 'raster', source: refId, minzoom: 0, maxzoom: 22 },
        soffitto,
      ],
    };
  }

  return {
    version: 8,
    glyphs: GLYPHS_URL,
    sources: {
      [sourceId]: {
        type: 'raster',
        tiles: cartoTileUrls(theme, cartoApiKey),
        tileSize: 256,
        attribution: `${OSM_ATTRIBUTION_HTML} ${CARTO_ATTRIBUTION_HTML}`,
      },
    },
    layers: [
      { id: `${sourceId}-layer`, type: 'raster', source: sourceId, minzoom: 0, maxzoom: 22 },
      soffitto,
    ],
  };
}

export const darkStyle = buildBasemapStyle('dark');
export const lightStyle = buildBasemapStyle('light');
