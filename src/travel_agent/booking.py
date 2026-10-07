"""Booking: the only action of the agent that changes the world, so it is guarded."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from .planner import Trip


@dataclass(frozen=True)
class Booking:
    status: str  # nothing_to_book, needs_confirmation, booked, already_booked, no_seats
    trip: Trip | None
    client: str
    reservation_id: int | None = None

    @property
    def done(self) -> bool:
        return self.status == "booked"


class _Refused(Exception):
    def __init__(self, status: str):
        self.status = status


def book(conn: sqlite3.Connection, trip: Trip | None, client: str, confirm: bool = False) -> Booking:
    """Record the trip in the `reservations` table, but only once the traveller has confirmed.

    Without `confirm=True` nothing is written: the result only says what would be booked. With it, the seats are
    taken from the flight and the reservation is written in one transaction, so both happen or neither does. The
    booking is refused when the flight has no longer enough seats, or when the same traveller already booked the
    same trip (a second click on the confirm button must not book twice).
    """
    if trip is None:
        return Booking("nothing_to_book", None, client)
    if not confirm:  # THE GUARD: as long as the traveller has not said yes, nothing is written
        return Booking("needs_confirmation", trip, client)

    r = trip.request
    try:
        with conn:  # commits on success, rolls back if anything below fails or is refused
            taken = conn.execute("UPDATE vols SET places_restantes = places_restantes - ? "
                                 "WHERE id = ? AND places_restantes >= ?",
                                 (int(r.travellers), int(trip.flight["id"]), int(r.travellers))).rowcount
            if not taken:
                raise _Refused("no_seats")
            duplicate = conn.execute("SELECT 1 FROM reservations WHERE client = ? AND destination = ? AND date_depart = ? "
                                     "AND nuits = ? AND voyageurs = ? AND vol = ? AND hotel = ?",
                                     (client, r.city, r.day, int(r.nights), int(r.travellers),
                                      str(trip.flight["flight"]), trip.hotel["hotel"])).fetchone()
            if duplicate:
                raise _Refused("already_booked")
            cursor = conn.execute(
                "INSERT INTO reservations (client, destination, date_depart, nuits, voyageurs, vol, hotel, "
                "activites, prix_total, reservee_le) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (client, r.city, r.day, int(r.nights), int(r.travellers), str(trip.flight["flight"]),
                 trip.hotel["hotel"], ", ".join(a["name"] for a in trip.activities), float(trip.total_for_all),
                 datetime.now().strftime("%Y-%m-%d %H:%M")))
    except _Refused as refused:
        return Booking(refused.status, trip, client)
    return Booking("booked", trip, client, cursor.lastrowid)
