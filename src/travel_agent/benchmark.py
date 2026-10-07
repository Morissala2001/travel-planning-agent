"""The measurements quoted in the README, reproducible with `travel-agent benchmark`.

1. The budget loop with and without putting activities back after a cheaper hotel, on a grid of requests.
2. The hotel search with wishes written in English, French and Russian.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pandas as pd

from .data import cities
from .planner import Request, TravelAgent
from .tools import Encoder, HotelSearch

WISHES_FILE = Path(__file__).resolve().parents[2] / "eval" / "hotel_wishes.json"
GRID_WISHES = ["un hôtel pour la famille avec une piscine, et des visites dans la ville",
               "le grand luxe, un palace avec spa",
               "je veux faire la fête et sortir le soir"]
GRID_BUDGETS = range(500, 1500, 100)
GRID_DAYS = ["2026-07-08", "2026-07-22", "2026-08-05", "2026-08-12", "2026-08-19"]


def grid(conn: sqlite3.Connection) -> list[Request]:
    """15 cities x 3 wishes x 10 budgets x 5 days = 2,250 requests, 4 nights, 2 travellers."""
    return [Request(city, day, 4, 2, budget, wish)
            for city in cities(conn) for wish in GRID_WISHES for budget in GRID_BUDGETS for day in GRID_DAYS]


def loop_report(conn: sqlite3.Connection, search: HotelSearch, requests: list[Request]) -> pd.DataFrame:
    rows = []
    for restore in (False, True):
        agent = TravelAgent(conn, search, restore_activities=restore)
        start = time.perf_counter()
        plans = [agent.plan(r) for r in requests]
        seconds = (time.perf_counter() - start) / len(requests)
        trips = [p.trip for p in plans if p.trip is not None]
        changed = [p for p in plans if p.trip is not None and any(n.kind == "changed_hotel" for n in p.notes)]
        rows.append({
            "put activities back": "yes" if restore else "no (original)",
            "requests": len(requests),
            "trip found": len(trips) / len(requests),
            "activities kept (all trips)": sum(len(t.activities) for t in trips) / len(trips),
            "trips with a cheaper hotel": len(changed),
            "activities kept (cheaper hotel)": sum(len(p.trip.activities) for p in changed) / max(len(changed), 1),
            "unused budget (cheaper hotel)": sum(p.request.budget - p.trip.total for p in changed) / max(len(changed), 1),
            "ms per request": 1000 * seconds,
        })
    return pd.DataFrame(rows)


def search_report(search: HotelSearch, encoder: Encoder, wishes_file: Path = WISHES_FILE) -> pd.DataFrame:
    spec = json.loads(wishes_file.read_text(encoding="utf-8"))
    brochures = search.brochures
    relevant = lambda i, keys: any(k in brochures.loc[i, "summary"].lower() for k in keys)  # noqa: E731
    rows = []
    for lang in ("fr", "en", "ru"):
        hits = agree = n = 0
        for wish in spec["wishes"]:
            for city in sorted(brochures["city"].unique()):
                rows_city = brochures.index[brochures["city"] == city]
                if not any(relevant(i, wish["keywords"]) for i in rows_city):
                    continue  # no such hotel in this city: nothing to find
                n += 1
                top = search.search(city, wish[lang], k=1)["hotel"].iloc[0]
                top_fr = search.search(city, wish["fr"], k=1)["hotel"].iloc[0]
                index = rows_city[brochures.loc[rows_city, "hotel"] == top][0]
                hits += relevant(index, wish["keywords"])
                agree += top == top_fr
        neg = spec["negation"]
        tops = [search.search(city, neg[lang], k=1)["hotel"].iloc[0] for city in sorted(brochures["city"].unique())]
        family_first = sum(relevant(brochures.index[(brochures["city"] == c) & (brochures["hotel"] == h)][0], neg["keywords"])
                           for c, h in zip(sorted(brochures["city"].unique()), tops))
        rows.append({"language": lang, "searches": n, "top hotel matches the wish": hits / n,
                     "same top hotel as in French": agree / n,
                     "'without children': family hotel first": family_first / len(tops)})
    return pd.DataFrame(rows)


def run(conn: sqlite3.Connection, brochures: pd.DataFrame, encoder: Encoder) -> None:
    search = HotelSearch(brochures, encoder)
    with pd.option_context("display.width", 200, "display.max_columns", 20, "display.float_format", "{:.3f}".format):
        print("Budget loop, 2,250 requests (15 cities x 3 wishes x 10 budgets x 5 days, 4 nights, 2 travellers)")
        print(loop_report(conn, search, grid(conn)).T.to_string(header=False), end="\n\n")
        print("Hotel search by language")
        print(search_report(search, encoder).to_string(index=False))
