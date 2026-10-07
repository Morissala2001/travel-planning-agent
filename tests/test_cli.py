import sqlite3

import pytest
from conftest import FakeEncoder

import travel_agent.cli as cli

FAMILY = "un hôtel pour les familles avec enfants et une piscine"


@pytest.fixture
def run(db, brochure_dir, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_encoder", lambda *args, **kwargs: FakeEncoder())

    def run(*args):
        cli.main(["--db", str(db), "--brochures", str(brochure_dir), *args])
        return capsys.readouterr().out

    return run


def plan_args(budget="560", wish=FAMILY, city="Madrid"):
    return ["--city", city, "--date", "2026-08-12", "--budget", budget, "--wish", wish]


def test_cities(run):
    out = run("cities")
    assert "Madrid" in out and "Мадрид" in out and "2026-08-08 to 2026-08-16" in out


def test_plan_answers_in_the_language_of_the_wish(run):
    assert "J'ai retiré « Flamenco » (40 €)." in run("plan", *plan_args())
    english = run("plan", *plan_args(wish="a hotel for families with children"))
    assert english.startswith("Flight T12 from Nice on Aug 12")
    assert "Итого" in run("plan", *plan_args(wish="отель для семьи с детьми"))
    assert run("plan", *plan_args(), "--lang", "en").startswith("Flight")


def test_plan_verbose_lists_every_priced_combination(run):
    out = run("plan", *plan_args(), "-v")
    assert "dépasse de 30 €" in out and "OK" in out


def test_city_names_in_any_language_and_unknown_city(run):
    assert "Итого" in run("plan", *plan_args(city="Мадрид", wish="семейный отель"))
    with pytest.raises(SystemExit, match="Unknown city"):
        run("plan", *plan_args(city="Atlantis"))


def test_book_needs_yes(run, db):
    assert "Rien n'a été réservé" in run("book", *plan_args(), "--name", "Ada")
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 0
    assert "C'est réservé pour Ada" in run("book", *plan_args(), "--name", "Ada", "--yes")
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 1
