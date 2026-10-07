"""The agent's three tools: two SQL queries and a semantic search over the hotel brochures."""

from __future__ import annotations

import sqlite3
from typing import Protocol

import numpy as np
import pandas as pd

from .data import query

DEFAULT_ENCODER = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def find_flights(conn: sqlite3.Connection, city: str, day: str, travellers: int = 1) -> pd.DataFrame:
    """Flights to `city` leaving on `day` (YYYY-MM-DD) with enough seats left, cheapest first.

    `id` identifies the row: a flight number alone is not unique (the same number can fly to two cities on one day).
    """
    sql = """
        SELECT id, numero AS flight, origine AS origin, heure_depart AS departure_time, duree_h AS hours,
               prix_eur AS price, places_restantes AS seats_left
        FROM vols
        WHERE destination = ? AND date_depart = ? AND places_restantes >= ?
        ORDER BY prix_eur ASC
    """
    return query(conn, sql, (city, day, travellers))


def find_activities(conn: sqlite3.Connection, city: str) -> pd.DataFrame:
    """Activities offered in `city`, cheapest first."""
    sql = """
        SELECT nom AS name, categorie AS category, duree_h AS hours, prix_eur AS price
        FROM activites
        WHERE ville = ?
        ORDER BY prix_eur ASC
    """
    return query(conn, sql, (city,))


class Encoder(Protocol):
    """Anything that turns texts into vectors, like a `SentenceTransformer`."""

    def encode(self, sentences: list[str], normalize_embeddings: bool = True) -> np.ndarray: ...


def load_encoder(model_id: str = DEFAULT_ENCODER) -> Encoder:
    """The multilingual sentence encoder (about 470 MB, downloaded once from the Hugging Face Hub, 50+ languages)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_id)


class HotelSearch:
    """Finds the hotels of a city that match a wish written freely, in any language the encoder knows.

    The brochures are embedded once, when the object is built. Only the wish is embedded at each search: the
    original version re-encoded the brochures of the city for every departure day it tried.
    """

    def __init__(self, brochures: pd.DataFrame, encoder: Encoder):
        self.brochures = brochures.reset_index(drop=True)
        self.encoder = encoder
        # One batch per city, as in the original version, so that the vectors are exactly the same.
        self.embeddings = np.zeros((len(self.brochures), 0))
        for city, rows in self.brochures.groupby("city").groups.items():
            vectors = np.asarray(encoder.encode(list(self.brochures.loc[rows, "summary"]), normalize_embeddings=True))
            if self.embeddings.shape[1] == 0:
                self.embeddings = np.zeros((len(self.brochures), vectors.shape[1]), dtype=vectors.dtype)
            self.embeddings[rows] = vectors

    def search(self, city: str, wish: str, k: int = 3) -> pd.DataFrame:
        """The `k` brochures of `city` closest in meaning to the wish, with a `score` column, best first.

        Normalised vectors: the dot product is the cosine similarity.
        """
        rows = self.brochures.index[self.brochures["city"] == city]
        hotels = self.brochures.loc[rows].reset_index(drop=True)
        if hotels.empty:
            return hotels.assign(score=pd.Series(dtype=float))
        wish_vector = np.asarray(self.encoder.encode([wish], normalize_embeddings=True))[0]
        hotels["score"] = self.embeddings[rows] @ wish_vector
        return hotels.sort_values("score", ascending=False).head(k).reset_index(drop=True)
