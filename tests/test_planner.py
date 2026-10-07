"""The budget loop on a tiny world: flight of the 12th = 120, Hôtel Familia = 100 a night, activities 0 + 10 + 20 + 40."""

import sqlite3

import pytest
from conftest import make_db

from travel_agent.planner import Request, TravelAgent, nearby_days, price_trip

FAMILY = "un hôtel pour les familles avec enfants et une piscine"


def ask(conn, search, budget, day="2026-08-12", restore=True, wish=FAMILY):
    return TravelAgent(conn, search, restore_activities=restore).plan(Request("Madrid", day, 4, 2, budget, wish))


def kinds(plan):
    return [n.kind for n in plan.notes]


def names(trip):
    return [a["name"] for a in trip.activities]


def test_price_is_per_person_hotel_included():
    assert price_trip({"price": 120}, {"price_per_night": 100}, [{"price": 10}, {"price": 20}], 4) == 550.0


def test_nearby_days_go_from_the_closest():
    assert nearby_days("2026-08-12") == ["2026-08-11", "2026-08-13", "2026-08-10", "2026-08-14"]
    assert nearby_days("2026-08-31", spread=1) == ["2026-08-30", "2026-09-01"]


def test_everything_fits_and_a_cheaper_day_with_the_same_programme_is_pointed_out(conn, search):
    plan = ask(conn, search, 600)
    assert plan.trip.total == 590 and plan.trip.hotel["hotel"] == "Hôtel Familia" and len(plan.trip.activities) == 4
    assert kinds(plan) == ["other_day_cheaper"]
    assert plan.notes[0].details == {"day": "2026-08-10", "total": 560.0, "saving": 30.0}


def test_the_dearest_paid_activity_goes_first_and_a_day_keeping_more_is_pointed_out(conn, search):
    plan = ask(conn, search, 560)
    assert plan.trip.total == 550 and "Flamenco" not in names(plan.trip)
    assert kinds(plan) == ["removed_activity", "other_day_more_activities"]
    assert plan.notes[1].details == {"day": "2026-08-10", "kept": 4, "instead_of": 3, "total": 560.0}


def test_the_agent_never_moves_the_dates_by_itself(conn, search):
    for budget in (560, 600, 900):
        assert ask(conn, search, budget).trip.day == "2026-08-12"


def test_cheaper_hotel_then_activities_put_back(conn, search):
    plan = ask(conn, search, 500)
    assert kinds(plan)[:5] == ["removed_activity"] * 3 + ["changed_hotel", "restored_activities"]
    assert plan.trip.hotel["hotel"] == "Hostal Barato"
    assert len(plan.trip.activities) == 4 and plan.trip.total == 120 + 200 + 70
    assert plan.notes[4].details == {"names": ["Temple de Debod", "Musée du Prado", "Flamenco"], "price": 70.0}


def test_original_behaviour_keeps_the_bare_programme_and_never_drops_a_free_activity(conn, search):
    plan = ask(conn, search, 500, restore=False)
    assert plan.trip.hotel["hotel"] == "Hostal Barato" and plan.trip.total == 320
    assert names(plan.trip) == ["Parc du Retiro"]  # the free one is never given up
    assert "restored_activities" not in kinds(plan)


def test_only_cheaper_hotels_are_tried_as_fallbacks(conn, search):
    plan = ask(conn, search, 500)
    assert "Palacio Real" not in {a.hotel for a in plan.attempts}  # dearer than the first choice


def test_restored_activities_never_break_the_budget(conn, search):
    for budget in range(300, 700, 5):
        plan = ask(conn, search, budget)
        for trip in [plan.trip, *plan.alternatives]:
            if trip is not None:
                assert trip.total <= budget


def test_nothing_fits_on_the_day_but_a_neighbour_does(conn, search):
    plan = ask(conn, search, 300)
    assert plan.trip is None
    assert kinds(plan)[-2:] == ["gave_up", "other_day_possible"]
    assert plan.notes[-1].details == {"day": "2026-08-11", "total": 295.0}


def test_impossible_everywhere_promises_nothing(conn, search):
    plan = ask(conn, search, 100)
    assert plan.trip is None and plan.alternatives == []
    assert kinds(plan)[-1] == "gave_up" and "other_day_possible" not in kinds(plan)


def test_no_flight_that_day(conn, search):
    plan = ask(conn, search, 900, day="2026-09-20")
    assert plan.trip is None and kinds(plan) == ["no_flight_or_hotel"]


@pytest.mark.parametrize("neighbour_price, expected", [(540, []), (500, ["other_day_cheaper"])])
def test_same_programme_is_only_claimed_when_true(tmp_path, search, neighbour_price, expected):
    """Regression: the original said 'the same programme for less' about a day that had kept one activity fewer."""
    flights = [("R12", "Nice", "Madrid", "2026-08-12", "09:15", 2.0, 520.0, 9),
               ("R13", "Nice", "Madrid", "2026-08-13", "09:15", 2.0, float(neighbour_price), 9)]
    conn = sqlite3.connect(make_db(tmp_path / "t.db", flights))
    plan = ask(conn, search, 1000)
    assert plan.trip.total == 990 and len(plan.trip.activities) == 4
    neighbour = plan.alternatives[0]
    assert neighbour.total < plan.trip.total - 10  # cheaper by more than 10 euros in both cases...
    assert kinds(plan) == expected  # ...but with 540 it kept 3 activities instead of 4: not the same programme
