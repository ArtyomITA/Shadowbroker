'use client';

import { type CSSProperties, type ReactNode, useCallback, useEffect, useState } from 'react';
import { API_BASE } from '@/lib/api';
import styles from './StartupGate.module.css';

type StartupProfile = 'shadowbroker' | 'vergilius-chat' | 'vergilius-lite' | 'full';
type StartupComponent = {
  id: string;
  label: string;
  status: 'loading' | 'ready' | 'error';
  detail?: string;
};
type StartupStatus = {
  profile: StartupProfile | null;
  phase: 'choose' | 'loading' | 'ready';
  progress: number;
  ready: boolean;
  components: StartupComponent[];
  target_url: string;
  /** Vergilius: il backend dichiara che la regia del boot (:7001) esiste. */
  boot_present?: boolean;
};

const PROFILES: Array<{
  id: StartupProfile;
  name: string;
  description: string;
  includes: string;
}> = [
  {
    id: 'shadowbroker',
    name: 'SHADOWBROKER',
    description: 'Centro operativo cartografico e intelligence in tempo reale.',
    includes: 'Mappa completa · radio/SIGINT · tutti i feed OSINT',
  },
  {
    id: 'vergilius-chat',
    name: 'VERGILIUS CHAT',
    description: 'La chat completa con il modello locale, memoria e RAG. Senza ShadowBroker.',
    includes: 'LLM · RAG · memoria · MCP · strumenti',
  },
  {
    id: 'vergilius-lite',
    name: 'VERGILIUS LITE',
    description: 'Esperienza Vergilius completa senza il sottosistema vocale e Avatar 2D.',
    includes: 'LLM · RAG · memoria · MCP · ShadowBroker · strumenti',
  },
  {
    id: 'full',
    name: 'FULL',
    description: 'Tutto lo stack, inclusa interazione vocale e presenza Avatar 2D.',
    includes: 'Vergilius Lite · TTS/STT live · Avatar 2D',
  },
];

async function readStatus(signal?: AbortSignal): Promise<StartupStatus> {
  const response = await fetch(`${API_BASE}/api/startup/status`, { signal, cache: 'no-store' });
  if (!response.ok) throw new Error(`startup_status_${response.status}`);
  return response.json() as Promise<StartupStatus>;
}

export default function StartupGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<StartupStatus | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  // Primo rendering identico su server e browser (niente errori di idratazione): il gate
  // decide solo dopo il montaggio, quando `window` esiste davvero.
  const [montato, setMontato] = useState(false);
  useEffect(() => { setMontato(true); }, []);
  // Vergilius (difetti 6/7): una volta vista la regia del boot, o un profilo
  // gia' scelto, il selettore non deve piu' ricomparire per una lettura di
  // stato lenta o fallita. Si mostra "riconnessione" e basta.
  const [regiaBoot, setRegiaBoot] = useState(false);
  const [profiloVisto, setProfiloVisto] = useState(false);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const next = await readStatus(signal);
    setStatus(next);
    if (next.boot_present || (next.target_url || '').includes(':7001')) setRegiaBoot(true);
    if (next.profile) setProfiloVisto(true);
    return next;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | null = null;
    const poll = async () => {
      try {
        const next = await refresh(controller.signal);
        setError('');
        if (!next.ready) timer = setTimeout(poll, next.profile ? 800 : 1600);
      } catch (cause) {
        if (controller.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : 'Bootstrap non raggiungibile');
        timer = setTimeout(poll, 1800);
      }
    };
    void poll();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [refresh]);

  useEffect(() => {
    // Vergilius Boot (:7001) e' la regia: se nessun profilo e' scelto e il
    // backend ci rimanda li', andiamo li' invece di avviare da qui.
    if (status && !status.profile && status.target_url && status.target_url.includes(':7001')
        && window.self === window.top) {
      window.location.replace(status.target_url);
      return;
    }
    if (!status?.ready || status.profile === 'shadowbroker') return;
    if (window.self !== window.top) return;
    const current = `${window.location.protocol}//${window.location.host}`;
    if (status.target_url && current !== status.target_url) {
      window.location.replace(status.target_url);
    }
  }, [status]);

  const choose = async (profile: StartupProfile) => {
    setSubmitting(true);
    setError('');
    try {
      const response = await fetch(`${API_BASE}/api/startup/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(String(body.detail || `startup_profile_${response.status}`));
      }
      setStatus((await response.json()) as StartupStatus);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Impossibile avviare il profilo');
    } finally {
      setSubmitting(false);
    }
  };

  // Il profilo si sceglie UNA volta sola, nel Vergilius Boot (:7001), che ne e'
  // la regia dichiarata (vedi `_stato_dal_boot` lato backend). Questo gate non
  // deve richiederlo una seconda volta.
  //
  // Dentro un iframe non si chiede mai: la regia sta fuori, e Odysseus, che
  // incorpora questo pannello, ha gia' il suo indicatore di stato
  // nell'intestazione. Bastava che la chiamata di stato fallisse dentro
  // l'iframe (status nullo) perche' il selettore comparisse sopra la mappa.
  //
  // `window` non esiste durante il rendering lato server: letto qui senza guardia faceva
  // rispondere 500 a TUTTA la dashboard in produzione (`next start`), con
  // "ReferenceError: window is not defined". Sul server si mostra la pagina: la regia
  // vera parte comunque nel browser, negli useEffect qui sopra.
  if (!montato || typeof window === 'undefined' || window.self !== window.top) {
    return children;
  }
  // A finestra intera: se un profilo e' gia' scelto ed e' pronto, si entra.
  // La condizione era `status.profile === 'shadowbroker'`, quindi chi sceglieva
  // 'vergilius-lite' o 'vergilius-chat' nel boot se lo vedeva richiedere di
  // nuovo. Se il profilo c'e' ma non e' ancora pronto si continua a mostrare la
  // rotella di avanzamento (ramo `hasProfile` qui sotto). Per cambiarlo, si
  // torna al boot.
  if (status?.ready && status.profile) {
    return children;
  }

  const hasProfile = Boolean(status?.profile);
  // Il selettore si mostra solo quando questa finestra e' davvero la regia:
  // nessun boot :7001 in giro, nessun profilo mai visto, stato letto e valido.
  const mostraSelettore = !hasProfile && !regiaBoot && !profiloVisto && Boolean(status) && !error;
  const riconnessione = !hasProfile && !mostraSelettore;
  const progress = Math.max(0, Math.min(100, status?.progress || 0));
  const dialStyle = { '--startup-progress': `${progress * 3.6}deg` } as CSSProperties;

  return (
    <>
      {hasProfile ? <div className={styles.contentBlur}>{children}</div> : null}
      <div className={styles.gate} aria-busy={hasProfile}>
        {!hasProfile ? <div className={styles.backdrop} /> : null}
        <div className={styles.veil}>
          <section className={styles.panel} role={hasProfile ? 'status' : 'dialog'} aria-modal="true">
            <div className={styles.eyebrow}>Vergilius boot control</div>
            <h1 className={styles.title}>
              {hasProfile ? 'SISTEMI IN AVVIO' : riconnessione ? 'RICONNESSIONE…' : 'SCEGLI IL PROFILO'}
            </h1>
            <p className={styles.subtitle}>
              {hasProfile
                ? 'Ogni indicatore corrisponde a un componente reale. La console resterà protetta finché il profilo non sarà completamente operativo.'
                : riconnessione
                  ? 'Lettura dello stato di avvio in corso. Il profilo è già stato scelto nel Vergilius Boot: nessuna scelta da rifare qui.'
                  : 'La scelta vale per questa accensione. Nessun controllo della console sarà disponibile prima della selezione.'}
            </p>

            {riconnessione ? null : mostraSelettore ? (
              <div className={styles.profiles}>
                {PROFILES.map((profile) => (
                  <button
                    key={profile.id}
                    type="button"
                    className={styles.profile}
                    disabled={submitting || !status}
                    onClick={() => void choose(profile.id)}
                  >
                    <span className={styles.profileName}>{profile.name}</span>
                    <span className={styles.profileDescription}>{profile.description}</span>
                    <span className={styles.profileIncludes}>{profile.includes}</span>
                  </button>
                ))}
              </div>
            ) : (
              <div className={styles.loadingLayout}>
                <div className={styles.dial} style={dialStyle}>
                  <span className={styles.percentage}>{progress}%</span>
                </div>
                <div className={styles.componentList}>
                  {(status?.components || []).map((component) => (
                    <div
                      key={component.id}
                      className={`${styles.component} ${styles[component.status]}`}
                      title={component.detail || undefined}
                    >
                      <span className={styles.dot} />
                      <span>{component.label}</span>
                      <span className={styles.status}>
                        {component.status === 'ready' ? 'caricato' : component.status === 'error' ? 'errore' : 'caricamento'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {error ? <div className={styles.errorText}>{error}</div> : null}
          </section>
        </div>
      </div>
    </>
  );
}

