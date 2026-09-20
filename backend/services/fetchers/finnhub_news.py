"""Notizie finanziarie da Finnhub.

ShadowBroker chiamava quattro endpoint di Finnhub — quotazioni, cripto, insider,
Congresso — ma **mai** quello delle notizie, che pure sta nel piano gratuito.
Questo modulo lo aggiunge.

Due sorgenti, un solo layer:

  /news?category=general        il flusso generale dei mercati        1 chiamata
  /company-news?symbol=...      notizie sui titoli della difesa       1 per titolo

Costo: 1 + len(TITOLI_SEGUITI) chiamate per giro. Con la pianificazione a dieci
minuti sono trascurabili rispetto al tetto di 60 al minuto, che se lo mangia
quasi tutto lo spazzolamento delle quotazioni.

Il layer prodotto e' ``finnhub_news``: lista di dizionari gia' appiattiti, con
la stessa forma degli altri layer di notizie (titolo, fonte, data, url), piu'
``ticker`` quando la notizia riguarda un titolo preciso.
"""

import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from services.fetchers._store import latest_data, _data_lock, _mark_fresh
# Contatore condiviso del tetto Finnhub (60/min): stessa chiave dello
# spazzolamento quotazioni, quindi stesso budget da leggere e da alimentare.
from services.fetchers.financial import aggiorna_budget, budget_residuo
from services.financial_config import get_config

logger = logging.getLogger(__name__)

BASE = "https://finnhub.io/api/v1"

# I titoli della difesa piu' i tech piu' pesanti.
#
# All'inizio c'erano solo i sei della difesa, e produceva un buco preciso: il
# titolo che si muoveva di piu' era quasi sempre un tech, e per quello non
# esisteva **nessuna** notizia. Un modello che riceve otto notizie e un picco
# del 15% non coperto da nessuna di esse tende a costruire un nesso con quello
# che ha sottomano — e infatti l'ha fatto, legando Amazon a un articolo su
# Palantir. Il rimedio non e' una regola in piu' nel prompt: e' dargli la
# notizia che manca.
#
# Costo: una chiamata per titolo, ogni dieci minuti. Trascurabile sui 60/minuto.
TITOLI_SEGUITI = [
    "RTX", "LMT", "NOC", "GD", "BA", "PLTR",           # difesa
    "NVDA", "AMZN", "GOOGL", "MSFT", "AAPL", "META", "TSLA",  # i tech che muovono
]

# Modalita' deep_news (services.financial_config): i 20 titoli azionari del
# core di financial.py (le cripto non hanno company-news) piu' dieci pesi
# massimi di finanza, energia, industria e salute. 30 titoli in tutto.
TITOLI_DEEP = [
    "RTX", "LMT", "NOC", "GD", "BA", "PLTR",                          # difesa
    "NVDA", "AMD", "TSM", "INTC", "GOOGL", "AMZN", "MSFT",            # tech
    "AAPL", "TSLA", "META", "NFLX", "SMCI", "ARM", "ASML",            # tech
    "JPM", "GS", "XOM", "CVX", "CAT", "LLY", "UNH", "WMT", "AVGO", "ORCL",
]

# Sedi centrali dei titoli seguiti: ticker -> (lat, lng, "Citta', Stato/Paese").
#
# HQ pin = dove sta l'azienda, non dove accade il fatto — approssimazione
# dichiarata. Serve solo a dare alla notizia un punto sulla mappa piu' preciso
# del paese; il popup del frontend rende visibile l'approssimazione ("HQ: ...").
#
# Le banche di New York hanno un piccolo scarto l'una dall'altra (coordinate
# reali delle rispettive sedi a Manhattan): senza, sette spilli finirebbero
# impilati sullo stesso pixel.
HQ_TICKER = {
    # difesa
    "RTX":  (38.8816, -77.1043, "Arlington, VA"),
    "LMT":  (38.9847, -77.1200, "Bethesda, MD"),
    "NOC":  (38.8823, -77.1711, "Falls Church, VA"),
    "GD":   (38.9586, -77.3570, "Reston, VA"),
    "BA":   (38.8529, -77.0510, "Arlington, VA"),
    "PLTR": (39.7392, -104.9903, "Denver, CO"),
    "LHX":  (28.0836, -80.6081, "Melbourne, FL"),
    "HII":  (36.9788, -76.4284, "Newport News, VA"),
    # tech / semiconduttori
    "NVDA": (37.3708, -121.9673, "Santa Clara, CA"),
    "AMD":  (37.3894, -121.9640, "Santa Clara, CA"),
    "TSM":  (24.7736, 120.9967, "Hsinchu, Taiwan"),
    "INTC": (37.3875, -121.9636, "Santa Clara, CA"),
    "GOOGL": (37.4220, -122.0841, "Mountain View, CA"),
    "AMZN": (47.6151, -122.3394, "Seattle, WA"),
    "MSFT": (47.6423, -122.1368, "Redmond, WA"),
    "AAPL": (37.3349, -122.0090, "Cupertino, CA"),
    "TSLA": (30.2226, -97.6208, "Austin, TX"),
    "META": (37.4530, -122.1817, "Menlo Park, CA"),
    "NFLX": (37.2586, -121.9614, "Los Gatos, CA"),
    "SMCI": (37.3830, -121.9297, "San Jose, CA"),
    "ARM":  (52.2054, 0.1235, "Cambridge, UK"),
    "ASML": (51.4104, 5.4055, "Veldhoven, NL"),
    "AVGO": (37.4432, -122.1544, "Palo Alto, CA"),
    "QCOM": (32.8946, -117.1951, "San Diego, CA"),
    "MU":   (43.5644, -116.1697, "Boise, ID"),
    "TXN":  (32.9109, -96.7529, "Dallas, TX"),
    "ORCL": (30.2436, -97.7202, "Austin, TX"),
    "CRM":  (37.7897, -122.3972, "San Francisco, CA"),
    "IBM":  (41.1081, -73.7204, "Armonk, NY"),
    "ADBE": (37.3308, -121.8944, "San Jose, CA"),
    # finanza — tutte a Manhattan, ciascuna sulla propria sede
    "JPM":  (40.7557, -73.9754, "New York, NY"),   # 383 Madison Ave
    "GS":   (40.7145, -74.0139, "New York, NY"),   # 200 West St
    "MS":   (40.7601, -73.9847, "New York, NY"),   # 1585 Broadway
    "BAC":  (40.7550, -73.9845, "New York, NY"),   # One Bryant Park
    "WFC":  (40.7052, -74.0086, "New York, NY"),   # sede storica 420 Montgomery e' SF, ma il centro operativo quotato in lista e' NY: 150 E 42nd
    "C":    (40.7203, -74.0121, "New York, NY"),   # 388 Greenwich St
    "BLK":  (40.7527, -74.0012, "New York, NY"),   # 50 Hudson Yards
    "V":    (37.7935, -122.3969, "San Francisco, CA"),
    "MA":   (41.0409, -73.7146, "Purchase, NY"),
    # energia / industria
    "XOM":  (30.0733, -95.4433, "Spring, TX"),
    "CVX":  (29.7752, -95.5628, "Houston, TX"),
    "COP":  (29.7803, -95.5621, "Houston, TX"),
    "SLB":  (29.7376, -95.5580, "Houston, TX"),
    "OXY":  (29.7345, -95.4623, "Houston, TX"),
    "CAT":  (32.8709, -96.9433, "Irving, TX"),
    "DE":   (41.4933, -90.4990, "Moline, IL"),
    "HON":  (35.2226, -80.8460, "Charlotte, NC"),
    "GE":   (39.0916, -84.5062, "Cincinnati, OH"),
    # salute / consumo
    "LLY":  (39.7420, -86.1808, "Indianapolis, IN"),
    "JNJ":  (40.4980, -74.4440, "New Brunswick, NJ"),
    "PFE":  (40.7529, -74.0032, "New York, NY"),
    "UNH":  (44.9146, -93.4620, "Minnetonka, MN"),
    "WMT":  (36.3650, -94.2178, "Bentonville, AR"),
    "KO":   (33.7712, -84.3963, "Atlanta, GA"),
    "PEP":  (41.0378, -73.7130, "Purchase, NY"),
}

# Quante notizie tenere. Il flusso generale ne restituisce anche cento: senza un
# tetto il layer diventa il piu' pesante della piattaforma per nessun motivo.
MAX_GENERALI = 30
MAX_PER_TITOLO = 5
MAX_TOTALE = 60

_TIMEOUT = 8


def _chiama(percorso: str, parametri: dict):
    chiave = os.getenv("FINNHUB_API_KEY", "").strip()
    if not chiave:
        return None
    parametri = dict(parametri)
    parametri["token"] = chiave
    url = f"{BASE}{percorso}?{urllib.parse.urlencode(parametri)}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            # Anche questa spesa va nel contatore condiviso: X-Ratelimit-*
            # arriva su ogni risposta Finnhub, non solo sulle quotazioni.
            aggiorna_budget(r.headers)
            return json.loads(r.read().decode())
    except Exception as e:
        logger.debug("Finnhub news %s: %s", percorso, e)
        return None


# Nome dell'azienda per ticker: serve solo a decidere se una notizia restituita
# da /company-news riguarda davvero quel titolo (vedi _riguarda).
NOMI_TICKER = {
    "RTX": ("RTX", "RAYTHEON"), "LMT": ("LOCKHEED",), "NOC": ("NORTHROP",),
    "GD": ("GENERAL DYNAMICS",), "BA": ("BOEING",), "PLTR": ("PALANTIR",),
    "LHX": ("L3HARRIS", "L3 HARRIS"), "HII": ("HUNTINGTON INGALLS",),
    "NVDA": ("NVIDIA",), "AMD": ("ADVANCED MICRO",), "TSM": ("TSMC", "TAIWAN SEMICONDUCTOR"),
    "INTC": ("INTEL",), "GOOGL": ("GOOGLE", "ALPHABET"), "AMZN": ("AMAZON",),
    "MSFT": ("MICROSOFT",), "AAPL": ("APPLE",), "TSLA": ("TESLA",),
    "META": ("META PLATFORMS", "FACEBOOK", "INSTAGRAM"), "NFLX": ("NETFLIX",),
    "SMCI": ("SUPER MICRO",), "ARM": ("ARM HOLDINGS",), "ASML": ("ASML",),
    "AVGO": ("BROADCOM",), "QCOM": ("QUALCOMM",), "MU": ("MICRON",),
    "TXN": ("TEXAS INSTRUMENTS",), "ORCL": ("ORACLE",), "CRM": ("SALESFORCE",),
    "IBM": ("IBM", "INTERNATIONAL BUSINESS MACHINES"), "ADBE": ("ADOBE",),
    "JPM": ("JPMORGAN", "JP MORGAN"), "GS": ("GOLDMAN SACHS",), "MS": ("MORGAN STANLEY",),
    "BAC": ("BANK OF AMERICA",), "WFC": ("WELLS FARGO",), "C": ("CITIGROUP",),
    "BLK": ("BLACKROCK",), "V": ("VISA",), "MA": ("MASTERCARD",),
    "XOM": ("EXXON",), "CVX": ("CHEVRON",), "COP": ("CONOCOPHILLIPS",),
    "SLB": ("SCHLUMBERGER", "SLB"), "OXY": ("OCCIDENTAL",), "CAT": ("CATERPILLAR",),
    "DE": ("DEERE",), "HON": ("HONEYWELL",), "GE": ("GENERAL ELECTRIC",),
    "LLY": ("ELI LILLY", "LILLY"), "JNJ": ("JOHNSON & JOHNSON", "JOHNSON AND JOHNSON"),
    "PFE": ("PFIZER",), "UNH": ("UNITEDHEALTH",), "WMT": ("WALMART",),
    "KO": ("COCA-COLA", "COCA COLA"), "PEP": ("PEPSICO", "PEPSI"),
    "NOW": ("SERVICENOW",),
}


def _nomina(testo: str, termine: str) -> bool:
    """``termine`` compare in ``testo`` come parola intera (entrambi maiuscoli)?

    Serve il confine di parola, altrimenti "INTEL" prende "INTELLIGENCE" e
    "ARM" prende "ARMY". Il confine e' su lettere e cifre soltanto, cosi'
    ``$NVDA`` e ``NVIDIA'S`` restano riconosciuti.
    """
    return re.search(rf"(?<![A-Z0-9]){re.escape(termine)}(?![A-Z0-9])", testo) is not None


def _riguarda(voce: dict, ticker: str) -> bool:
    """La notizia riguarda davvero quel titolo?

    ``/company-news?symbol=NVDA`` non restituisce solo notizie su NVIDIA: il
    flusso contiene anche pezzi di mercato generale (la Fed, Oracle, IBM).
    Marcarli tutti col simbolo della chiamata metteva il badge NVDA su
    qualunque cosa (difetto 25).

    Vergilius (verifica finale N3): il primo rimedio si fidava del campo
    ``related``, ma su ``/company-news?symbol=X`` Finnhub ci mette **sempre**
    X, quindi rispondeva sempre si' e il ripiego sul testo non veniva mai
    raggiunto ("Berkshire Hathaway...", "Plug Power vs. Bloom Energy...",
    "These 3 Stocks Will 10x..." tutte marcate NVDA). Su questa rotta
    ``related`` non porta informazione: si guarda **solo** il testo. Il
    distintivo si attacca se titolo o sommario nominano il simbolo come
    parola intera (``NVDA``, ``$NVDA``) o il nome dell'azienda
    (``NOMI_TICKER``, con le varianti ovvie).
    """
    if not ticker:
        return False
    simbolo = ticker.upper()
    testo = f"{voce.get('headline') or ''} {voce.get('summary') or ''}".upper()

    # Il simbolo nudo vale solo da tre lettere in su: "C" (Citigroup), "V"
    # (Visa), "BA", "DE", "GS", "KO"... come parole intere compaiono in
    # qualunque testo inglese e rimetterebbero il distintivo ovunque.
    if len(simbolo) >= 3 and _nomina(testo, simbolo):
        return True
    if _nomina(testo, f"${simbolo}"):
        return True
    for nome in NOMI_TICKER.get(simbolo, ()):
        if _nomina(testo, nome):
            return True
    return False


def _normalizza(voce: dict, ticker: str | None = None):
    """Riduce una notizia alla forma che usano gli altri layer.

    Finnhub restituisce anche ``image``, ``id``, ``related`` e ``category``:
    campi che nessuno legge e che moltiplicati per sessanta voci pesano piu' del
    contenuto. Restano fuori.
    """
    titolo = (voce.get("headline") or "").strip()
    if not titolo:
        return None

    epoca = voce.get("datetime")
    try:
        quando = datetime.fromtimestamp(int(epoca), tz=timezone.utc).isoformat()
    except Exception:
        quando = None

    fuori = {
        "title": titolo,
        "source": (voce.get("source") or "Finnhub").strip(),
        "url": voce.get("url") or "",
        "published": quando,
        "summary": (voce.get("summary") or "").strip()[:400],
    }
    if ticker:
        fuori["ticker"] = ticker
        # HQ pin = dove sta l'azienda, non dove accade il fatto —
        # approssimazione dichiarata (il popup mostra "HQ: ...").
        sede = HQ_TICKER.get(ticker)
        if sede:
            fuori["lat"], fuori["lng"], fuori["hq"] = sede
    return fuori


def fetch_finnhub_news():
    """Riempie il layer ``finnhub_news``. Silenzioso se la chiave manca."""
    if not os.getenv("FINNHUB_API_KEY", "").strip():
        logger.debug("FINNHUB_API_KEY assente — niente notizie finanziarie.")
        return

    # Manopola runtime: deep_news allarga titoli e finestra, e rallenta il
    # passo per non mangiarsi il minuto. A manopola spenta i valori sono
    # esattamente quelli storici.
    try:
        deep = bool(get_config().get("deep_news"))
    except Exception:
        deep = False
    titoli = list(TITOLI_DEEP if deep else TITOLI_SEGUITI)
    giorni_finestra = 7 if deep else 3
    pausa_s = 1.0 if deep else 0.2
    max_per_titolo = 6 if deep else MAX_PER_TITOLO
    max_totale = 120 if deep else MAX_TOTALE

    raccolte: list[dict] = []
    viste: set[str] = set()

    def aggiungi(voci, ticker=None, tetto=MAX_GENERALI):
        n = 0
        for v in voci or []:
            if not isinstance(v, dict):
                continue
            # Il simbolo si attacca solo se la notizia e' davvero di quella
            # azienda: le notizie di mercato generale restano senza badge.
            pulita = _normalizza(v, ticker if ticker and _riguarda(v, ticker) else None)
            if not pulita:
                continue
            # Le notizie di settore ricompaiono su piu' titoli: dedotte per URL,
            # altrimenti lo stesso pezzo su Boeing arriva sei volte.
            chiave = pulita["url"] or pulita["title"]
            if chiave in viste:
                continue
            viste.add(chiave)
            raccolte.append(pulita)
            n += 1
            if n >= tetto:
                break

    generali = _chiama("/news", {"category": "general"})
    aggiungi(generali, tetto=MAX_GENERALI)

    oggi = datetime.now(timezone.utc).date()
    da = (oggi - timedelta(days=giorni_finestra)).isoformat()
    a = oggi.isoformat()

    # Guardia sul tetto condiviso (60/min, stessa chiave delle quotazioni):
    # se il minuto e' quasi esaurito si accorcia la lista dei titoli invece
    # di collezionare 429. Margine 8 lasciato agli altri fetcher.
    residuo = budget_residuo()
    if residuo is not None:
        disponibili = max(0, residuo - 8)
        if disponibili < len(titoli):
            logger.info(
                "Finnhub news: restano %d chiamate, titoli ridotti da %d a %d",
                residuo, len(titoli), disponibili,
            )
            titoli = titoli[:disponibili]

    for titolo in titoli:
        voci = _chiama("/company-news", {"symbol": titolo, "from": da, "to": a})
        aggiungi(voci, ticker=titolo, tetto=max_per_titolo)
        # Il tetto del piano gratuito e' al minuto: una pausa breve fra i titoli
        # evita di consumarlo tutto in un lampo insieme alle quotazioni.
        time.sleep(pausa_s)

    raccolte.sort(key=lambda v: v.get("published") or "", reverse=True)
    raccolte = raccolte[:max_totale]

    with _data_lock:
        latest_data["finnhub_news"] = raccolte
    _mark_fresh("finnhub_news")

    con_titolo = sum(1 for v in raccolte if v.get("ticker"))
    logger.info(
        "Finnhub news: %d totali (%d legate a un titolo della difesa)",
        len(raccolte), con_titolo,
    )
