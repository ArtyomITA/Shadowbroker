/**
 * useAgentActions — receives display actions pushed by the agent.
 *
 * Every browser view owns a replay cursor. A long poll removes the old 700ms
 * latency/rate-limit loop while ensuring iframe and pop-out both receive the
 * same actions. The backend still supports destructive polling for old clients.
 *
 * Vergilius additions:
 *   - `set_layers`  turn layers on/off, or show ONLY the ones named. This is
 *     what makes "hide everything except what I'm talking about" possible; the
 *     toggles live in React state, so nothing outside the browser could reach
 *     them before.
 *   - `highlight`   drop transient markers on specific entities.
 *   - The request stays open for up to 20 seconds and returns immediately when
 *     an action arrives, so delivery no longer waits for a timer tick.
 */

import { useEffect, useRef, useCallback } from 'react';
import { API_BASE } from '@/lib/api';

export interface HighlightPoint {
  id?: string;
  lat: number;
  lng: number;
  label?: string;
}

interface AgentAction {
  seq?: number;
  action: string;
  source?: string;
  lat?: number;
  lng?: number;
  sentinel2?: Record<string, unknown>;
  preset?: string;
  caption?: string | null;
  ts?: number;
  // fly_to extras
  zoom?: number;
  aoi_id?: string;
  // set_layers
  on?: string[];
  off?: string[];
  solo?: boolean;
  reset?: boolean;
  // highlight
  points?: HighlightPoint[];
  ttl_seconds?: number;
}

const LONG_POLL_MS = 20_000;
const RETRY_MS = 750;

/**
 * @param onShowImage — agent wants to display satellite imagery for a point.
 * @param onFlyTo — agent wants to centre the map without opening imagery.
 * @param onSetLayers — agent wants to change which layers are visible.
 *   `solo` means "these and nothing else"; `reset` restores the operator's own
 *   selection from before the agent touched it.
 * @param onHighlight — agent wants to mark specific entities. An empty array
 *   clears the marks.
 */
export function useAgentActions(
  onShowImage: (coords: { lat: number; lng: number }) => void,
  onFlyTo?: (coords: { lat: number; lng: number; zoom?: number }) => void,
  enabled = true,
  onSetLayers?: (change: { on: string[]; off: string[]; solo: boolean; reset: boolean }) => void,
  onHighlight?: (points: HighlightPoint[], ttlSeconds: number) => void,
) {
  const onShowImageRef = useRef(onShowImage);
  onShowImageRef.current = onShowImage;
  const onFlyToRef = useRef(onFlyTo);
  onFlyToRef.current = onFlyTo;
  const onSetLayersRef = useRef(onSetLayers);
  onSetLayersRef.current = onSetLayers;
  const onHighlightRef = useRef(onHighlight);
  onHighlightRef.current = onHighlight;

  const cursorRef = useRef(-1);

  const applyActions = useCallback((actions: AgentAction[]) => {
    for (const action of actions) {
      if (action.action === 'show_image' && action.lat != null && action.lng != null) {
        onShowImageRef.current({ lat: action.lat, lng: action.lng });
      } else if (
        action.action === 'fly_to' &&
        action.lat != null &&
        action.lng != null
      ) {
        onFlyToRef.current?.({
          lat: action.lat,
          lng: action.lng,
          zoom: action.zoom,
        });
      } else if (action.action === 'set_layers') {
        onSetLayersRef.current?.({
          on: action.on ?? [],
          off: action.off ?? [],
          solo: action.solo ?? false,
          reset: action.reset ?? false,
        });
      } else if (action.action === 'highlight') {
        onHighlightRef.current?.(action.points ?? [], action.ttl_seconds ?? 120);
      }
    }
  }, []);

  const poll = useCallback(async (signal: AbortSignal) => {
    try {
      const params = new URLSearchParams({
        after: String(cursorRef.current),
        wait_ms: String(LONG_POLL_MS),
      });
      const res = await fetch(`${API_BASE}/api/ai/agent-actions?${params}`, {
        signal,
        cache: 'no-store',
      });
      if (!res.ok) return false;
      const data = await res.json();
      const actions: AgentAction[] = data.actions || [];
      if (typeof data.cursor === 'number') cursorRef.current = data.cursor;
      applyActions(actions);
      return true;
    } catch (cause) {
      if (signal.aborted) return true;
      return false;
    }
  }, [applyActions]);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    const loop = async () => {
      if (controller.signal.aborted) return;
      const ok = await poll(controller.signal);
      if (controller.signal.aborted) return;
      if (ok) void loop();
      else retryTimer = setTimeout(() => void loop(), RETRY_MS);
    };
    void loop();
    return () => {
      controller.abort();
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [enabled, poll]);
}
