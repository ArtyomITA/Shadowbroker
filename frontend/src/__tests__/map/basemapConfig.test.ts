import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { GET as getBasemapConfig } from '@/app/api/basemap-config/route';
import {
  buildBasemapStyle,
  cartoTileUrls,
  darkStyle,
  lightStyle,
} from '@/components/map/styles/mapStyles';

describe('CARTO basemap API key plumbing', () => {
  const originalKey = process.env.CARTO_API_KEY;

  beforeEach(() => {
    delete process.env.CARTO_API_KEY;
  });

  afterEach(() => {
    if (originalKey === undefined) delete process.env.CARTO_API_KEY;
    else process.env.CARTO_API_KEY = originalKey;
  });

  describe('GET /api/basemap-config', () => {
    it('reports unconfigured when CARTO_API_KEY is unset', async () => {
      const res = await getBasemapConfig();
      expect(res.status).toBe(200);
      expect(res.headers.get('cache-control')).toContain('no-store');
      expect(await res.json()).toEqual({ carto: { configured: false, key: '' } });
    });

    it('returns the trimmed key read at request time', async () => {
      process.env.CARTO_API_KEY = '  abc123  ';
      const res = await getBasemapConfig();
      expect(await res.json()).toEqual({ carto: { configured: true, key: 'abc123' } });
    });
  });

  describe('buildBasemapStyle', () => {
    it('produces unkeyed CARTO tile URLs when no key is given', () => {
      const style = buildBasemapStyle('dark');
      const source = style.sources['carto-dark'];
      expect(source.tiles).toHaveLength(4);
      for (const url of source.tiles) {
        expect(url).toMatch(/^https:\/\/[abcd]\.basemaps\.cartocdn\.com\/rastertiles\/dark_all\//);
        expect(url).not.toContain('?');
      }
      expect(style.layers[0]).toMatchObject({ id: 'carto-dark-layer', source: 'carto-dark' });
    });

    it('appends ?key= to every tile URL when a key is given', () => {
      const style = buildBasemapStyle('light', 'my key');
      for (const url of style.sources['carto-light'].tiles) {
        expect(url).toMatch(/\/rastertiles\/light_all\/\{z\}\/\{x\}\/\{y\}@2x\.png\?key=my%20key$/);
      }
    });

    it('treats blank keys as unconfigured', () => {
      expect(cartoTileUrls('dark', '   ')).toEqual(cartoTileUrls('dark'));
      expect(cartoTileUrls('dark', null)).toEqual(cartoTileUrls('dark'));
    });

    it('keeps the key-less default exports in sync with the builder', () => {
      expect(darkStyle).toEqual(buildBasemapStyle('dark'));
      expect(lightStyle).toEqual(buildBasemapStyle('light'));
    });
  });
});
