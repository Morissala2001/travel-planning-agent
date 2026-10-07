"""Turning the agent's results into sentences, in English, French or Russian. Only numbers computed by the agent go in."""

from __future__ import annotations

from .booking import Booking
from .i18n import city_name, count, day_label, money, number, origin_name, t
from .planner import Attempt, Note, Plan, Trip


def note_text(note: Note, lang: str) -> str:
    """One line of the agent's log."""
    d = note.details
    if note.kind == "removed_activity":
        return t("removed_activity", lang, name=d["name"], price=money(d["price"], lang))
    if note.kind == "changed_hotel":
        return t("changed_hotel", lang, old=d["old"], new=d["new"])
    if note.kind == "restored_activities":
        names = ", ".join(f"« {n} »" if lang == "fr" else f"«{n}»" if lang == "ru" else f"“{n}”" for n in d["names"])
        return t("restored_activities", lang, names=names, price=money(d["price"], lang))
    if note.kind in ("gave_up", "no_flight_or_hotel"):
        return t(note.kind, lang, day=day_label(d["day"], lang))
    if note.kind == "other_day_possible":
        return t(note.kind, lang, day=day_label(d["day"], lang), total=money(d["total"], lang))
    if note.kind == "other_day_more_activities":
        return t(note.kind, lang, day=day_label(d["day"], lang), kept=count(d["kept"], "activity", lang),
                 instead_of=d["instead_of"], total=money(d["total"], lang))
    if note.kind == "other_day_cheaper":
        return t(note.kind, lang, day=day_label(d["day"], lang), total=money(d["total"], lang),
                 saving=money(d["saving"], lang))
    raise ValueError(f"Unknown note: {note.kind}")


def log_lines(plan: Plan, lang: str) -> list[str]:
    return [note_text(n, lang) for n in plan.notes]


def summary(plan: Plan, lang: str) -> str:
    """The proposal in a short paragraph, written without any language model: nothing in it can be invented."""
    trip = plan.trip
    if trip is None:
        return " ".join([t("summary_nothing", lang), *log_lines(plan, lang), t("hint_nothing", lang)])
    f, h = trip.flight, trip.hotel
    sentences = [
        t("summary_flight", lang, flight=f["flight"], origin=origin_name(f["origin"], lang), day=day_label(trip.day, lang),
          time=f["departure_time"], hours=number(f["hours"], lang), price=money(f["price"], lang)),
        t("summary_hotel", lang, hotel=h["hotel"], nights=count(trip.request.nights, "night", lang),
          price=money(h["price_per_night"], lang)),
        t("summary_activities", lang, names=", ".join(a["name"] for a in trip.activities))
        if trip.activities else t("summary_no_activity", lang),
        t("summary_total", lang, total=money(trip.total, lang), budget=money(trip.request.budget, lang)),
    ]
    return " ".join(sentences + log_lines(plan, lang))


def booking_text(booking: Booking, lang: str) -> str:
    """What happened when booking, in plain words."""
    trip = booking.trip
    if booking.status == "nothing_to_book":
        return t("nothing_to_book", lang)
    r = trip.request
    values = {"client": booking.client, "city": city_name(r.city, lang), "nights": count(r.nights, "night", lang),
              "total": money(trip.total, lang), "total_all": money(trip.total_for_all, lang),
              "flight": trip.flight["flight"], "seats": count(r.travellers, "seat", lang)}
    return t(booking.status, lang, **values)


def verdict(attempt: Attempt, lang: str) -> str:
    return t("fits", lang) if attempt.fits else t("over", lang, amount=money(attempt.total - attempt.budget, lang))


def attempt_line(attempt: Attempt, lang: str) -> str:
    """One priced combination, as the original version printed them: flight + hotel + activities = total."""
    return (f"{day_label(attempt.day, lang):>12}  {attempt.hotel[:22]:22s} {money(attempt.flight_price, lang):>6} + "
            f"{money(attempt.hotel_price, lang):>7} + {money(attempt.activities_price, lang):>6} = "
            f"{money(attempt.total, lang):>7}   {verdict(attempt, lang)}")


def trip_title(trip: Trip, end_day: str, lang: str) -> str:
    r = trip.request
    title = t("trip_title", lang, city=city_name(r.city, lang), start=day_label(r.day, lang), end=day_label(end_day, lang))
    return f"{title} · {count(r.nights, 'night', lang)} · {count(r.travellers, 'traveller', lang)}"
