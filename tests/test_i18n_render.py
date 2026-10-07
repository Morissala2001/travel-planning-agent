import re

import pytest

from travel_agent.booking import Booking, book
from travel_agent.i18n import (CITY_NAMES, LANGUAGES, TEXT, city_key, count, day_label, detect_language, money,
                               number)
from travel_agent.planner import Note, Request, TravelAgent
from travel_agent.render import attempt_line, booking_text, note_text, summary, trip_title

FAMILY = "un hôtel pour les familles avec enfants et une piscine"


@pytest.mark.parametrize("text, expected", [
    ("un hôtel pour la famille avec une piscine, et des visites dans la ville", "fr"),
    ("je veux faire la fête", "fr"),
    ("a family hotel with a pool, and sightseeing in the city", "en"),
    ("I want to party and go out at night", "en"),
    ("семейный отель с бассейном", "ru"),
    ("отель near the beach, тихий и спокойный", "ru"),
    ("spa", None),
    ("", None),
    ("1234 !!", None),
])
def test_language_detection(text, expected):
    assert detect_language(text) == expected


def test_every_text_exists_in_the_three_languages():
    for key, versions in TEXT.items():
        assert set(versions) == set(LANGUAGES), key
        fields = {lang: set(re.findall(r"{(\w+)}", text)) for lang, text in versions.items()}
        assert fields["en"] == fields["fr"] == fields["ru"], key  # same placeholders everywhere


@pytest.mark.parametrize("n, expected", [(1, "1 ночь"), (2, "2 ночи"), (4, "4 ночи"), (5, "5 ночей"), (11, "11 ночей"),
                                         (12, "12 ночей"), (21, "21 ночь"), (22, "22 ночи"), (25, "25 ночей")])
def test_russian_plurals(n, expected):
    assert count(n, "night", "ru") == expected


def test_plurals_dates_and_money():
    assert count(1, "night", "en") == "1 night" and count(4, "night", "en") == "4 nights"
    assert count(1, "traveller", "fr") == "1 voyageur" and count(2, "traveller", "fr") == "2 voyageurs"
    assert day_label("2026-08-12", "en") == "Aug 12"
    assert day_label("2026-08-12", "fr") == "12 août"
    assert day_label("2026-08-12", "ru") == "12 августа"
    assert money(732.0, "en") == "€732" and money(732.0, "fr") == "732 €"
    assert number(2.2, "fr") == "2,2" and number(2.2, "ru") == "2,2" and number(2.2, "en") == "2.2"
    assert number(0.7851, "en", 2) == "0.79"


def test_cities_are_understood_in_any_language():
    assert city_key("Barcelona") == city_key("barcelone") == city_key("Барселона") == "Barcelone"
    assert city_key(" vienna ") == "Vienne"
    assert city_key("Atlantis") is None
    assert len(CITY_NAMES) == 15


ALL_NOTES = [Note("removed_activity", {"name": "Flamenco", "price": 40.0}),
             Note("changed_hotel", {"old": "Palacio Real", "new": "Hostal Barato"}),
             Note("restored_activities", {"names": ["Musée du Prado", "Flamenco"], "price": 60.0}),
             Note("gave_up", {"day": "2026-08-12"}), Note("no_flight_or_hotel", {"day": "2026-08-12"}),
             Note("other_day_possible", {"day": "2026-08-10", "total": 295.0}),
             Note("other_day_more_activities", {"day": "2026-08-10", "kept": 4, "instead_of": 3, "total": 560.0}),
             Note("other_day_cheaper", {"day": "2026-08-10", "total": 560.0, "saving": 30.0})]


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_every_note_renders_in_every_language(lang):
    for note in ALL_NOTES:
        text = note_text(note, lang)
        assert "{" not in text and text.endswith(".")
    assert "4 занятия вместо 3" in note_text(ALL_NOTES[6], "ru")
    with pytest.raises(ValueError):
        note_text(Note("unknown"), lang)


def test_summary_and_booking_texts_in_three_languages(conn, search):
    plan = TravelAgent(conn, search).plan(Request("Madrid", "2026-08-12", 4, 2, 560, FAMILY))
    assert summary(plan, "en").startswith("Flight T12 from Nice on Aug 12 at 09:15 (2.0 h): €120.")
    assert "Hôtel : Hôtel Familia, 4 nuits à 100 € la nuit." in summary(plan, "fr")
    assert "Итого 550 € на человека при бюджете 560 €." in summary(plan, "ru")
    assert "I removed “Flamenco” (€40)." in summary(plan, "en")
    assert trip_title(plan.trip, "2026-08-16", "fr") == "Madrid, du 12 août au 16 août · 4 nuits · 2 voyageurs"
    assert attempt_line(plan.attempts[0], "en").endswith("over by €30")

    asked = book(conn, plan.trip, "Ada")
    assert "€550 per person, €1100 in all" in booking_text(asked, "en")
    assert "Подтвердите" in booking_text(asked, "ru")
    assert booking_text(book(conn, plan.trip, "Ada", confirm=True), "fr") == \
        "C'est réservé pour Ada : Madrid, 4 nuits, 1100 € au total."
    assert "seats" in booking_text(Booking("no_seats", plan.trip, "Ada"), "en")


def test_nothing_found_summary_gives_a_hint(conn, search):
    plan = TravelAgent(conn, search).plan(Request("Madrid", "2026-08-12", 4, 2, 100, FAMILY))
    text = summary(plan, "en")
    assert text.startswith("I found nothing that fits this budget.") and "other dates" in text
    assert "weekend" not in text  # the original blamed weekend flights, which the data does not support
