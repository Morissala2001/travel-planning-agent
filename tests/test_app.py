"""The web app renders, answers in the traveller's language and books only after confirmation (fake encoder, tiny world)."""

import sqlite3
from pathlib import Path

import pytest
from conftest import FakeEncoder

pytest.importorskip("streamlit")
import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

import travel_agent.tools  # noqa: E402

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def app(db, brochure_dir, monkeypatch):
    st.cache_resource.clear()
    monkeypatch.setenv("TRAVEL_AGENT_DB", str(db))
    monkeypatch.setenv("TRAVEL_AGENT_BROCHURES", str(brochure_dir))
    monkeypatch.setattr(travel_agent.tools, "load_encoder", lambda *args, **kwargs: FakeEncoder())
    return AppTest.from_file(str(APP), default_timeout=60).run()


def button(app, label):
    return next(b for b in app.button if b.label == label)


def search(app, wish=None):
    if wish is not None:
        app.text_area[0].set_value(wish)
    return button(app, app.button[0].label).click().run()  # the form's search button comes first


def test_first_screen(app):
    assert not app.exception
    assert app.title[0].value == "Where are you going?"
    assert app.text_area[0].value == "a family hotel with a pool, and sightseeing in the city"
    assert "Fill in the form" in app.info[0].value


def test_a_search_shows_the_trip(app):
    search(app)
    assert not app.exception
    assert app.subheader[0].value.startswith("Madrid, Aug 12 – Aug 16 · 4 nights · 2 travellers")
    assert [m.label for m in app.metric] == ["Flight", "Hotel", "Activities", "Total per person"]
    assert app.metric[0].value == "€120"


def test_a_russian_wish_turns_the_page_to_russian_and_keeps_the_form(app):
    app.number_input[1].set_value(800)
    search(app, "отель для семьи с детьми")
    assert not app.exception
    assert app.title[0].value == "Куда поедем?"
    assert app.metric[0].label == "Перелёт"
    assert app.subheader[0].value.startswith("Мадрид, 12 августа – 16 августа · 4 ночи · 2 путешественника")
    # Regression: the translated labels used to reset the form to its default values
    assert app.number_input[1].value == 800 and app.text_area[0].value == "отель для семьи с детьми"


def test_the_language_can_be_forced(app):
    app.button_group[0].set_value("fr").run()
    assert app.title[0].value == "Où partez-vous ?"
    assert app.text_area[0].value.startswith("un hôtel pour la famille")  # the untouched example follows
    search(app, "a hotel for families with children")
    assert app.title[0].value == "Où partez-vous ?"  # forced: the English wish does not switch it back


def test_booking_needs_a_name_and_a_confirmation(app, db):
    search(app)
    button(app, "Book this trip").click().run()
    assert "Enter a name first." in [w.value for w in app.warning]
    app.text_input[0].set_value("Ada").run()
    assert any("Nothing has been booked yet" in i.value for i in app.info)
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 0
    button(app, "Yes, I confirm").click().run()
    assert not app.exception
    assert app.success[-1].value.startswith("Booked for Ada: Madrid, 4 nights")
    assert "Yes, I confirm" not in [b.label for b in app.button]  # once booked, only the result is shown
    assert not any("Nothing has been booked yet" in i.value for i in app.info)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT client, vol FROM reservations").fetchall() == [("Ada", "T12")]
    assert conn.execute("SELECT places_restantes FROM vols WHERE numero = 'T12'").fetchone()[0] == 7

    button(app, "Book this trip").click().run()
    button(app, "Yes, I confirm").click().run()
    assert "already booked this trip" in app.warning[-1].value
    assert conn.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 1


def test_turning_restore_off_recomputes_the_plan(app):
    app.number_input[1].set_value(500)
    search(app, "un hôtel pour les familles avec enfants et une piscine")
    with_restore = app.metric[2].value
    app.sidebar.toggle[0].set_value(False).run()
    assert not app.exception
    assert (with_restore, app.metric[2].value) == ("70 €", "0 €")  # all activities back vs. the bare programme
