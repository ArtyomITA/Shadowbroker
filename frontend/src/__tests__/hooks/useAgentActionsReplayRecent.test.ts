/**
 * Vergilius (focus a vista appena nata).
 *
 * The embedded map is opened BY the very command it should obey, so it is
 * born after that command was pushed. Two things used to lose it: the first
 * poll asked `after=-1`, which returns nothing older than "now", and the
 * viewer's fly-to effect bailed out while the map did not exist yet and never
 * re-ran. These tests pin both halves of the fix.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import * as fs from 'fs';
import * as path from 'path';

import { useAgentActions } from '@/hooks/useAgentActions';

const SRC_DIR = path.resolve(__dirname, '../../');

describe('useAgentActions — recupero dei comandi recenti', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('la prima chiamata chiede i comandi di vista recenti, le successive no', async () => {
    const urls: string[] = [];
    const fetchMock = vi.fn(async (url: string) => {
      urls.push(String(url));
      // Il ciclo del hook si richiama da solo senza pause: dopo la seconda
      // chiamata lo si parcheggia, altrimenti il test gira all'infinito.
      if (urls.length > 2) await new Promise(() => {});
      return {
        ok: true,
        json: async () => ({
          actions: urls.length === 1
            ? [{ action: 'fly_to', lat: 46.48, lng: 30.73, zoom: 6, seq: 7 }]
            : [],
          cursor: 7,
        }),
      };
    });
    vi.stubGlobal('fetch', fetchMock);
    const onFlyTo = vi.fn();
    renderHook(() => useAgentActions(vi.fn(), onFlyTo));

    await waitFor(() => expect(urls.length).toBeGreaterThan(1));
    expect(urls[0]).toContain('after=-1');
    expect(urls[0]).toContain('replay_recent=90');
    expect(urls[1]).toContain('after=7');
    expect(urls[1]).not.toContain('replay_recent');
    expect(onFlyTo).toHaveBeenCalledWith({ lat: 46.48, lng: 30.73, zoom: 6 });
  });
});

describe('il volo riparte quando la mappa diventa pronta', () => {
  it("l'effetto del fly-to dipende anche da mapReady", () => {
    const viewer = fs.readFileSync(
      path.join(SRC_DIR, 'components/MaplibreViewer.tsx'),
      'utf-8',
    );
    expect(viewer).toContain('if (!flyToLocation || !mapReady || !mapRef.current) return;');
    expect(viewer).toContain('}, [flyToLocation, mapReady]);');
  });
});
