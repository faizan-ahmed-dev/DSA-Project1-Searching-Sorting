"""url_scraper.py - BONUS: paste a TMDB URL and scrape the movies it points at.

SAFETY: the pasted URL is never downloaded. We only read WHAT it points at (a movie, a
collection, a person, a genre...) and then ask the official TMDB API for it, using your
API key. So the app only ever talks to api.themoviedb.org.

Supported URLs (website or API form)
------------------------------------
  https://www.themoviedb.org/movie/550-fight-club          one movie
  https://www.themoviedb.org/collection/10                 every movie in a collection
  https://www.themoviedb.org/person/287                    every movie a person worked on
  https://www.themoviedb.org/genre/28-action/movie         movies of a genre
  https://www.themoviedb.org/keyword/9715/movie            movies with a keyword
  https://www.themoviedb.org/company/420                   movies of a production company
  https://www.themoviedb.org/movie/top-rated               popular / top-rated / now-playing / upcoming
  https://www.themoviedb.org/search?query=batman           search results
  https://api.themoviedb.org/3/discover/movie?with_genres=35&primary_release_year=1999
      (also movie/popular, movie/top_rated, search/movie, trending/movie/week, ...)

It reuses everything from scraper.py (requests, retries, parsing, pause/resume/stop) and
the same database: movies already saved are skipped, new ones are added.
"""
import re
import time
from urllib.parse import parse_qsl, urlparse

from scraper import DELAY, FLUSH_EVERY, ScraperWorker
from storage import DEFAULT_DB, MovieStore

MAX_PAGES = 500                      # TMDB never returns more than 500 pages
LIST_ENDPOINTS = {"discover/movie", "movie/popular", "movie/top_rated", "movie/now_playing",
                  "movie/upcoming", "search/movie", "trending/movie/day", "trending/movie/week"}
WEBSITE_LISTS = {"popular": "movie/popular", "top-rated": "movie/top_rated",
                 "now-playing": "movie/now_playing", "upcoming": "movie/upcoming"}
DROP_PARAMS = {"api_key", "page", "append_to_response"}   # we set these ourselves
SUPPORTED = ("a movie, collection or person page, a genre / keyword / company page, a search, "
             "or an api.themoviedb.org/3 list such as discover/movie")


def _lead_id(text):
    match = re.match(r"\d+", text)
    return int(match.group()) if match else None


def _plan(kind, description, id=None, path=None, params=None):
    return {"kind": kind, "description": description, "id": id, "path": path, "params": params or {}}


def _list_plan(path, params, description):
    return _plan("list", description, path=path, params=params)


def _from_api_url(segments, params):
    if not segments or segments[0] != "3":
        raise ValueError("Only version 3 API URLs (api.themoviedb.org/3/...) are supported.")
    endpoint = "/".join(segments[1:])
    if endpoint in LIST_ENDPOINTS:
        return _list_plan(endpoint, params, f"List '{endpoint}'" + (f" {params}" if params else ""))
    for pattern, kind, label in [(r"movie/(\d+)", "movie", "Movie #{}"),
                                 (r"collection/(\d+)", "collection", "Collection #{}"),
                                 (r"person/(\d+)(?:/movie_credits)?", "person", "Person #{} (their movies)")]:
        match = re.fullmatch(pattern, endpoint)
        if match:
            number = int(match.group(1))
            return _plan(kind, label.format(number), id=number)
    raise ValueError(f"That API endpoint isn't supported. Supported: {SUPPORTED}.")


def _from_website_url(segments, params):
    if not segments:
        raise ValueError(f"Paste a link to something specific. Supported: {SUPPORTED}.")
    first = segments[0]
    second = segments[1] if len(segments) > 1 else ""
    number = _lead_id(second)
    if first == "movie":
        if not second:
            return _list_plan("movie/popular", params, "Popular movies")
        if number is not None:
            return _plan("movie", f"Movie #{number}", id=number)
        if second in WEBSITE_LISTS:
            return _list_plan(WEBSITE_LISTS[second], params, f"{second} movies")
    elif first == "collection" and number is not None:
        return _plan("collection", f"Collection #{number}", id=number)
    elif first == "person" and number is not None:
        return _plan("person", f"Person #{number} (their movies)", id=number)
    elif first == "genre" and number is not None:
        return _list_plan("discover/movie", dict(params, with_genres=str(number)), f"Genre #{number}")
    elif first == "keyword" and number is not None:
        return _list_plan("discover/movie", dict(params, with_keywords=str(number)), f"Keyword #{number}")
    elif first == "company" and number is not None:
        return _list_plan("discover/movie", dict(params, with_companies=str(number)), f"Company #{number}")
    elif first == "search":
        if not params.get("query"):
            raise ValueError("That search link has no query in it.")
        return _list_plan("search/movie", params, f"Search for '{params['query']}'")
    elif first == "tv":
        raise ValueError("This project collects movies; TV shows aren't supported.")
    raise ValueError(f"That kind of link isn't supported. Supported: {SUPPORTED}.")


def parse_tmdb_url(url):
    """Turn a pasted URL into a 'plan' dict (kind, description, id/path/params).
    Raises ValueError with a friendly message if the URL can't be used."""
    text = (url or "").strip()
    if not text:
        raise ValueError("Paste a TMDB URL first.")
    if "://" not in text:
        text = "https://" + text
    parts = urlparse(text)
    host = (parts.hostname or "").lower()
    segments = [s for s in parts.path.split("/") if s]
    params = {k: v for k, v in parse_qsl(parts.query) if k not in DROP_PARAMS}
    if host == "api.themoviedb.org":
        return _from_api_url(segments, params)
    if host in ("themoviedb.org", "www.themoviedb.org"):
        return _from_website_url(segments, params)
    raise ValueError("Only themoviedb.org and api.themoviedb.org links are supported.")


def _unique(ids):
    seen, out = set(), []
    for movie_id in ids:
        if movie_id not in seen:
            seen.add(movie_id)
            out.append(movie_id)
    return out


class UrlScraperWorker(ScraperWorker):
    """Scrapes the movies behind one URL. Inherits pause / resume / stop, the retrying
    request function and the parser from ScraperWorker.

    progress(done, expected): movies processed so far / movies found at the URL."""

    def __init__(self, api_key, plan, max_movies=100, db_path=DEFAULT_DB):
        super().__init__(api_key, target=max_movies, db_path=db_path)
        self.plan = plan
        self.max_movies = max_movies

    def _collect_ids(self):
        """Step 1: find the ids of the movies the URL points at (at most max_movies)."""
        plan, limit = self.plan, self.max_movies
        if plan["kind"] == "movie":
            return [plan["id"]]
        if plan["kind"] == "collection":
            data = self._get(f"/collection/{plan['id']}", {}) or {}
            return _unique(p["id"] for p in data.get("parts", []))[:limit]
        if plan["kind"] == "person":
            data = self._get(f"/person/{plan['id']}/movie_credits", {}) or {}
            return _unique(e["id"] for e in data.get("cast", []) + data.get("crew", []))[:limit]
        ids, page = [], 1                                 # a paged list: 20 movies per page
        while len(ids) < limit and page <= MAX_PAGES:
            data = self._get("/" + plan["path"], dict(plan["params"], page=page))
            if not data or not data.get("results"):
                break
            ids = _unique(ids + [item["id"] for item in data["results"]])
            if page >= data.get("total_pages", 1):
                break
            page += 1
        return ids[:limit]

    def run(self):
        store = MovieStore(self.db_path)
        have = store.existing_ids()
        buffer = []
        added = skipped = failed = 0
        outcome = "done"
        try:
            self.status.emit(f"URL scrape: {self.plan['description']}")
            ids = self._collect_ids()
            if self._bad_key:
                outcome = "error"
                self.status.emit("Invalid API key (401).")
                raise InterruptedError
            if not self._running:
                raise InterruptedError
            if not ids:
                self.status.emit("No movies found at that URL.")
                return
            expected = len(ids)
            self.status.emit(f"Found {expected} movie(s) at that URL.")
            self.progress.emit(0, expected)

            for processed, movie_id in enumerate(ids, start=1):
                if not self._alive():
                    raise InterruptedError
                if movie_id in have:
                    skipped += 1
                else:
                    detail = self._get(f"/movie/{movie_id}", {"append_to_response": "credits"})
                    if detail:
                        buffer.append(self._parse(detail))
                        have.add(movie_id)
                        added += 1
                        if len(buffer) >= FLUSH_EVERY:
                            store.add_many(buffer)
                            buffer.clear()
                    elif not self._running:
                        raise InterruptedError
                    else:
                        failed += 1
                    time.sleep(DELAY)
                self.progress.emit(processed, expected)
        except InterruptedError:
            if outcome != "error":
                outcome = "stopped"
        finally:
            store.add_many(buffer)                        # never lose the last partial batch
            store.close()
            self.status.emit(f"URL scrape {'stopped' if outcome == 'stopped' else 'finished'}: "
                             f"{added} new movie(s) added, {skipped} already in the database, "
                             f"{failed} could not be fetched.")
            self.finished_signal.emit(outcome)
