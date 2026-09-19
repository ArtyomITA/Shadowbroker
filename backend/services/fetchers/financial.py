import logging
import math
import random
import time
import os
import urllib.request
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from services.fetchers._store import latest_data, _data_lock, _mark_fresh
from services.fetchers.retry import with_retry

logger = logging.getLogger(__name__)

_YFINANCE_REQUEST_DELAY_SECONDS = 0.5
_YFINANCE_REQUEST_JITTER_SECONDS = 0.2

TICKERS_DEFENSE = ["RTX", "LMT", "NOC", "GD", "BA", "PLTR"]
TICKERS_TECH = ["NVDA", "AMD", "TSM", "INTC", "GOOGL", "AMZN", "MSFT", "AAPL", "TSLA", "META", "NFLX", "SMCI", "ARM", "ASML"]
TICKERS_CRYPTO = [
    ("BTC", "BINANCE:BTCUSDT", "BTC-USD"),
    ("ETH", "BINANCE:ETHUSDT", "ETH-USD"),
    ("SOL", "BINANCE:SOLUSDT", "SOL-USD"),
    ("XRP", "BINANCE:XRPUSDT", "XRP-USD"),
    ("ADA", "BINANCE:ADAUSDT", "ADA-USD"),
]

# Preset "broad" (services.financial_config): i 25 del core piu' questi 35,
# 60 simboli totali. Coprono i settori che il core ignora del tutto.
TICKERS_BROAD_EXTRA = [
    "JPM", "GS", "MS", "BAC", "WFC", "C", "BLK", "V", "MA",   # finanza
    "XOM", "CVX", "COP", "SLB", "OXY",                         # energia
    "CAT", "DE", "HON", "GE", "LHX", "HII", "AVGO",            # industria
    "QCOM", "MU", "TXN", "ORCL", "CRM", "IBM", "ADBE",         # tech
    "LLY", "JNJ", "PFE", "UNH", "WMT", "KO", "PEP",            # salute/consumo
]

# Contatore delle passate in modalita' broad: serve ad alternare le due meta'
# della lista, cosi' 60 simboli non finiscono mai nello stesso minuto.
_broad_sweep_counter = 0

# Ticker priority for high-frequency updates (we update these every tick)
PRIORITY_SYMBOLS = ["BTC", "ETH", "NVDA", "PLTR"]

# Minimum seconds between two Finnhub sweeps. The free tier allows 60 calls per
# minute; a full sweep is len(TICKERS_TECH + TICKERS_DEFENSE + TICKERS_CRYPTO)
# calls, so at 30s that is 2 sweeps/minute and roughly half the budget — leaving
# headroom for the insider/congress fetcher that shares the same key.
FINNHUB_THROTTLE_S = float(os.getenv("FINNHUB_THROTTLE_SECONDS", "30"))

# Persistence for state between short-lived scheduler ticks
_last_fetch_results = {}
_last_fetch_time = 0.0
_rotating_index = 0
_executor = ThreadPoolExecutor(max_workers=10)


# Quanto resta del tetto al minuto, letto dalle intestazioni della risposta.
# Finnhub le manda a ogni chiamata (X-Ratelimit-Limit / -Remaining / -Reset):
# meglio leggere il numero vero che stimarlo, perche' la stessa chiave la usano
# anche il fetcher insider e quello delle notizie.
_budget = {"restanti": None, "azzeramento": 0.0}
_budget_lock = threading.Lock()


def _aggiorna_budget(headers):
    try:
        restanti = int(headers.get("X-Ratelimit-Remaining", ""))
        azzeramento = float(headers.get("X-Ratelimit-Reset", "0") or 0)
    except (TypeError, ValueError):
        return
    with _budget_lock:
        _budget["restanti"] = restanti
        _budget["azzeramento"] = azzeramento


def budget_residuo() -> int | None:
    """Chiamate ancora disponibili nella finestra corrente, o None se ignoto."""
    with _budget_lock:
        if _budget["restanti"] is None:
            return None
        # Passato l'istante di azzeramento il contatore riparte pieno.
        if time.time() >= _budget["azzeramento"]:
            return None
        return _budget["restanti"]


def aggiorna_budget(headers) -> None:
    """Alimenta il contatore condiviso dalle risposte di altri fetcher Finnhub.

    Stessa chiave, stesso tetto al minuto: il fetcher delle notizie
    (finnhub_news) passa qui le intestazioni delle proprie risposte, cosi'
    il budget visto da tutti riflette anche la sua spesa.
    """
    _aggiorna_budget(headers)


def _fetch_finnhub_quote(symbol: str, api_key: str):
    """Fetch from Finnhub. Returns (symbol, data) or (symbol, None)."""
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={api_key}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            _aggiorna_budget(response.headers)
            data = json.loads(response.read().decode())
            if "c" not in data or data["c"] == 0:
                return symbol, None
            current = float(data["c"])
            change_p = float(data.get("dp", 0.0) or 0.0)
            return symbol, {
                "price": round(current, 2),
                "change_percent": round(change_p, 2),
                "up": bool(change_p >= 0),
            }
    except Exception as e:
        logger.debug(f"Finnhub error for {symbol}: {e}")
        return symbol, None


def _fetch_yfinance_single(symbol: str, period: str = "2d"):
    """Fetch from yfinance. Returns (symbol, data) or (symbol, None)."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if len(hist) >= 1:
            current_price = hist["Close"].iloc[-1]
            prev_close = hist["Close"].iloc[0] if len(hist) > 1 else current_price
            change_percent = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0
            current_price_f = float(current_price)
            change_percent_f = float(change_percent)
            if not math.isfinite(current_price_f) or not math.isfinite(change_percent_f):
                return symbol, None
            return symbol, {
                "price": round(current_price_f, 2),
                "change_percent": round(change_percent_f, 2),
                "up": bool(change_percent_f >= 0),
            }
    except Exception as e:
        logger.debug(f"Yfinance error for {symbol}: {e}")
    return symbol, None


@with_retry(max_retries=1, base_delay=1)
def financial_fetch_enabled() -> bool:
    """Return True only when the operator explicitly opts into financial pulls.

    Either ``FINANCIAL_ENABLED=true`` or the presence of ``FINNHUB_API_KEY``
    counts as an explicit opt-in. Without either, the default yfinance path
    is disabled to avoid silent outbound calls to finance.yahoo.com.
    """
    if os.getenv("FINNHUB_API_KEY", "").strip():
        return True
    return str(os.environ.get("FINANCIAL_ENABLED", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def fetch_financial_markets():
    """Fetches full market list with smart throttling (3s for Finnhub, 60s for yfinance)."""
    global _last_fetch_time, _last_fetch_results, _rotating_index, _broad_sweep_counter

    if not financial_fetch_enabled():
        logger.debug(
            "Financial fetch skipped; set FINANCIAL_ENABLED=true or supply "
            "FINNHUB_API_KEY to opt in"
        )
        with _data_lock:
            latest_data["financial"] = {}
        _mark_fresh("financial")
        return

    finnhub_key = os.getenv("FINNHUB_API_KEY", "").strip()
    use_finnhub = bool(finnhub_key)
    
    now = time.time()
    # Throttle logic: configurable for Finnhub (default 30s), 60s for yfinance
    throttle_s = FINNHUB_THROTTLE_S if use_finnhub else 60.0

    if now - _last_fetch_time < throttle_s and _last_fetch_results:
        return # Skip if too frequent

    _last_fetch_time = now
    
    # Prepare symbol lists
    all_crypto = {label: (f_sym, y_sym) for label, f_sym, y_sym in TICKERS_CRYPTO}
    all_stocks = TICKERS_TECH + TICKERS_DEFENSE
    
    subset_to_fetch = []
    
    if use_finnhub:
        # Sweep EVERY symbol, not three of them.
        #
        # The previous version fetched BTC, ETH and one rotating ticker per run,
        # sized for a 3-second tick. But the scheduler calls this once every
        # FINANCIAL_REFRESH_MINUTES, so in practice a single ticker was refreshed
        # per run and a full pass over the 25 symbols took hours — most of the
        # list showed a price from the previous session, with nothing saying so.
        #
        # Budget check: 25 calls per sweep (core preset), throttled to one
        # sweep every 30s, is 50 calls/minute against a 60/minute free tier.
        # The insider and congress fetcher runs every 15 minutes and is
        # cached, so the two together stay under the ceiling.
        subset_to_fetch = list(all_stocks)

        # Preset runtime (services.financial_config): "broad" aggiunge 35
        # simboli ai 25 del core. Vale solo per il ramo Finnhub — il
        # fallback yfinance resta sui 25 per non martellare Yahoo.
        try:
            from services.financial_config import get_config
            preset = get_config().get("preset", "core")
        except Exception:
            preset = "core"
        if preset == "broad":
            subset_to_fetch += TICKERS_BROAD_EXTRA

        for label, (f_sym, y_sym) in all_crypto.items():
            subset_to_fetch.append(f_sym)

        if preset == "broad":
            # 60 simboli non entrano in un minuto insieme agli altri fetcher
            # che condividono la chiave: si alternano le due meta' (indici
            # pari / dispari) a ogni passata. Ogni simbolo si aggiorna ogni
            # 2 minuti e la spesa resta ~30 chiamate al minuto. La divisione
            # per indice tiene anche le cripto sparse fra le due meta'.
            subset_to_fetch = subset_to_fetch[_broad_sweep_counter % 2 :: 2]
            _broad_sweep_counter += 1

        # Guardia sul tetto vero. Il limite misurato sull'API e' 60 al minuto
        # (X-Ratelimit-Limit), e la stessa chiave la usano anche il fetcher
        # insider e quello delle notizie. Se non c'e' spazio per la passata
        # intera si accorcia invece di prendersi dei 429: meglio meno simboli
        # aggiornati che una raffica di errori che li lascia fermi tutti.
        residuo = budget_residuo()
        if residuo is not None:
            margine = 8  # lasciato agli altri fetcher che condividono la chiave
            disponibili = max(0, residuo - margine)
            if disponibili < len(subset_to_fetch):
                logger.info(
                    "Finnhub: restano %d chiamate, passata ridotta da %d a %d simboli",
                    residuo, len(subset_to_fetch), disponibili,
                )
                subset_to_fetch = subset_to_fetch[:disponibili]
        if not subset_to_fetch:
            return

        # Concurrently fetch
        futures = [_executor.submit(_fetch_finnhub_quote, s, finnhub_key) for s in subset_to_fetch]
        for f in futures:
            sym, data = f.result()
            if data:
                # Map back to readable label if it was crypto
                label = sym
                for l, (fs, ys) in all_crypto.items():
                    if fs == sym:
                        label = l
                        break
                _last_fetch_results[label] = data
    else:
        # Yahoo Finance Fallback - fetch all (once per minute)
        logger.info("Finnhub key missing, using Yahoo Finance 60s update cycle.")
        to_fetch = all_stocks + [y_sym for l, (fs, y_sym) in all_crypto.items()]
        futures = [_executor.submit(_fetch_yfinance_single, s) for s in to_fetch]
        for f in futures:
            sym, data = f.result()
            if data:
                # Map back to readable label if it was crypto
                label = sym
                for l, (fs, ys) in all_crypto.items():
                    if ys == sym:
                        label = l
                        break
                _last_fetch_results[label] = data

    if not _last_fetch_results:
        return
        
    with _data_lock:
        latest_data["stocks"] = dict(_last_fetch_results)
        latest_data["financial_source"] = "finnhub" if use_finnhub else "yfinance"
    _mark_fresh("stocks")
