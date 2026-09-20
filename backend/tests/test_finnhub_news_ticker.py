"""Vergilius (verifica finale N3): il distintivo del ticker sulle notizie Finnhub.

``/company-news?symbol=X`` mette SEMPRE X nel campo ``related``, quindi quel
campo non distingue nulla su questa rotta. Il distintivo si attacca solo se
titolo o sommario nominano il simbolo (parola intera, anche ``$NVDA``) o il
nome dell'azienda.

I casi "NON deve" sono i titoli veri raccolti nel referto del 20 settembre.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.fetchers.finnhub_news import _riguarda  # noqa: E402


def voce(headline: str, summary: str = "", related: str = "NVDA") -> dict:
    return {"headline": headline, "summary": summary, "related": related}


# I titoli veri che il referto ha trovato marcati NVDA senza alcun rapporto.
SENZA_DISTINTIVO = [
    "Berkshire Hathaway's CEO Now Has to Consult Howard Buffett Before Buying Back Stock",
    "Plug Power vs. Bloom Energy: Which Hydrogen-Adjacent Stock Actually Has a Real Business Model?",
    "Prediction: These 3 Stocks Will 10x in the Next 10 Years",
    "The Stock Market Has Been Sending a Quiet Warning Signal for Years",
    "This Overlooked Pipeline Stock Just Became a Rival's Joint-Venture Partner",
    "World leaders return to UN headquarters",
]


@pytest.mark.parametrize("titolo", SENZA_DISTINTIVO)
def test_titoli_generici_non_prendono_nvda(titolo):
    # related = "NVDA" come lo manda davvero Finnhub su /company-news?symbol=NVDA
    assert _riguarda(voce(titolo), "NVDA") is False


def test_greci_non_prendono_jpm():
    assert _riguarda(voce("Why Greek banks deserve your attention", related="JPM"), "JPM") is False


@pytest.mark.parametrize(
    "titolo, ticker",
    [
        ("Nvidia unveils its next data-center GPU", "NVDA"),
        ("NVDA slips after guidance", "NVDA"),
        ("Analysts still like $NVDA into year end", "NVDA"),
        ("NVIDIA's margins keep expanding", "NVDA"),
        ("JPMorgan lifts its target", "JPM"),
        ("JP Morgan lifts its target", "JPM"),
        ("Lockheed wins a new contract", "LMT"),
        ("Coca-Cola raises its dividend", "KO"),
    ],
)
def test_nome_o_simbolo_nel_testo_prende_il_distintivo(titolo, ticker):
    assert _riguarda(voce(titolo, related=ticker), ticker) is True


def test_nome_nel_sommario_basta():
    v = voce("Chip demand keeps climbing", summary="Nvidia said orders doubled.", related="NVDA")
    assert _riguarda(v, "NVDA") is True


def test_related_da_solo_non_basta_piu():
    """Il cuore del difetto N3: related dice NVDA ma il testo non la nomina."""
    v = voce("Oracle and IBM report", related="NVDA,ORCL,IBM")
    assert _riguarda(v, "NVDA") is False


@pytest.mark.parametrize(
    "titolo, ticker",
    [
        # Confini di parola: prefissi/suffissi non devono contare.
        ("Military intelligence report released", "INTC"),   # INTEL dentro INTELLIGENCE
        ("The army expands its drone fleet", "ARM"),          # ARM dentro ARMY
        # Simboli corti: da soli non valgono mai (C = Citigroup, V = Visa, BA...).
        ("Vitamin C sales climb", "C"),
        ("The V shaped recovery is over", "V"),
        ("Flight BA 117 diverted", "BA"),
    ],
)
def test_falsi_positivi_di_confine_e_simboli_corti(titolo, ticker):
    assert _riguarda(voce(titolo, related=ticker), ticker) is False


def test_simbolo_corto_col_dollaro_vale():
    assert _riguarda(voce("Buying $C here", related="C"), "C") is True
