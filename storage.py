"""storage.py - saves scraped movies to SQLite so progress is never lost."""
import csv
import os
import sqlite3

# movies.db always lives next to these .py files, wherever you launch the app from
DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "movies.db")

# (column name, SQL type). 13 attributes, you need at least 8.
COLUMNS = [
    ("id", "INTEGER PRIMARY KEY"),
    ("title", "TEXT"),
    ("release_year", "INTEGER"),
    ("release_date", "TEXT"),
    ("genres", "TEXT"),
    ("director", "TEXT"),
    ("original_language", "TEXT"),
    ("runtime", "INTEGER"),
    ("vote_average", "REAL"),
    ("vote_count", "INTEGER"),
    ("popularity", "REAL"),
    ("budget", "INTEGER"),
    ("revenue", "INTEGER"),
]
FIELDS = [name for name, _ in COLUMNS]


class MovieStore:
    # NOTE: SQLite connections must stay in the thread that created them,
    # so the scraper thread and the UI thread each create their own MovieStore.
    def __init__(self, path=DEFAULT_DB):
        self.conn = sqlite3.connect(path)
        cols = ", ".join(f"{n} {t}" for n, t in COLUMNS)
        self.conn.execute(f"CREATE TABLE IF NOT EXISTS movies ({cols})")
        self.conn.commit()

    def existing_ids(self):
        return {r[0] for r in self.conn.execute("SELECT id FROM movies")}

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]

    def add_many(self, rows):
        """rows: list of dicts keyed by FIELDS. Duplicate ids are ignored."""
        if not rows:
            return
        placeholders = ", ".join("?" for _ in FIELDS)
        self.conn.executemany(
            f"INSERT OR IGNORE INTO movies ({', '.join(FIELDS)}) VALUES ({placeholders})",
            [tuple(r.get(f) for f in FIELDS) for r in rows],
        )
        self.conn.commit()

    def load_all(self):
        """Return every movie as a list of dicts (used by the UI later)."""
        cur = self.conn.execute(f"SELECT {', '.join(FIELDS)} FROM movies")
        return [dict(zip(FIELDS, row)) for row in cur]

    def export_csv(self, path="movies.csv"):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(self.load_all())

    def close(self):
        self.conn.close()
