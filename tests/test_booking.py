import sqlite3

from conftest import make_db

from travel_agent.booking import book
from travel_agent.planner import Request, TravelAgent

FAMILY = "un hôtel pour les familles avec enfants et une piscine"


def plan_trip(conn, search, travellers=2):
    return TravelAgent(conn, search).plan(Request("Madrid", "2026-08-12", 4, travellers, 900, FAMILY)).trip


def reservations(conn):
    return conn.execute("SELECT client, destination, date_depart, nuits, voyageurs, vol, hotel, prix_total "
                        "FROM reservations").fetchall()


def seats(conn, flight="T12"):
    return conn.execute("SELECT places_restantes FROM vols WHERE numero = ?", (flight,)).fetchone()[0]


def test_without_confirmation_nothing_is_written(conn, search):
    result = book(conn, plan_trip(conn, search), "Ada")
    assert result.status == "needs_confirmation" and not result.done
    assert reservations(conn) == [] and seats(conn) == 9


def test_nothing_to_book_without_a_trip(conn):
    assert book(conn, None, "Ada", confirm=True).status == "nothing_to_book"
    assert reservations(conn) == []


def test_confirmed_booking_records_the_trip_and_takes_the_seats(conn, search):
    trip = plan_trip(conn, search)
    result = book(conn, trip, "Ada", confirm=True)
    assert result.done and result.reservation_id == 1
    assert reservations(conn) == [("Ada", "Madrid", "2026-08-12", 4, 2, "T12", "Hôtel Familia", trip.total * 2)]
    assert seats(conn) == 7


def test_a_second_click_does_not_book_twice(conn, search):
    trip = plan_trip(conn, search)
    book(conn, trip, "Ada", confirm=True)
    again = book(conn, trip, "Ada", confirm=True)
    assert again.status == "already_booked"
    assert len(reservations(conn)) == 1 and seats(conn) == 7  # the seats taken by the refused attempt were given back
    assert book(conn, trip, "Grace", confirm=True).done  # another traveller may book the same trip


def test_a_full_flight_is_refused_and_nothing_is_written(tmp_path, search):
    conn = sqlite3.connect(make_db(tmp_path / "t.db", [("T12", "Nice", "Madrid", "2026-08-12", "09:15", 2.0, 120.0, 2)]))
    trip = plan_trip(conn, search)
    conn.execute("UPDATE vols SET places_restantes = 1")  # someone else booked in the meantime
    conn.commit()
    assert book(conn, trip, "Ada", confirm=True).status == "no_seats"
    assert reservations(conn) == [] and seats(conn) == 1


def test_a_booking_survives_a_new_connection(db, search):
    conn = sqlite3.connect(db)
    book(conn, plan_trip(conn, search), "Ada", confirm=True)
    conn.close()
    assert len(reservations(sqlite3.connect(db))) == 1  # committed, not left pending
