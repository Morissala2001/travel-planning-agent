"""The agent: it composes a trip with its tools, gives things up when the budget is short, and explains what it did.

An agent is a loop, not a language model: set a goal, call tools, check the result against the goal, correct, and
start again. No language model is used here, so every sentence of the explanation comes from numbers the code
computed and cannot be invented.

Every price is per person, the hotel included: the budget is a budget per person.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

import pandas as pd

from .tools import HotelSearch, find_activities, find_flights

MIN_SAVING = 10  # euros per person: a neighbouring day cheaper by less than this is not worth mentioning
MAX_STEPS = 30  # safety net against an endless loop; real searches need a dozen steps at most


@dataclass(frozen=True)
class Request:
    city: str  # as written in the database, e.g. "Barcelone"
    day: str  # departure day, YYYY-MM-DD
    nights: int
    travellers: int
    budget: float  # per person, everything included
    wish: str  # what the traveller is looking for, in their own words and language


@dataclass
class Trip:
    request: Request  # its `day` is the departure day of this trip
    flight: dict
    hotel: dict
    activities: list[dict]
    total: float  # per person

    @property
    def day(self) -> str:
        return self.request.day

    @property
    def total_for_all(self) -> float:
        return self.total * self.request.travellers

    def same_programme(self, other: Trip) -> bool:
        """Same hotel and same activities: only the flight differs."""
        return (self.hotel["hotel"] == other.hotel["hotel"]
                and [a["name"] for a in self.activities] == [a["name"] for a in other.activities])


@dataclass(frozen=True)
class Note:
    """One line of the agent's log, as data: `render.note_text` writes it in the traveller's language."""

    kind: str  # removed_activity, changed_hotel, restored_activities, gave_up, no_flight_or_hotel,
    #            other_day_possible, other_day_more_activities, other_day_cheaper
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Attempt:
    """One combination the agent priced, to show it searching instead of guessing."""

    day: str
    hotel: str
    flight_price: float
    hotel_price: float  # for all the nights
    activities_price: float
    total: float
    budget: float

    @property
    def fits(self) -> bool:
        return self.total <= self.budget


@dataclass
class Plan:
    request: Request
    trip: Trip | None  # always for the requested day: the agent never moves the dates by itself
    notes: list[Note]
    attempts: list[Attempt]
    alternatives: list[Trip]  # the trips that fit on the neighbouring days


def price_trip(flight: dict, hotel: dict, activities: list[dict], nights: int) -> float:
    """Total price of a trip, per person."""
    return float(flight["price"] + hotel["price_per_night"] * nights + sum(a["price"] for a in activities))


def nearby_days(day: str, spread: int = 2) -> list[str]:
    """The other days to explore around `day`, closest first: the day before, the day after, and so on."""
    start = date.fromisoformat(day)
    return [(start + timedelta(days=sign * shift)).isoformat() for shift in range(1, spread + 1) for sign in (-1, 1)]


class TravelAgent:
    """Composes the best trip it can for a request, with three tools: flights, activities and hotels.

    restore_activities: after stepping down to a cheaper hotel, put back the activities given up earlier that now
    fit in the budget (cheapest first). Without it, the agent keeps the bare programme it had to accept for the
    dearer hotel, and may leave a large part of the budget unused.
    """

    def __init__(self, conn: sqlite3.Connection, hotels: HotelSearch, restore_activities: bool = True,
                 spread: int = 2, k_hotels: int = 3):
        self.conn = conn
        self.hotels = hotels
        self.restore_activities = restore_activities
        self.spread = spread
        self.k_hotels = k_hotels

    def plan_day(self, request: Request) -> tuple[Trip | None, list[Note], list[Attempt]]:
        """The best trip for ONE departure day, or None if nothing fits the budget."""
        flights = find_flights(self.conn, request.city, request.day, request.travellers)
        hotels = self.hotels.search(request.city, request.wish, self.k_hotels)
        activities = find_activities(self.conn, request.city).to_dict("records")
        if flights.empty or hotels.empty:
            return None, [Note("no_flight_or_hotel", {"day": request.day})], []

        flight = flights.iloc[0].to_dict()  # the cheapest flight
        kept = list(activities)  # every activity, to start with
        notes: list[Note] = []
        attempts: list[Attempt] = []

        # The order in which hotels are tried: the most relevant first, then only those that are really cheaper
        # than it, from the dearest to the cheapest, to step down gently.
        first_price = hotels.iloc[0]["price_per_night"]
        fallbacks = [j for j in range(1, len(hotels)) if hotels.iloc[j]["price_per_night"] < first_price]
        order = [0] + sorted(fallbacks, key=lambda j: hotels.iloc[j]["price_per_night"], reverse=True)
        position = 0

        for _ in range(MAX_STEPS):
            hotel = hotels.iloc[order[position]].to_dict()
            total = price_trip(flight, hotel, kept, request.nights)
            attempts.append(Attempt(request.day, hotel["hotel"], flight["price"],
                                    hotel["price_per_night"] * request.nights,
                                    sum(a["price"] for a in kept), total, request.budget))
            if total <= request.budget:
                return Trip(request, flight, hotel, kept, total), notes, attempts

            paid = [a for a in kept if a["price"] > 0]  # removing a free activity would save nothing
            if paid:  # first fallback: give up the dearest activity, and go back to the best hotel
                dearest = max(paid, key=lambda a: a["price"])
                kept = [a for a in kept if a is not dearest]
                position = 0
                notes.append(Note("removed_activity", {"name": dearest["name"], "price": dearest["price"]}))
            elif position + 1 < len(order):  # second fallback: step down to the next cheaper hotel
                position += 1
                cheaper = hotels.iloc[order[position]].to_dict()
                notes.append(Note("changed_hotel", {"old": hotel["hotel"], "new": cheaper["hotel"]}))
                if self.restore_activities:
                    kept, restored = _restore(activities, kept, flight, cheaper, request)
                    if restored:
                        notes.append(Note("restored_activities", {"names": [a["name"] for a in restored],
                                                                  "price": sum(a["price"] for a in restored)}))
            else:  # nothing left to give up
                break
        notes.append(Note("gave_up", {"day": request.day}))
        return None, notes, attempts

    def plan(self, request: Request) -> Plan:
        """The trip for the requested day, plus what the agent noticed on the neighbouring days.

        Hotels and activities do not change from one day to the next, the flight price does. The agent compares
        first the number of activities kept and only then the price: since it stops as soon as it fits, every
        trip ends just under the budget, and comparing totals alone would show almost nothing.
        """
        trip, notes, attempts = self.plan_day(request)
        alternatives = []
        for other_day in nearby_days(request.day, self.spread):
            candidate, _, tried = self.plan_day(replace(request, day=other_day))
            attempts += tried
            if candidate is not None:
                alternatives.append(candidate)

        if alternatives and trip is None:  # nothing fits on the requested day: point to the cheapest day that works
            fallback = min(alternatives, key=lambda t: t.total)
            notes.append(Note("other_day_possible", {"day": fallback.day, "total": fallback.total}))
        elif alternatives:
            more = [t for t in alternatives if len(t.activities) > len(trip.activities)]
            # "The same programme for less" is only said when it is true: same hotel and same activities.
            same = [t for t in alternatives if t.same_programme(trip) and trip.total - t.total >= MIN_SAVING]
            if more:
                best = max(more, key=lambda t: (len(t.activities), -t.total))
                notes.append(Note("other_day_more_activities", {"day": best.day, "kept": len(best.activities),
                                                                "instead_of": len(trip.activities), "total": best.total}))
            elif same:
                best = min(same, key=lambda t: t.total)
                notes.append(Note("other_day_cheaper", {"day": best.day, "total": best.total,
                                                        "saving": trip.total - best.total}))
        return Plan(request, trip, notes, attempts, alternatives)

    def consulted(self, request: Request) -> tuple[pd.DataFrame, pd.DataFrame]:
        """What the agent looked at for the requested day: the flights and the closest hotels."""
        return (find_flights(self.conn, request.city, request.day, request.travellers),
                self.hotels.search(request.city, request.wish, self.k_hotels))


def _restore(activities: list[dict], kept: list[dict], flight: dict, hotel: dict,
             request: Request) -> tuple[list[dict], list[dict]]:
    """Put back the given-up activities that fit in what the cheaper hotel leaves of the budget, cheapest first."""
    left = request.budget - price_trip(flight, hotel, kept, request.nights)
    kept_ids = {id(a) for a in kept}
    restored = []
    for activity in sorted((a for a in activities if id(a) not in kept_ids), key=lambda a: a["price"]):
        if activity["price"] <= left:
            restored.append(activity)
            left -= activity["price"]
    keep = kept_ids | {id(a) for a in restored}
    return [a for a in activities if id(a) in keep], restored
