import gc
from datetime import date
from pathlib import Path

import pytest
from conftest import ACTIVITIES, HOTELS, FakeEncoder, brochures_frame, make_db

from travel_agent.data import PrivateCopy, cities, connect, date_range, load_brochures, query
from travel_agent.tools import HotelSearch, find_activities, find_flights


def test_connect_refuses_a_missing_file_instead_of_creating_an_empty_database(tmp_path):
    with pytest.raises(FileNotFoundError):
        connect(tmp_path / "missing.db")
    assert not (tmp_path / "missing.db").exists()


def test_a_private_copy_is_deleted_with_its_owner(db):
    copy = PrivateCopy(db)
    path = copy.path
    assert path != Path(db) and path.read_bytes() == Path(db).read_bytes()
    del copy  # a visitor's session ends
    gc.collect()
    assert not path.exists()


def test_cities_and_date_range(conn):
    assert cities(conn) == ["Madrid"]
    assert date_range(conn) == (date(2026, 8, 8), date(2026, 8, 16))


def test_query_values_are_never_pasted_into_the_sql(conn):
    hostile = "Madrid' OR '1'='1"
    assert query(conn, "SELECT * FROM vols WHERE destination = ?", (hostile,)).empty


def test_flights_are_filtered_on_seats_and_sorted_by_price(tmp_path):
    flights = [("A1", "Nice", "Madrid", "2026-08-12", "07:40", 2.0, 150.0, 9),
               ("A2", "Paris CDG", "Madrid", "2026-08-12", "11:30", 2.2, 90.0, 1),  # cheapest, but one seat only
               ("A3", "Nice", "Madrid", "2026-08-12", "20:20", 1.9, 120.0, 3),
               ("A4", "Nice", "Rome", "2026-08-12", "06:15", 2.0, 50.0, 9)]
    conn = connect(make_db(tmp_path / "f.db", flights))
    found = find_flights(conn, "Madrid", "2026-08-12", travellers=2)
    assert list(found["flight"]) == ["A3", "A1"]
    assert list(found.columns) == ["id", "flight", "origin", "departure_time", "hours", "price", "seats_left"]
    assert list(find_flights(conn, "Madrid", "2026-08-12", 1)["flight"]) == ["A2", "A3", "A1"]


def test_activities_are_sorted_from_the_cheapest(conn):
    found = find_activities(conn, "Madrid")
    assert list(found["price"]) == sorted(a[-1] for a in ACTIVITIES)
    assert list(found.columns) == ["name", "category", "hours", "price"]


def test_hotel_search_ranks_by_meaning_and_returns_k(search):
    assert search.search("Madrid", "un palace de luxe avec spa")["hotel"][0] == "Palacio Real"
    assert search.search("Madrid", "une auberge pas chère")["hotel"][0] == "Hostal Barato"
    found = search.search("Madrid", "familles avec enfants", k=2)
    assert len(found) == 2 and found["score"].is_monotonic_decreasing
    assert search.search("Atlantis", "anything").empty


def test_brochures_are_embedded_once_and_only_the_wish_afterwards():
    class Counting(FakeEncoder):
        texts = 0

        def encode(self, sentences, normalize_embeddings=True):
            Counting.texts += len(sentences)
            return super().encode(sentences, normalize_embeddings)

    search = HotelSearch(brochures_frame(), Counting())
    assert Counting.texts == len(HOTELS)
    for _ in range(5):
        search.search("Madrid", "piscine")
    assert Counting.texts == len(HOTELS) + 5


def test_brochures_are_read_from_pdf(brochure_dir):
    brochures = load_brochures(brochure_dir)
    assert len(brochures) == 3
    familia = brochures.set_index("hotel").loc["Hôtel Familia"]
    assert (familia["city"], familia["stars"], familia["rating"], familia["reviews"], familia["price_per_night"]) == \
        ("Madrid", 3, 8.2, 660, 100.0)
    assert familia["summary"].startswith("un hôtel familial") and "Tres bien" in familia["summary"]
    assert "Equipements" not in familia["summary"] and "Equipements" in familia["text"]
