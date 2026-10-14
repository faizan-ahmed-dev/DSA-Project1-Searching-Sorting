"""test_url_scraper.py - tests the URL bonus WITHOUT internet.
URL parsing is tested directly; the scraper is tested against a fake TMDB API that returns
the same JSON shapes the real one does (this checks OUR logic, not TMDB itself).
Run:  python test_url_scraper.py"""
import os
import tempfile

from PyQt5.QtCore import QCoreApplication

from storage import MovieStore
from url_scraper import UrlScraperWorker, parse_tmdb_url

app = QCoreApplication([])


def check_parsing():
    good = [
        ("https://www.themoviedb.org/movie/550-fight-club", "movie", 550, None),
        ("themoviedb.org/movie/550", "movie", 550, None),
        ("https://www.themoviedb.org/collection/10-star-wars-collection", "collection", 10, None),
        ("https://www.themoviedb.org/person/287-brad-pitt", "person", 287, None),
        ("https://www.themoviedb.org/genre/28-action/movie", "list", None, ("discover/movie", {"with_genres": "28"})),
        ("https://www.themoviedb.org/keyword/9715-time-travel/movie", "list", None, ("discover/movie", {"with_keywords": "9715"})),
        ("https://www.themoviedb.org/company/420-marvel-studios", "list", None, ("discover/movie", {"with_companies": "420"})),
        ("https://www.themoviedb.org/movie/top-rated", "list", None, ("movie/top_rated", {})),
        ("https://www.themoviedb.org/movie", "list", None, ("movie/popular", {})),
        ("https://www.themoviedb.org/search?query=batman", "list", None, ("search/movie", {"query": "batman"})),
        ("https://api.themoviedb.org/3/discover/movie?with_genres=35&primary_release_year=1999&api_key=SECRET&page=7",
         "list", None, ("discover/movie", {"with_genres": "35", "primary_release_year": "1999"})),
        ("https://api.themoviedb.org/3/movie/550?api_key=SECRET", "movie", 550, None),
        ("https://api.themoviedb.org/3/collection/10", "collection", 10, None),
        ("https://api.themoviedb.org/3/person/287/movie_credits", "person", 287, None),
        ("https://api.themoviedb.org/3/trending/movie/week", "list", None, ("trending/movie/week", {})),
    ]
    bad = ["", "   ", "https://example.com/movie/550", "https://www.themoviedb.org/tv/1396-breaking-bad",
           "https://www.themoviedb.org/", "https://www.themoviedb.org/search", "https://www.themoviedb.org/movie/abc",
           "https://api.themoviedb.org/4/list/1", "https://api.themoviedb.org/3/account/1/favorite/movies",
           "https://evil.com/?u=https://www.themoviedb.org/movie/550", "https://themoviedb.org.evil.com/movie/550"]
    failures = 0
    for url, kind, number, listing in good:
        try:
            plan = parse_tmdb_url(url)
        except ValueError as e:
            print("FAIL (rejected a good URL):", url, e)
            failures += 1
            continue
        ok = plan["kind"] == kind and plan["id"] == number
        if listing:
            ok = ok and plan["path"] == listing[0] and plan["params"] == listing[1]
        if not ok:
            failures += 1
            print("FAIL:", url, plan)
    for url in bad:
        try:
            parse_tmdb_url(url)
            failures += 1
            print("FAIL (accepted a bad URL):", url)
        except ValueError:
            pass
    print(f"URL parsing: {len(good)} good + {len(bad)} bad URLs checked, {failures} failures")


# ------------------------------------------------------------------ fake TMDB
def detail(movie_id):
    return {"id": movie_id, "title": f"Movie {movie_id}", "release_date": "2001-05-04",
            "genres": [{"name": "Drama"}], "original_language": "en", "runtime": 100,
            "vote_average": 7.5, "vote_count": 1000, "popularity": 12.5, "budget": 0, "revenue": 5000,
            "credits": {"crew": [{"job": "Director", "name": "Jane Doe"}, {"job": "Writer", "name": "X"}]}}


class FakeApi:
    def __init__(self, worker, stop_after=None):
        self.calls = []
        self.worker = worker
        self.stop_after = stop_after

    def __call__(self, path, params):
        self.calls.append((path, dict(params)))
        if self.stop_after is not None and len(self.calls) > self.stop_after:
            self.worker.stop()
            return None
        if path == "/collection/10":
            return {"parts": [{"id": 101}, {"id": 102}, {"id": 103}, {"id": 102}]}     # one duplicate
        if path == "/person/287/movie_credits":
            return {"cast": [{"id": 201}, {"id": 202}], "crew": [{"id": 202}, {"id": 203}]}
        if path == "/discover/movie":
            page = params["page"]
            return {"results": [{"id": 1000 + (page - 1) * 20 + i} for i in range(20)], "total_pages": 3}
        if path == "/collection/404":
            return None
        if path.startswith("/movie/"):
            movie_id = int(path.split("/")[2])
            return None if movie_id == 999 else detail(movie_id)
        return None


def run_worker(url, max_movies=100, preload=(), stop_after=None):
    db = os.path.join(tempfile.mkdtemp(), "t.db")
    store = MovieStore(db)
    store.add_many([{"id": i, "title": "old"} for i in preload])
    store.close()
    worker = UrlScraperWorker("KEY", parse_tmdb_url(url), max_movies, db)
    api = FakeApi(worker, stop_after)
    worker._get = api
    log, progress, outcome = [], [], []
    worker.status.connect(log.append)
    worker.progress.connect(lambda d, t: progress.append((d, t)))
    worker.finished_signal.connect(outcome.append)
    worker.run()                                  # runs synchronously here (no thread needed for the test)
    store = MovieStore(db)
    rows = store.load_all()
    store.close()
    return rows, log, progress, outcome[0], api


def check_scraping():
    failures = 0

    def expect(name, condition):
        nonlocal failures
        if not condition:
            failures += 1
            print("FAIL:", name)

    rows, log, progress, outcome, api = run_worker("https://www.themoviedb.org/movie/550")
    expect("single movie saved", [r["id"] for r in rows] == [550] and outcome == "done")
    expect("parsed fields", rows[0]["director"] == "Jane Doe" and rows[0]["budget"] is None
           and rows[0]["release_year"] == 2001 and rows[0]["genres"] == "Drama")

    rows, log, progress, outcome, api = run_worker("https://www.themoviedb.org/collection/10", preload=[102])
    ids = sorted(r["id"] for r in rows)
    expect("collection: dedupe + skip existing", ids == [101, 102, 103], )
    expect("collection summary", "2 new movie(s) added, 1 already in the database" in log[-1])
    expect("collection progress ends at 3/3", progress[-1] == (3, 3))

    rows, log, progress, outcome, api = run_worker("https://www.themoviedb.org/person/287")
    expect("person: cast + crew merged without duplicates", sorted(r["id"] for r in rows) == [201, 202, 203])

    rows, log, progress, outcome, api = run_worker("https://www.themoviedb.org/genre/28-action/movie", max_movies=45)
    expect("list: stops at max_movies", len(rows) == 45)
    pages = [c[1]["page"] for c in api.calls if c[0] == "/discover/movie"]
    expect("list: only needed pages requested", pages == [1, 2, 3])
    expect("list: genre filter passed on", all(c[1].get("with_genres") == "28" for c in api.calls if c[0] == "/discover/movie"))
    expect("list: api key never forwarded from URL", all("api_key" not in c[1] for c in api.calls))

    rows, log, progress, outcome, api = run_worker("https://www.themoviedb.org/genre/28-action/movie", max_movies=500)
    expect("list: ends when TMDB runs out of pages", len(rows) == 60)

    rows, log, progress, outcome, api = run_worker("https://www.themoviedb.org/collection/404")
    expect("unknown collection handled", rows == [] and "No movies found" in " ".join(log))

    rows, log, progress, outcome, api = run_worker("https://www.themoviedb.org/genre/28-action/movie",
                                                   max_movies=60, stop_after=12)
    expect("stop: outcome", outcome == "stopped")
    expect("stop: movies fetched before stopping are still saved", 0 < len(rows) < 60)

    print(f"URL scraper (fake API): 9 scenarios checked, {failures} failures")


if __name__ == "__main__":
    check_parsing()
    check_scraping()
