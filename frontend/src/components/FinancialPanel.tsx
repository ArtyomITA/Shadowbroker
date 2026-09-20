'use client';

/**
 * FINANCIAL — left-column collapsible section between DATA LAYERS and
 * MESHTASTIC CHAT. Same panel skin as its neighbours (MeshChat / ShodanPanel).
 *
 * Contents:
 *  - FINANCIAL MAP MODE: one switch applies the slim financial layer preset
 *    ("solo" semantics via the same onApplyPreset wiring WorldviewLeftPanel
 *    gets); switching it off restores the operator's own selection.
 *  - Finnhub market news wire from the slow-poll `finnhub_news` key.
 */

import React, { useState } from 'react';
import { TrendingUp, Plus, Minus } from 'lucide-react';
import { useDataKeys } from '@/hooks/useDataStore';
import type { FinnhubNewsItem } from '@/types/dashboard';

/**
 * Slim financial map view: news layers only — GDELT incidents, the RSS news
 * alerts, and Finnhub financial news pinned at each ticker's company HQ.
 * military_bases and datacenters were dropped: they proved to be noise for a
 * markets-first read of the map.
 */
const FINANCIAL_LAYERS = ['gdelt', 'news', 'finnhub_news'];

/** Tempo relativo in italiano ("12 min fa"). Accetta ISO o epoch in s/ms.
 *  Vergilius (difetto 24): questo pannello e' nostro e deve parlare una sola
 *  lingua; prima mescolava "1h ago" e "sulla mappa". */
function newsTime(published: string | number | undefined): string {
  if (published === undefined || published === null || published === '') return '';
  let ms: number;
  if (typeof published === 'number') {
    ms = published < 1e12 ? published * 1000 : published;
  } else {
    ms = Date.parse(published);
    if (Number.isNaN(ms)) ms = Date.parse(published + 'Z');
  }
  if (!Number.isFinite(ms) || Number.isNaN(ms)) return '';
  const diff = Date.now() - ms;
  if (diff < 60_000) return 'adesso';
  const min = Math.floor(diff / 60_000);
  if (min < 60) return `${min} min fa`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} h fa`;
  return `${Math.floor(hr / 24)} g fa`;
}

export default function FinancialPanel({
  onApplyPreset,
}: {
  /** Same wiring as WorldviewLeftPanel: string[] = solo these layers, null = restore. */
  onApplyPreset?: (layerNames: string[] | null) => void;
}) {
  // Default COLLAPSED — matches the rest of the left column on first load.
  const [expanded, setExpanded] = useState(false);
  const [mapMode, setMapMode] = useState(false);
  const data = useDataKeys(['finnhub_news'] as const);
  const items: FinnhubNewsItem[] = Array.isArray(data?.finnhub_news) ? data.finnhub_news : [];

  const toggleMapMode = (e: React.MouseEvent) => {
    e.stopPropagation();
    const next = !mapMode;
    setMapMode(next);
    onApplyPreset?.(next ? FINANCIAL_LAYERS : null);
  };

  return (
    <div className="pointer-events-auto flex flex-col flex-shrink-0">
      {/* Single unified box — matches Data Layers / MeshChat panel skin */}
      <div className="bg-[#0a0a0a]/90 backdrop-blur-sm border border-cyan-900/40 flex flex-col relative overflow-hidden">
        {/* HEADER */}
        <div
          onClick={() => setExpanded(!expanded)}
          className="flex items-center justify-between px-3 py-2.5 cursor-pointer hover:bg-cyan-950/30 transition-colors border-b border-cyan-900/40 shrink-0 select-none"
        >
          <div className="flex items-center gap-2">
            <TrendingUp size={16} className="text-cyan-400" />
            <span className="text-[12px] text-cyan-400 font-mono tracking-widest font-bold">
              FINANCIAL
            </span>
            {mapMode && (
              <span className="text-[9px] font-mono px-1.5 py-0.5 bg-cyan-500/20 border border-cyan-500/40 text-cyan-300">
                MAP MODE
              </span>
            )}
          </div>
          {expanded ? (
            <Minus size={16} className="text-cyan-400" />
          ) : (
            <Plus size={16} className="text-cyan-400" />
          )}
        </div>

        {/* EXPANDED BODY */}
        {expanded && (
          <div className="flex flex-col gap-3 p-3">
            {/* FINANCIAL MAP MODE — same switch skin as the layer-section toggles */}
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono tracking-[0.2em] font-bold text-[var(--text-muted)]">
                FINANCIAL MAP MODE
              </span>
              <button
                className="relative w-8 h-4 rounded-full transition-colors shrink-0"
                style={{
                  backgroundColor: mapMode ? 'rgb(6 182 212 / 0.5)' : 'rgb(100 116 139 / 0.3)',
                }}
                onClick={toggleMapMode}
                title={
                  mapMode
                    ? 'Ripristina i livelli scelti prima della modalità mappa finanziaria'
                    : `Mostra solo: ${FINANCIAL_LAYERS.join(', ')}`
                }
              >
                <span
                  className="absolute top-0.5 w-3 h-3 rounded-full transition-all"
                  style={{
                    left: mapMode ? '18px' : '2px',
                    backgroundColor: mapMode ? 'rgb(34 211 238)' : 'rgb(148 163 184 / 0.5)',
                  }}
                />
              </button>
            </div>

            {/* FINNHUB NEWS WIRE */}
            <div className="flex flex-col gap-1.5">
              <span className="text-[9px] font-mono tracking-[0.2em] text-[var(--text-muted)]">
                MARKET WIRE · FINNHUB
              </span>
              {items.length === 0 ? (
                <div className="text-[10px] font-mono text-[var(--text-muted)]/60 py-2">
                  in attesa del flusso Finnhub…
                </div>
              ) : (
                <div className="max-h-[320px] overflow-y-auto styled-scrollbar flex flex-col gap-2 pr-1">
                  {items.slice(0, 30).map((item, i) => {
                    const when = newsTime(item?.published);
                    return (
                      <div
                        key={`${item?.url || item?.title || 'fin'}-${i}`}
                        className="flex flex-col gap-0.5 border-b border-cyan-900/20 pb-1.5 last:border-b-0 last:pb-0"
                      >
                        <div className="flex items-start gap-1.5">
                          {item?.ticker && (
                            <span className="text-[9px] font-mono px-1 py-px border border-cyan-500/40 text-cyan-300 shrink-0 mt-px">
                              {item.ticker}
                            </span>
                          )}
                          <a
                            href={item?.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[11px] font-mono leading-snug text-[var(--text-primary)] hover:text-cyan-300 transition-colors"
                          >
                            {item?.title || '(senza titolo)'}
                          </a>
                        </div>
                        <div className="text-[10px] font-mono text-[var(--text-muted)]">
                          {item?.source || 'finnhub'}
                          {when ? ` · ${when}` : ''}
                          {/* HQ pin available — the finnhub_news layer shows it on the map */}
                          {item?.lat != null && item?.lng != null && (
                            <span className="text-amber-400/80"> · sulla mappa</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
