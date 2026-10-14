"""test_sorting.py - checks every algorithm for correctness, stability and speed.
Run:  python test_sorting.py
(Python's sorted() is used ONLY here, as the answer key. The project itself never uses it.)"""
import random
import string
import time

from sorting import ALGORITHMS, sort_records

random.seed(1)


def make_movies(n):
    movies = []
    for i in range(n):
        movies.append({
            "id": random.randint(2, 1_500_000) + i * 0,        # wide range
            "title": "".join(random.choices(string.ascii_letters + " ", k=random.randint(3, 12))),
            "release_year": random.randint(1980, 2025),         # many duplicates
            "vote_average": round(random.uniform(0, 10), 1),    # float, many duplicates
            "original_language": random.choice(["en"] * 6 + ["fr", "ja", "es"]),
            "budget": random.choice([None, None, random.randint(1, 300_000_000)]),
        })
    for i, m in enumerate(movies):
        m["row"] = i                                            # original position, for stability check
    return movies


def expected_order(movies, column, descending):
    present = [m for m in movies if m[column] is not None]
    missing = [m for m in movies if m[column] is None]
    key = (lambda m: m[column].lower()) if isinstance(present[0][column], str) else (lambda m: m[column])
    return sorted(present, key=key, reverse=descending) + missing   # Python's sort is stable


def correctness(n=1500):
    movies = make_movies(n)
    columns = ["title", "release_year", "vote_average", "original_language", "budget"]
    failures, checked, refused = 0, 0, 0
    for name, info in ALGORITHMS.items():
        for col in columns:
            for desc in (False, True):
                try:
                    out = sort_records(movies, col, name, desc)["records"]
                except ValueError:
                    refused += 1          # e.g. radix on text, counting on floats/huge range
                    continue
                exp = expected_order(movies, col, desc)
                if isinstance(exp[0][col], str):
                    key = lambda m: m[col].lower() if m[col] is not None else None
                else:
                    key = lambda m: m[col]
                keys_ok = [key(m) for m in out] == [key(m) for m in exp]
                stable_ok = (not info["stable"]) or [m["row"] for m in out] == [m["row"] for m in exp]
                checked += 1
                if not (keys_ok and stable_ok):
                    failures += 1
                    print(f"FAIL: {name} on {col} desc={desc} keys_ok={keys_ok} stable_ok={stable_ok}")
    print(f"Correctness: {checked} runs checked, {failures} failures, "
          f"{refused} combinations correctly refused (algorithm can't handle that column)")


def speed(n_big=16000, n_small=3000):
    print(f"\nSpeed (column: release_year, ints with many duplicates)")
    big, small = make_movies(n_big), make_movies(n_small)
    for name, info in ALGORITHMS.items():
        slow = info["average"] == "O(n²)" and name != "Bucket Sort"
        data, size = (small, n_small) if slow else (big, n_big)
        r = sort_records(data, "release_year", name)
        print(f"  {name:15} n={size:6}  {r['time_ms']:9.1f} ms  "
              f"comparisons={r['comparisons']:>11,}  swaps={r['swaps']:>10,}")


def edge_cases(n_small=2000, n_big=16000):
    """Inputs that break naive implementations: sorted, reversed, all equal,
    mostly equal, tiny and empty lists. The slow O(n^2) sorts get the smaller size."""
    def build(values):
        return [{"v": v, "row": i} for i, v in enumerate(values)]

    def datasets(n):
        return {
            "sorted": list(range(n)),
            "reversed": list(range(n, 0, -1)),
            "all equal": [7] * n,
            "90% equal": [5 if random.random() < 0.9 else random.randint(0, 100) for _ in range(n)],
            "3 items": [3, 1, 2],
            "1 item": [4],
            "empty": [],
        }

    runs = failures = 0
    for name, info in ALGORITHMS.items():
        n = n_small if info["average"] == "O(n²)" else n_big
        for label_, values in datasets(n).items():
            data = build(values)
            for desc in (False, True):
                try:
                    out = sort_records(data, "v", name, desc)["records"]
                except Exception as e:          # includes RecursionError
                    failures += 1
                    print(f"FAIL (crash): {name} on '{label_}' desc={desc}: {type(e).__name__}: {e}")
                    continue
                exp = sorted(data, key=lambda m: m["v"], reverse=desc)
                ok = [m["v"] for m in out] == [m["v"] for m in exp]
                if info["stable"]:
                    ok = ok and [m["row"] for m in out] == [m["row"] for m in exp]
                runs += 1
                if not ok:
                    failures += 1
                    print(f"FAIL: {name} on '{label_}' desc={desc}")
    print(f"Edge cases: {runs} runs checked, {failures} failures")


def multi_level_correctness(n=3000, tries=40):
    """Random multi-column sorts checked against a full multi-column comparison."""
    from functools import cmp_to_key
    from sorting import multi_level_sort

    movies = make_movies(n)
    kinds = {"title": "text", "original_language": "text", "release_year": "int",
             "vote_average": "float", "budget": "int"}
    specs = [
        [("release_year", False), ("vote_average", True)],
        [("original_language", False), ("release_year", True), ("title", False)],
        [("budget", True), ("original_language", False)],
        [("title", True), ("release_year", False), ("vote_average", False)],
    ]

    def compatible(name, column):
        info = ALGORITHMS[name]
        if info["kind"] == "comparison":
            return True
        return kinds[column] != "text" and not (info["integers_only"] and kinds[column] == "float")

    runs = failures = skipped = 0
    for spec in specs:
        def cmp_rows(a, b, spec=spec):
            for column, desc in spec:
                va, vb = norm_val(a[column]), norm_val(b[column])
                if va is None and vb is None:
                    continue
                if va is None:
                    return 1                      # empty values always last
                if vb is None:
                    return -1
                if va == vb:
                    continue
                smaller = va < vb
                return (1 if smaller else -1) if desc else (-1 if smaller else 1)
            return 0
        expected = sorted(movies, key=cmp_to_key(cmp_rows))      # stable answer key

        for _ in range(tries):
            levels = []
            for number, (column, desc) in enumerate(spec):
                last = number == len(spec) - 1
                options = [a for a, i in ALGORITHMS.items()
                           if compatible(a, column) and (last or i["stable"])]
                levels.append((column, random.choice(options), desc))
            try:
                out = multi_level_sort(movies, levels)["records"]
            except ValueError:
                skipped += 1                       # e.g. counting sort on a huge range
                continue
            all_stable = all(ALGORITHMS[a]["stable"] for _, a, _ in levels)
            keys = lambda m: tuple(norm_val(m[c]) for c, _ in spec)
            ok = [keys(m) for m in out] == [keys(m) for m in expected]
            if all_stable:                         # ties must also keep their original order
                ok = ok and [m["row"] for m in out] == [m["row"] for m in expected]
            runs += 1
            if not ok:
                failures += 1
                print(f"FAIL multi-level: {levels}")

    # an unstable algorithm on a NON-last level must be refused
    refused = False
    try:
        multi_level_sort(movies, [("release_year", "Quick Sort", False), ("title", "Merge Sort", False)])
    except ValueError:
        refused = True
    if not refused:
        failures += 1
        print("FAIL: unstable algorithm on level 1 was not refused")
    print(f"Multi-level: {runs} runs checked, {failures} failures, {skipped} skipped "
          f"(algorithm can't handle that column), unstable-on-level-1 refused: {refused}")


def norm_val(v):
    return v.lower() if isinstance(v, str) else v


if __name__ == "__main__":
    correctness()
    edge_cases()
    multi_level_correctness()
    speed()
