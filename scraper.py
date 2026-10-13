"""scraper.py - TMDB scraper that runs in a background QThread.

Phase 1: discover/movie, one query per release year -> list of movie ids
Phase 2: movie/{id}?append_to_response=credits       -> full details + director
Both phases are interleaved: each discovered movie is fetched immediately.
Resumable: ids already in the database are skipped, so you can close the
app and continue later.
"""
import threading
import time

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from storage import DEFAULT_DB, MovieStore

BASE_URL = "https://api.themoviedb.org/3"
START_YEAR, END_YEAR = 1980, 2025
PAGES_PER_YEAR = 20          # 20 pages * 20 movies * 46 years = up to 18,400
FLUSH_EVERY = 50             # write to the database every N movies
DELAY = 0.05                 # seconds between requests (be polite)


class ScraperWorker(QThread):
    progress = pyqtSignal(int, int)   # movies saved so far, target
    status = pyqtSignal(str)          # text for the log / status label
    finished_signal = pyqtSignal(str) # "done", "stopped" or "error"

    def __init__(self, api_key, target=16000, db_path=DEFAULT_DB):
        super().__init__()
        self.api_key = api_key.strip()
        self.target = target
        self.db_path = db_path
        self._running = True
        self._not_paused = threading.Event()
        self._not_paused.set()        # set = running, cleared = paused
        self._bad_key = False

    # ---- controls called from the UI thread ----
    def pause(self):
        self._not_paused.clear()
        self.status.emit("Paused")

    def resume(self):
        self._not_paused.set()
        self.status.emit("Resumed")

    def stop(self):
        self._running = False
        self._not_paused.set()        # wake the thread if it is paused

    # ---- internals ----
    def _alive(self):
        """Blocks while paused. Returns False once stop() was called."""
        self._not_paused.wait()
        return self._running

    def _get(self, path, params):
        params = dict(params, api_key=self.api_key)
        for attempt in range(3):
            if not self._alive():
                return None
            try:
                r = requests.get(BASE_URL + path, params=params, timeout=15)
            except requests.RequestException:
                time.sleep(1 + attempt)
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code == 401:
                self._bad_key = True
                return None
            if r.status_code == 429:  # rate limited
                time.sleep(int(r.headers.get("Retry-After", 2)))
                continue
            if r.status_code == 404:
                return None
            time.sleep(1 + attempt)
        return None

    @staticmethod
    def _parse(d):
        date = d.get("release_date") or ""
        crew = (d.get("credits") or {}).get("crew", [])
        directors = [c["name"] for c in crew if c.get("job") == "Director"]
        return {
            "id": d["id"],
            "title": d.get("title"),
            "release_year": int(date[:4]) if date[:4].isdigit() else None,
            "release_date": date or None,
            "genres": ", ".join(g["name"] for g in d.get("genres", [])) or None,
            "director": ", ".join(directors) or None,
            "original_language": d.get("original_language"),
            "runtime": d.get("runtime") or None,   # 0 -> None (missing)
            "vote_average": d.get("vote_average"),
            "vote_count": d.get("vote_count"),
            "popularity": d.get("popularity"),
            "budget": d.get("budget") or None,     # 0 -> None (missing)
            "revenue": d.get("revenue") or None,
        }

    def run(self):
        store = MovieStore(self.db_path)
        have = store.existing_ids()
        buffer = []
        outcome = "done"
        self.status.emit(f"Starting. {len(have)} movies already saved.")
        self.progress.emit(len(have), self.target)

        try:
            for year in range(END_YEAR, START_YEAR - 1, -1):
                for page in range(1, PAGES_PER_YEAR + 1):
                    if not self._alive():
                        raise InterruptedError
                    data = self._get("/discover/movie", {
                        "primary_release_year": year,
                        "sort_by": "vote_count.desc",
                        "page": page,
                    })
                    if self._bad_key:
                        outcome = "error"
                        self.status.emit("Invalid API key (401).")
                        raise InterruptedError
                    if not data or not data.get("results"):
                        break
                    self.status.emit(f"Year {year}, page {page}")

                    for item in data["results"]:
                        if not self._alive():
                            raise InterruptedError
                        if item["id"] in have:
                            continue
                        detail = self._get(f"/movie/{item['id']}",
                                           {"append_to_response": "credits"})
                        if not detail:
                            continue
                        buffer.append(self._parse(detail))
                        have.add(item["id"])
                        if len(buffer) >= FLUSH_EVERY:
                            store.add_many(buffer)
                            buffer.clear()
                        self.progress.emit(len(have), self.target)
                        if len(have) >= self.target:
                            raise InterruptedError
                        time.sleep(DELAY)

                    if page >= data.get("total_pages", 1):
                        break
        except InterruptedError:
            if outcome != "error":
                outcome = "done" if len(have) >= self.target else "stopped"
        finally:
            store.add_many(buffer)   # never lose the last partial batch
            store.close()
            self.progress.emit(len(have), self.target)
            self.finished_signal.emit(outcome)
