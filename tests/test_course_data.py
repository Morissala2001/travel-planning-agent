"""Checks on the real data in data/. The slow ones load the real encoder and reproduce the original notebook's results."""

import os

import pytest

from travel_agent.data import DEFAULT_BROCHURES, DEFAULT_DB, cities, connect, load_brochures
from travel_agent.planner import Request, TravelAgent

pytestmark = pytest.mark.skipif(not DEFAULT_DB.exists() or not DEFAULT_BROCHURES.exists(), reason="no data in data/")
slow = pytest.mark.skipif(os.environ.get("TRAVEL_AGENT_RUN_SLOW") != "1", reason="set TRAVEL_AGENT_RUN_SLOW=1 to run")
FAMILY = "un hôtel pour la famille avec une piscine, et des visites dans la ville"
PALACE = "le grand luxe, un palace avec spa"


def test_the_shipped_database_is_complete_and_has_no_booking():
    conn = connect()
    assert len(cities(conn)) == 15
    assert conn.execute("SELECT COUNT(*) FROM vols").fetchone()[0] == 7438
    assert conn.execute("SELECT COUNT(*) FROM activites").fetchone()[0] == 120
    assert conn.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 0


def test_every_brochure_is_parsed():
    brochures = load_brochures()
    assert len(brochures) == 135 and set(brochures["city"]) == set(cities(connect()))
    assert brochures.groupby("city").size().eq(9).all()
    assert brochures["price_per_night"].notna().all() and brochures["rating"].notna().all()
    assert (brochures["summary"].str.len() < brochures["text"].str.len()).all()


@pytest.fixture(scope="module")
def search():
    from travel_agent.tools import HotelSearch, load_encoder

    return HotelSearch(load_brochures(), load_encoder())


def plan(search, restore=False, **changes):
    values = {"city": "Barcelone", "day": "2026-08-12", "nights": 4, "travellers": 2, "budget": 750, "wish": FAMILY}
    return TravelAgent(connect(), search, restore_activities=restore).plan(Request(**(values | changes)))


@pytest.mark.slow
@slow
@pytest.mark.parametrize("restore", [False, True])
def test_the_notebook_trip_is_reproduced(search, restore):
    p = plan(search, restore)
    assert (p.trip.hotel["hotel"], p.trip.flight["flight"], p.trip.total, len(p.trip.activities)) == \
        ("Casa Bellavista", "W67507", 732.0, 6)
    assert [n.kind for n in p.notes] == ["removed_activity", "removed_activity", "other_day_more_activities"]
    assert p.notes[2].details == {"day": "2026-08-10", "kept": 7, "instead_of": 6, "total": 736.0}


@pytest.mark.slow
@slow
@pytest.mark.parametrize("budget, fallback", [(660, [{"day": "2026-08-10", "total": 648.0}]), (200, [])])
def test_the_notebook_dead_ends_are_reproduced(search, budget, fallback):
    p = plan(search, budget=budget)
    assert p.trip is None
    assert [n.details for n in p.notes if n.kind == "other_day_possible"] == fallback


@pytest.mark.slow
@slow
def test_the_palace_request_gets_its_activities_back(search):
    original = plan(search, budget=1100, wish=PALACE).trip
    restored = plan(search, restore=True, budget=1100, wish=PALACE).trip
    assert (original.hotel["hotel"], original.total, len(original.activities)) == ("Résidence Doria", 881.0, 3)
    assert restored.hotel["hotel"] == "Résidence Doria" and len(restored.activities) == 8 and restored.total <= 1100
