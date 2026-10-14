"""composite.py - combine several conditions with AND, OR and NOT.

HOW IT WORKS
------------
1. Every condition (e.g. "Genres contains drama") is run on its own over the full
   dataset. 'equals' conditions use the chosen search algorithm; every other operator
   scans the rows. Each condition gives a SET of the movie ids that match it.
2. The sets are combined:
       NOT  ->  all ids minus the set        (so a movie with an EMPTY cell does match
                                              "NOT genres contains drama")
       AND  ->  intersection of two sets     (ids in both)
       OR   ->  union of two sets            (ids in either)
3. AND is evaluated before OR (like multiplication before addition):
       A OR B AND C   means   A OR (B AND C)
   So the conditions are split into OR-groups, each group is an AND of conditions.

A term is a dict: connector ("AND"/"OR", ignored for the first term), negate (bool),
column, kind ("text"/"int"/"float"), operator, value / value2 (typed), text / text2
(what the user typed, for display).
"""
import time

from filters import filter_records
from searching import SEARCH_ALGORITHMS, search_records


def split_into_or_groups(terms):
    """[A, AND B, OR C, AND D] -> [[A, B], [C, D]]"""
    groups = []
    for i, term in enumerate(terms):
        if i == 0 or term["connector"] == "OR":
            groups.append([term])
        else:
            groups[-1].append(term)
    return groups


def condition_text(term, titles):
    title = titles[term["column"]]
    if term["operator"] == "between":
        return f"{title} between '{term['text']}' and '{term['text2']}'"
    return f"{title} {term['operator']} '{term['text']}'"


def term_text(term, titles):
    text = condition_text(term, titles)
    return f"NOT ({text})" if term["negate"] else text


def describe(terms, titles):
    """The whole expression with brackets showing how AND/OR are grouped."""
    groups = split_into_or_groups(terms)
    parts = []
    for group in groups:
        joined = " AND ".join(term_text(t, titles) for t in group)
        parts.append(f"({joined})" if len(group) > 1 and len(groups) > 1 else joined)
    return " OR ".join(parts)


def _run_condition(records, term, algorithm):
    if term["operator"] == "equals":
        chosen = algorithm
        # interpolation search only works on numbers; use binary search for text conditions
        if SEARCH_ALGORITHMS[chosen]["numeric_only"] and term["kind"] == "text":
            chosen = "Binary Search"
        return search_records(records, term["column"], chosen, term["value"])
    return filter_records(records, term["column"], term["operator"], term["value"], term["value2"])


def evaluate(records, terms, algorithm, titles):
    """Apply the composite filter to `records`. Returns a dict shaped like the single
    search result (records, matches, time_ms, comparisons, rows, presort) plus
    `expression` and `details` (one line per condition)."""
    if not terms:
        raise ValueError("Add at least one condition.")

    all_ids = {r["id"] for r in records}
    matched = set()
    comparisons = 0
    time_ms = 0.0
    presort = {"algorithm": "Merge Sort", "time_ms": 0.0, "comparisons": 0, "count": 0}
    details = []

    for group in split_into_or_groups(terms):
        group_ids = None
        for term in group:
            result = _run_condition(records, term, algorithm)
            ids = {r["id"] for r in result["records"]}
            comparisons += result["comparisons"]
            time_ms += result["time_ms"]
            if result["presort"]:
                presort["time_ms"] += result["presort"]["time_ms"]
                presort["comparisons"] += result["presort"]["comparisons"]
                presort["count"] += 1
            line = (f"{condition_text(term, titles)}: {result['matches']:,} matches "
                    f"({result['algorithm']}, {result['comparisons']:,} comparisons)")

            start = time.perf_counter()                 # combining sets also counts as time
            if term["negate"]:
                ids = all_ids - ids                     # NOT
                line = "NOT " + line + f" -> {len(ids):,} remain"
            group_ids = ids if group_ids is None else (group_ids & ids)     # AND
            time_ms += (time.perf_counter() - start) * 1000
            details.append(line)
        start = time.perf_counter()
        matched |= group_ids                                                # OR
        time_ms += (time.perf_counter() - start) * 1000

    found = [r for r in records if r["id"] in matched]       # keep the current row order
    return {
        "records": found,
        "matches": len(found),
        "time_ms": time_ms,
        "comparisons": comparisons,
        "rows": len(records),
        "presort": presort if presort["count"] else None,
        "expression": describe(terms, titles),
        "details": details,
        "algorithm": "Composite filter",
    }
