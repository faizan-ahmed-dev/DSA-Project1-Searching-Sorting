"""test_searching.py - checks every search algorithm and filter against a simple answer key.
Run:  python test_searching.py
(Python's `in`, startswith() etc. are used ONLY here as the answer key.)"""
import random
import string

from filters import (contains_text, ends_with_text, filter_records, starts_with_text)
from searching import SEARCH_ALGORITHMS, search_records

random.seed(7)


def make_records(n):
    records = []
    for i in range(n):
        records.append({
            "id": i,
            "title": "".join(random.choices("abc ", k=random.randint(1, 6))),     # many duplicates
            "release_year": random.randint(1980, 2025),
            "vote_average": round(random.uniform(0, 10), 1),
            "budget": random.choice([None, random.randint(1, 300_000_000)]),
        })
    return records


def norm(v):
    return v.lower() if isinstance(v, str) else v


def search_correctness():
    records = make_records(2000)
    checked = refused = failures = 0
    for column in ["title", "release_year", "vote_average", "budget"]:
        values = [norm(r[column]) for r in records if r[column] is not None]
        targets = random.sample(values, 15) + [min(values), max(values)]       # present
        targets += ["zzz"] if isinstance(values[0], str) else [min(values) - 5, max(values) + 5, -1]
        if column == "vote_average":
            targets.append(5.55)                                               # absent decimal
        for algo in SEARCH_ALGORITHMS:
            for target in targets:
                try:
                    out = search_records(records, column, algo, target)
                except ValueError:
                    refused += 1
                    continue
                expected = {r["id"] for r in records if r[column] is not None and norm(r[column]) == norm(target)}
                got = [r["id"] for r in out["records"]]
                checked += 1
                if set(got) != expected or len(got) != len(expected):
                    failures += 1
                    print(f"FAIL: {algo} on {column} target={target!r}: got {len(got)} expected {len(expected)}")
    print(f"Search: {checked} searches checked, {failures} failures, "
          f"{refused} correctly refused (interpolation on text)")


def search_edge_cases():
    failures = 0
    for algo in SEARCH_ALGORITHMS:
        for rows, target, expected in [
            ([], 5, 0), ([{"id": 0, "v": 5}], 5, 1), ([{"id": 0, "v": 5}], 4, 0),
            ([{"id": i, "v": 7} for i in range(500)], 7, 500),                 # all equal
            ([{"id": i, "v": 7} for i in range(500)], 8, 0),
            ([{"id": i, "v": i} for i in range(1000)], 0, 1),                  # first element
            ([{"id": i, "v": i} for i in range(1000)], 999, 1),                # last element
            ([{"id": i, "v": i} for i in range(1000)], 1000, 0),               # just past the end
            ([{"id": i, "v": i * i} for i in range(1000)], 250000, 1),         # skewed values
        ]:
            got = len(search_records(rows, "v", algo, target)["records"])
            if got != expected:
                failures += 1
                print(f"FAIL edge: {algo} rows={len(rows)} target={target}: got {got} expected {expected}")
    print(f"Search edge cases: {failures} failures")


def filter_correctness():
    failures = 0
    words = ["".join(random.choices("abcAB ", k=random.randint(0, 8))) for _ in range(3000)]
    for pattern in ["a", "ab", "b ", "AB", "abc", "zz", "a b"]:
        p = pattern.lower()
        for w in words:
            lw = w.lower()
            if contains_text(lw, p) != (p in lw) or starts_with_text(lw, p) != lw.startswith(p) \
                    or ends_with_text(lw, p) != lw.endswith(p):
                failures += 1
    records = make_records(2000)
    for op, test in [("greater than", lambda c: c > 2000), ("greater or equal", lambda c: c >= 2000),
                     ("less than", lambda c: c < 1990), ("less or equal", lambda c: c <= 1990),
                     ("equals", lambda c: c == 2000)]:
        got = {r["id"] for r in filter_records(records, "release_year", op, 2000 if op != "less than" and op != "less or equal" else 1990)["records"]}
        value = 1990 if op.startswith("less") else 2000
        exp = {r["id"] for r in records if test(r["release_year"])}
        if got != exp:
            failures += 1
            print("FAIL numeric filter", op)
    got = {r["id"] for r in filter_records(records, "release_year", "between", 2010, 1990)["records"]}
    if got != {r["id"] for r in records if 1990 <= r["release_year"] <= 2010}:
        failures += 1
        print("FAIL between")
    got = {r["id"] for r in filter_records(records, "title", "contains", "AB")["records"]}
    if got != {r["id"] for r in records if "ab" in r["title"].lower()}:
        failures += 1
        print("FAIL contains on records")
    got = {r["id"] for r in filter_records(records, "budget", "greater than", 0)["records"]}
    if got != {r["id"] for r in records if r["budget"] is not None}:
        failures += 1
        print("FAIL: empty budgets must never match")
    print(f"Filters: {failures} failures")


def comparison_demo(n=16000):
    """How many comparisons does each algorithm need on 16,000 sorted values?"""
    records = [{"id": i, "v": i * 3} for i in range(n)]          # evenly spread, already sorted
    skewed = [{"id": i, "v": i * i} for i in range(n)]            # heavily skewed
    print(f"\nComparisons to find ONE value among {n:,} rows:")
    print(f"  {'':22}{'evenly spread':>15}{'skewed (i*i)':>15}")
    for algo in SEARCH_ALGORITHMS:
        a = search_records(records, "v", algo, 3 * 11111)
        b = search_records(skewed, "v", algo, 11111 * 11111)
        assert a["matches"] == 1 and b["matches"] == 1
        print(f"  {algo:22}{a['comparisons']:>15,}{b['comparisons']:>15,}")


if __name__ == "__main__":
    search_correctness()
    search_edge_cases()
    filter_correctness()
    comparison_demo()
