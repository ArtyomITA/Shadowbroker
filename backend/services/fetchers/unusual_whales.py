"""Finnhub scheduled fetcher — congress trades, insider transactions, defense quotes.

Runs on a 15-minute schedule and stores results in latest_data["unusual_whales"].
Quotes stay inside that layer only — latest_data["stocks"] is owned by the
per-minute financial sweep (see fetch_financial_markets).
Falls back gracefully if no API key is configured.
"""

import logging
from services.fetchers._store import latest_data, _data_lock, _mark_fresh
from services.fetchers.retry import with_retry

logger = logging.getLogger(__name__)


@with_retry(max_retries=1, base_delay=2)
def fetch_unusual_whales():
    """Fetch congress trades, insider txns, and defense quotes from Finnhub."""
    import os

    if not os.environ.get("FINNHUB_API_KEY", "").strip():
        logger.debug("FINNHUB_API_KEY not set — skipping scheduled fetch.")
        return

    from services.unusual_whales_connector import (
        fetch_congress_trades,
        fetch_insider_transactions,
        fetch_defense_quotes,
        FinnhubConnectorError,
    )

    result: dict = {}

    # Defense stock quotes — kept inside the unusual_whales layer payload only.
    #
    # NON scrivere latest_data["stocks"] qui: queste sono 8 voci (6 difesa +
    # 2 cripto) e assegnarle rimpiazzerebbe la mappa da 25 simboli prodotta
    # dallo spazzolamento al minuto di financial.py, restringendola per ~60s
    # ogni 15 minuti. Quel layer lo possiede lo sweep finanziario.
    try:
        quotes = fetch_defense_quotes()
        if quotes:
            result["quotes"] = quotes
    except FinnhubConnectorError as e:
        logger.warning(f"Finnhub quotes fetch failed: {e.detail}")
    except Exception as e:
        logger.warning(f"Finnhub quotes fetch error: {e}")

    # Congress trades
    try:
        congress = fetch_congress_trades()
        result["congress_trades"] = congress.get("trades", [])
    except FinnhubConnectorError as e:
        logger.warning(f"Finnhub congress trades fetch failed: {e.detail}")
    except Exception as e:
        logger.warning(f"Finnhub congress trades fetch error: {e}")

    # Insider transactions
    try:
        insiders = fetch_insider_transactions()
        result["insider_transactions"] = insiders.get("transactions", [])
    except FinnhubConnectorError as e:
        logger.warning(f"Finnhub insider fetch failed: {e.detail}")
    except Exception as e:
        logger.warning(f"Finnhub insider fetch error: {e}")

    if not result:
        logger.warning("Finnhub update produced no data; keeping previous cache.")
        return

    with _data_lock:
        latest_data["unusual_whales"] = result
    _mark_fresh("unusual_whales")
    logger.info(
        f"Finnhub updated: {len(result.get('congress_trades', []))} congress, "
        f"{len(result.get('insider_transactions', []))} insider, "
        f"{len(result.get('quotes', {}))} quotes"
    )
