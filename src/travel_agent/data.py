"""Access to the two data sources: the SQLite database (flights, activities, bookings) and the hotel brochures (PDF).

The database keeps the French schema of the original dataset (`vols`, `activites`, `reservations`, ...). The tools
rename the columns to English in their SQL, so the rest of the code never sees the French names.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[2] / "data"
DEFAULT_DB = DATA / "voyages.db"
DEFAULT_BROCHURES = DATA / "hotels"


def connect(path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    """Open the travel database. A missing file raises an error instead of silently creating an empty database."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No database at {path}")
    return sqlite3.connect(path)


def query(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a parameterised query (`?` placeholders, values passed apart: no SQL injection) and return a DataFrame."""
    return pd.read_sql_query(sql, conn, params=params)


def cities(conn: sqlite3.Connection) -> list[str]:
    """The destinations served by at least one flight, as written in the database."""
    return sorted(query(conn, "SELECT DISTINCT destination FROM vols")["destination"])


def date_range(conn: sqlite3.Connection) -> tuple[date, date]:
    """The first and last departure dates found in the flights table."""
    first, last = conn.execute("SELECT MIN(date_depart), MAX(date_depart) FROM vols").fetchone()
    return date.fromisoformat(first), date.fromisoformat(last)


def load_brochures(folder: str | Path = DEFAULT_BROCHURES) -> pd.DataFrame:
    """Read every PDF brochure and return one row per hotel.

    A few facts are written in a fixed format in each brochure (city, stars, price, guest rating) and are extracted
    with regular expressions. Everything else stays free text, because that is what the sentence encoder reads:
    "quiet", "for families" or "romantic" are not columns anywhere.

    Columns: city, hotel, stars, rating, reviews, price_per_night, text (the whole brochure) and summary (the
    presentation and the guest reviews only, the part that is embedded).
    """
    from pypdf import PdfReader

    rows = []
    for pdf in sorted(Path(folder).glob("*.pdf")):
        text = "\n".join((page.extract_text() or "") for page in PdfReader(pdf).pages)
        header = re.search(r"^(.+?) - (\d) etoiles - a partir de (\d+) euros la nuit", text, re.M)
        rating = re.search(r"Note des voyageurs : ([\d.]+) sur 10 \((\d+) avis\)", text)
        flat = " ".join(text.split())
        presentation = re.search(r"Presentation (.*?) Equipements", flat)
        reviews = re.search(r"Avis des clients (.*?) [A-ZÀ-Ý][^ ]* .*Brochure du reseau", flat)
        rows.append({
            "city": header.group(1).strip() if header else "?",
            "hotel": text.strip().splitlines()[0].strip(),
            "stars": int(header.group(2)) if header else 0,
            "rating": float(rating.group(1)) if rating else float("nan"),
            "reviews": int(rating.group(2)) if rating else 0,
            "price_per_night": float(header.group(3)) if header else float("nan"),
            "text": flat,
            # The amenities list and the footer are almost identical from one brochure to the next: embedding them
            # would pull every hotel towards the others. The presentation and the reviews carry each hotel's character.
            "summary": " ".join(m.group(1) for m in (presentation, reviews) if m) or flat,
        })
    return pd.DataFrame(rows)
