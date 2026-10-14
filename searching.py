"""searching.py - the search algorithms (written from scratch).

Linear Search and Binary Search are from class. Jump Search and Interpolation
Search are the two extras.

WHAT A "SEARCH" DOES HERE
-------------------------
search_records(records, column, algorithm, target) finds EVERY record whose value in
that column equals the target (text is compared ignoring upper/lower case). The
algorithms themselves work on a plain list of keys and return the INDEXES of the
matches:      algorithm(keys, target, stats) -> [index, index, ...]

SORTED DATA
-----------
Binary, Jump and Interpolation search only work on data sorted ascending. If the
column is not already sorted, search_records() first sorts a COPY with Merge Sort
(from sorting.py). That pre-sort is reported separately and is NOT included in the
search time, so you can see how cheap the search itself is.

WHAT WE COUNT
-------------
comparisons = number of three-way comparisons compare(a, b) -> smaller / equal / bigger.
Linear search compares every key once, so it always uses n comparisons (it must
look at every row to find ALL matches). Binary search needs about log2(n).

DUPLICATES
----------
Many columns repeat values (a year, a language). Binary and interpolation search
land on ONE matching row; collect_around() then walks left and right to collect the
other equal rows. Jump search lands on the FIRST matching row and walks right.
"""
import math
import time

from sorting import sort_records


class SearchStats:
    def __init__(self):
        self.comparisons = 0


def compare(a, b, stats):
    """Three-way comparison, counted as ONE comparison: -1 if a < b, 0 if equal, 1 if a > b."""
    stats.comparisons += 1
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def collect_around(keys, target, found, stats):
    """keys[found] equals the target. Walk left, then right, while keys still equal it."""
    left = found
    while left > 0 and compare(keys[left - 1], target, stats) == 0:
        left -= 1
    right = found
    while right < len(keys) - 1 and compare(keys[right + 1], target, stats) == 0:
        right += 1
    return list(range(left, right + 1))


# =====================================================================
# THE FOUR ALGORITHMS
# =====================================================================

def linear_search(keys, target, stats):
    """Look at every key from left to right. Works on unsorted data."""
    matches = []
    for i in range(len(keys)):
        if compare(keys[i], target, stats) == 0:
            matches.append(i)
    return matches


def binary_search(keys, target, stats):
    """Needs SORTED keys. Look at the middle: if it is the target we are done; if the
    target is bigger, throw away the left half; if smaller, throw away the right half.
    Each step halves the range, so about log2(n) steps."""
    low = 0
    high = len(keys) - 1
    found = -1
    while low <= high:
        mid = (low + high) // 2
        result = compare(keys[mid], target, stats)
        if result == 0:
            found = mid
            break
        elif result < 0:            # keys[mid] is smaller -> target is in the right half
            low = mid + 1
        else:                       # keys[mid] is bigger  -> target is in the left half
            high = mid - 1
    if found == -1:
        return []
    return collect_around(keys, target, found, stats)


def jump_search(keys, target, stats):
    """EXTRA 1. Needs SORTED keys. Jump ahead in blocks of sqrt(n) until the LAST key
    of a block is >= the target (so the target can only be inside that block), then
    scan that one block with linear search. About 2*sqrt(n) steps."""
    n = len(keys)
    if n == 0:
        return []
    step = math.isqrt(n)            # block size
    prev = 0
    curr = step
    # jump while the last key of the current block is still smaller than the target
    while compare(keys[min(curr, n) - 1], target, stats) < 0:
        prev = curr
        curr = curr + step
        if prev >= n:               # jumped past the end: target is bigger than everything
            return []
    # linear scan inside the block [prev, curr) for the first key that is not smaller
    i = prev
    while i < min(curr, n) and compare(keys[i], target, stats) < 0:
        i += 1
    # collect every key equal to the target (they sit next to each other)
    matches = []
    while i < n and compare(keys[i], target, stats) == 0:
        matches.append(i)
        i += 1
    return matches


def interpolation_search(keys, target, stats):
    """EXTRA 2. Needs SORTED NUMERIC keys. Like binary search, but instead of always
    looking in the middle it GUESSES where the target is, the way you open a
    dictionary near the end when looking for 'zebra':
        pos = low + (target - keys[low]) / (keys[high] - keys[low]) * (high - low)
    Very fast (about log log n) when values are spread evenly, slow (up to n steps)
    when they are heavily skewed, e.g. budget or popularity."""
    low = 0
    high = len(keys) - 1
    found = -1
    while low <= high:
        # target outside the current range -> not present
        if compare(target, keys[low], stats) < 0 or compare(target, keys[high], stats) > 0:
            break
        # all keys in the range are equal -> avoid dividing by zero
        if compare(keys[low], keys[high], stats) == 0:
            if compare(keys[low], target, stats) == 0:
                found = low
            break
        pos = low + int((target - keys[low]) * (high - low) / (keys[high] - keys[low]))
        pos = max(low, min(high, pos))      # safety against rounding
        result = compare(keys[pos], target, stats)
        if result == 0:
            found = pos
            break
        elif result < 0:
            low = pos + 1
        else:
            high = pos - 1
    if found == -1:
        return []
    return collect_around(keys, target, found, stats)


# =====================================================================
# REGISTRY - the UI dropdown reads from this
# =====================================================================
SEARCH_ALGORITHMS = {
    "Linear Search":        dict(func=linear_search,        needs_sorted=False, numeric_only=False,
                                 best="O(n)*", average="O(n)", worst="O(n)"),
    "Binary Search":        dict(func=binary_search,        needs_sorted=True,  numeric_only=False,
                                 best="O(1)", average="O(log n)", worst="O(log n)"),
    "Jump Search":          dict(func=jump_search,          needs_sorted=True,  numeric_only=False,
                                 best="O(1)", average="O(√n)", worst="O(√n)"),
    "Interpolation Search": dict(func=interpolation_search, needs_sorted=True,  numeric_only=True,
                                 best="O(1)", average="O(log log n)", worst="O(n)"),
}
# * we collect ALL matches, so linear search always scans the whole column.


def search_label(name):
    info = SEARCH_ALGORITHMS[name]
    return f"{name}  |  {info['average']} avg, {info['worst']} worst"


def _build_items(records, column):
    """(key, record) for every record that has a value; text keys are lower-cased."""
    items = []
    for rec in records:
        value = rec.get(column)
        if value is None or value == "":
            continue                                  # empty cells never match
        if isinstance(value, str):
            value = value.lower()
        items.append((value, rec))
    return items


def _is_ascending(items):
    for i in range(1, len(items)):
        if items[i - 1][0] > items[i][0]:
            return False
    return True


def search_records(records, column, algorithm, target):
    """Find all records whose `column` equals `target`.

    Returns a dict: records, matches, time_ms, comparisons, algorithm, rows (number of
    rows searched) and presort (None, or a dict describing the Merge Sort that had to be
    done first). Raises ValueError if the algorithm cannot handle the column."""
    if algorithm not in SEARCH_ALGORITHMS:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    info = SEARCH_ALGORITHMS[algorithm]
    if isinstance(target, str):
        target = target.lower()

    items = _build_items(records, column)
    presort = None
    if info["needs_sorted"] and not _is_ascending(items):
        sorted_result = sort_records(records, column, "Merge Sort")
        items = _build_items(sorted_result["records"], column)
        presort = {"algorithm": "Merge Sort",
                   "time_ms": sorted_result["time_ms"],
                   "comparisons": sorted_result["comparisons"]}

    keys = [key for key, _ in items]
    if info["numeric_only"]:
        if isinstance(target, str) or not all(isinstance(k, (int, float)) for k in keys):
            raise ValueError(f"{algorithm} only works on numeric columns.")

    stats = SearchStats()
    start = time.perf_counter()
    indexes = info["func"](keys, target, stats)
    time_ms = (time.perf_counter() - start) * 1000

    found = [items[i][1] for i in indexes]
    return {
        "records": found,
        "matches": len(found),
        "time_ms": time_ms,
        "comparisons": stats.comparisons,
        "algorithm": algorithm,
        "rows": len(items),
        "presort": presort,
    }
