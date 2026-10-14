"""test_composite.py - checks AND / OR / NOT filters against a simple row-by-row answer key.
Run:  python test_composite.py"""
import random

from composite import describe, evaluate, split_into_or_groups
from filters import NUMERIC_OPERATORS, TEXT_OPERATORS
from searching import SEARCH_ALGORITHMS

random.seed(11)
TITLES = {"title": "Title", "genres": "Genres", "original_language": "Lang",
          "release_year": "Year", "vote_average": "Rating"}
KINDS = {"title": "text", "genres": "text", "original_language": "text",
         "release_year": "int", "vote_average": "float"}


def make_records(n=1500):
    return [{
        "id": i,
        "title": "".join(random.choices("abc ", k=random.randint(1, 6))),
        "genres": random.choice([None, "Drama", "Drama, Comedy", "Horror, Thriller", "Action"]),
        "original_language": random.choice(["en", "en", "fr", "ja"]),
        "release_year": random.randint(1990, 2010),
        "vote_average": round(random.uniform(0, 10), 1),
    } for i in range(n)]


def random_term(first):
    column = random.choice(list(TITLES))
    kind = KINDS[column]
    operator = random.choice(TEXT_OPERATORS if kind == "text" else NUMERIC_OPERATORS)
    if kind == "text":
        value = random.choice({"title": ["a", "ab", "b ", "abc"], "genres": ["drama", "thriller", "a", "comedy"],
                               "original_language": ["en", "fr", "e"]}[column])
        value2 = None
    elif kind == "int":
        value, value2 = random.randint(1992, 2008), random.randint(1992, 2008)
    else:
        value, value2 = round(random.uniform(2, 8), 1), round(random.uniform(2, 8), 1)
    return {"connector": "AND" if first else random.choice(["AND", "OR"]),
            "negate": random.random() < 0.35, "column": column, "kind": kind, "operator": operator,
            "value": value, "value2": value2 if operator == "between" else None,
            "text": str(value), "text2": str(value2)}


def oracle_term(rec, t):
    v = rec[t["column"]]
    if v is None or v == "":
        base = False
    elif t["kind"] == "text":
        s, p = v.lower(), t["value"].lower()
        base = {"equals": s == p, "contains": p in s, "starts with": s.startswith(p),
                "ends with": s.endswith(p)}[t["operator"]]
    else:
        x, y = t["value"], t["value2"]
        base = {"equals": v == x, "greater than": v > x, "greater or equal": v >= x,
                "less than": v < x, "less or equal": v <= x,
                "between": (min(x, y) <= v <= max(x, y)) if y is not None else False}[t["operator"]]
    return (not base) if t["negate"] else base


def oracle(rec, terms):
    # OR of ANDs
    result = False
    current = None
    for i, t in enumerate(terms):
        value = oracle_term(rec, t)
        if i == 0 or t["connector"] == "OR":
            if current is not None:
                result = result or current
            current = value
        else:
            current = current and value
    return result or current


def main():
    records = make_records()
    failures = 0
    runs = 0
    for _ in range(400):
        count = random.randint(1, 5)
        terms = [random_term(i == 0) for i in range(count)]
        algorithm = random.choice(list(SEARCH_ALGORITHMS))
        out = evaluate(records, terms, algorithm, TITLES)
        expected = [r["id"] for r in records if oracle(r, terms)]
        got = [r["id"] for r in out["records"]]
        runs += 1
        if got != expected:
            failures += 1
            print("FAIL:", out["expression"], f"got {len(got)} expected {len(expected)}")
    print(f"Composite filters: {runs} random expressions checked, {failures} failures")

    # precedence: A OR B AND C  ==  A OR (B AND C)
    a = {"connector": "AND", "negate": False, "column": "original_language", "kind": "text",
         "operator": "equals", "value": "fr", "value2": None, "text": "fr", "text2": ""}
    b = dict(a, connector="OR", value="en", text="en")
    c = dict(a, connector="AND", column="release_year", kind="int", operator="greater than",
             value=2000, text="2000")
    groups = split_into_or_groups([a, b, c])
    print("Grouping of 'A OR B AND C':", [[t["text"] for t in g] for g in groups])
    print("Described as:", describe([a, b, c], TITLES))
    assert len(groups) == 2 and len(groups[1]) == 2

    # NOT includes rows with an empty cell
    t = dict(a, column="genres", operator="contains", value="drama", text="drama", negate=True)
    out = evaluate(records, [t], "Binary Search", TITLES)
    empty = sum(1 for r in records if r["genres"] is None)
    included = sum(1 for r in out["records"] if r["genres"] is None)
    print(f"NOT genres contains 'drama': {out['matches']} rows, including all {included} of the "
          f"{empty} movies with no genre")
    assert included == empty


if __name__ == "__main__":
    main()
