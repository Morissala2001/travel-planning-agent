"""Shared fixtures. No test downloads a model or needs the real data: a fake encoder and a tiny world stand in."""

import hashlib
import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from travel_agent.tools import HotelSearch

ROOT = Path(__file__).resolve().parents[1]

SCHEMA = """
CREATE TABLE vols (
    id INTEGER PRIMARY KEY, numero TEXT NOT NULL, origine TEXT NOT NULL,
    destination TEXT NOT NULL, date_depart TEXT NOT NULL, heure_depart TEXT NOT NULL,
    duree_h REAL, prix_eur REAL NOT NULL, places_restantes INTEGER);
CREATE TABLE activites (
    id INTEGER PRIMARY KEY, ville TEXT NOT NULL, nom TEXT NOT NULL,
    categorie TEXT NOT NULL, duree_h REAL, prix_eur REAL NOT NULL);
CREATE TABLE reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, client TEXT NOT NULL, destination TEXT NOT NULL,
    date_depart TEXT NOT NULL, nuits INTEGER NOT NULL, voyageurs INTEGER NOT NULL,
    vol TEXT, hotel TEXT, activites TEXT, prix_total REAL NOT NULL, reservee_le TEXT NOT NULL);
"""

# Madrid, 4 activities: one free, three paid (70 EUR in all).
ACTIVITIES = [("Madrid", "Parc du Retiro", "plein air", 2.5, 0.0), ("Madrid", "Temple de Debod", "culture", 1.0, 10.0),
              ("Madrid", "Musée du Prado", "culture", 3.0, 20.0), ("Madrid", "Flamenco", "nocturne", 2.0, 40.0)]

# Three hotels whose summaries share words with the test wishes (the fake encoder only sees shared words).
HOTELS = [("Madrid", "Hôtel Familia", 3, 8.2, 660, 100.0, "un hôtel familial pour les familles avec enfants et piscine"),
          ("Madrid", "Palacio Real", 5, 9.1, 300, 300.0, "le grand luxe un palace avec spa et majordome"),
          ("Madrid", "Hostal Barato", 1, 6.4, 210, 50.0, "une auberge pas chère et économique pour petit budget")]


class FakeEncoder:
    """Bag-of-words hashing: texts sharing words get similar vectors, with no model to download."""

    dim = 512

    def encode(self, sentences, normalize_embeddings=True):
        vectors = np.zeros((len(sentences), self.dim))
        for row, sentence in enumerate(sentences):
            for word in re.findall(r"[^\W\d_]+", sentence.lower()):
                vectors[row, int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return vectors / norms


def make_db(path: Path, flights: list[tuple], activities: list[tuple] = ACTIVITIES) -> Path:
    """A database with the schema of the real one. Flights: (number, origin, city, day, time, hours, price, seats)."""
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO vols (numero, origine, destination, date_depart, heure_depart, duree_h, prix_eur, "
                     "places_restantes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", flights)
    conn.executemany("INSERT INTO activites (ville, nom, categorie, duree_h, prix_eur) VALUES (?, ?, ?, ?, ?)", activities)
    conn.commit()
    conn.close()
    return path


def brochures_frame(hotels=HOTELS) -> pd.DataFrame:
    return pd.DataFrame([{"city": c, "hotel": h, "stars": s, "rating": r, "reviews": n, "price_per_night": p,
                          "text": f"{h} {c} {summary}", "summary": summary} for c, h, s, r, n, p, summary in hotels])


def make_pdf(path: Path, lines: list[str]) -> Path:
    """A one-page PDF with one line of text per entry, readable by pypdf (no dependency needed to write it)."""
    escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    stream = "BT /F1 10 Tf 40 800 Td 14 TL " + " ".join(f"({line}) Tj T*" for line in escaped) + " ET"
    data = stream.encode("cp1252")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    path.write_bytes(bytes(out))
    return path


def brochure_lines(city, hotel, stars, rating, reviews, price, summary) -> list[str]:
    """The layout of the real brochures."""
    return [hotel, f"{city} - {stars} etoiles - a partir de {price:.0f} euros la nuit",
            f"Note des voyageurs : {rating} sur 10 ({reviews} avis)", "Presentation", summary + ".",
            "Equipements", "wifi gratuit, climatisation.", "Avis des clients", '"Tres bien."',
            f"{hotel} - {city} - Brochure du reseau d'hoteliers de Marc"]


def week_of_flights(city="Madrid", seats=9):
    """One Nice flight a day from Aug 8 to Aug 16, 2026; the 12th is dearer than the days around it."""
    prices = {"08": 130, "09": 125, "10": 90, "11": 95, "12": 120, "13": 110, "14": 100, "15": 140, "16": 150}
    return [(f"T{day}", "Nice", city, f"2026-08-{day}", "09:15", 2.0, float(p), seats) for day, p in prices.items()]


@pytest.fixture
def db(tmp_path):
    return make_db(tmp_path / "travel.db", week_of_flights())


@pytest.fixture
def conn(db):
    connection = sqlite3.connect(db)
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def search():
    return HotelSearch(brochures_frame(), FakeEncoder())


@pytest.fixture
def brochure_dir(tmp_path):
    folder = tmp_path / "hotels"
    folder.mkdir()
    for c, h, s, r, n, p, summary in HOTELS:
        make_pdf(folder / f"{h.lower().replace(' ', '_')}.pdf", brochure_lines(c, h, s, r, n, p, summary))
    return folder
