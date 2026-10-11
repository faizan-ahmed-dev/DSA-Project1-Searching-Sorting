"""sorting.py - every sorting algorithm is written from scratch (no sorted()/.sort()).

The 8 class algorithms (Insertion, Selection, Bubble, Merge, Quick, Counting, Radix,
Bucket) are YOUR code, with the same names and the same logic. Heap Sort and Shell
Sort are the 2 extra algorithms.

HOW THE PIECES FIT
------------------
sort_records(records, column, algorithm, descending)   <- the UI calls only this
    1. splits the records into "has a value" and "missing value"
    2. builds a list of (key, record) pairs, e.g. ("the godfather", {...})
    3. runs the chosen algorithm on the pairs, timing it
    4. puts the missing-value records at the END (both ascending and descending)

WHAT CHANGED FROM YOUR ORIGINAL CODE (look for these marks in the comments)
---------------------------------------------------------------------------
  "was:"      the comparison as you originally wrote it, next to the new version
  "ADDED:"    a counter line (comparisons / swaps)
  "CHANGED:"  a real change to the logic, with the reason
Every algorithm now takes two extra parameters, before and stats (explained below),
and works on (key, record) pairs, so the key is item[0].

THE before() FUNCTION
---------------------
Your code compared values directly, e.g.  array[j] > key.  We replace that with
before(a, b), which asks "should a come strictly before b?" and also adds 1 to the
comparison counter.   array[j] > key   becomes   before(key, array[j]).
For descending order before() flips its test (a > b instead of a < b), so the
algorithms never need to know which direction they sort.

WHAT WE COUNT
-------------
comparisons : number of times before() is called
swaps       : number of times an element is exchanged OR moved in the array
              (bubble/selection/quick/heap: one exchange = 1;
               insertion/shell: one shift = 1;
               merge: one element written back into the array = 1;
               counting/radix/bucket: one element placed into its output slot = 1)
Counting and radix sort never compare elements, so their comparison count is 0.

TWO KINDS OF ALGORITHM
----------------------
"comparison": works on any column (text, numbers).
"numeric":    counting / radix / bucket need numbers. For descending order the
              keys are negated and sorted ascending (so ties keep original order).
"""
import random
import time

MAX_COUNTING_RANGE = 2_000_000   # counting sort allocates (max - min + 1) counters


class Stats:
    def __init__(self):
        self.comparisons = 0
        self.swaps = 0


def make_before(stats, descending=False):
    """Return the comparison function that also counts comparisons."""
    if descending:
        def before(a, b):
            stats.comparisons += 1
            return a[0] > b[0]
        return before
    def before(a, b):
        stats.comparisons += 1
        return a[0] < b[0]
    return before


# =====================================================================
# YOUR 8 ALGORITHMS
# =====================================================================

def InsertionSort(array, start, end, before, stats):
    # Like sorting playing cards in your hand
    for i in range(start + 1, end + 1):
        key = array[i]          # the card we want to place
        j = i - 1

        # Move bigger values one step to the right
        # was: while j >= start and array[j] > key:
        while j >= start and before(key, array[j]):
            array[j + 1] = array[j]
            stats.swaps = stats.swaps + 1            # ADDED: count one shift
            j = j - 1

        # Put the key in the empty spot
        array[j + 1] = key


def Merge(array, p, q, r, before, stats):
    # Left half is array[p..q], right half is array[q+1..r]. Both are already sorted.
    left = []
    for i in range(p, q + 1):
        left.append(array[i])

    right = []
    for i in range(q + 1, r + 1):
        right.append(array[i])

    i = 0       # position in left
    j = 0       # position in right
    k = p       # position in the main array where we write

    # Take the smaller front value each time
    while i < len(left) and j < len(right):
        # was: if left[i] <= right[j]:
        # "left <= right" is the same as "right is NOT strictly before left".
        # On a tie we take from the LEFT half, which is what makes merge sort stable.
        if not before(right[j], left[i]):
            array[k] = left[i]
            i = i + 1
        else:
            array[k] = right[j]
            j = j + 1
        stats.swaps = stats.swaps + 1                # ADDED: count one write
        k = k + 1

    # One side may still have values left, copy them
    while i < len(left):
        array[k] = left[i]
        stats.swaps = stats.swaps + 1                # ADDED
        i = i + 1
        k = k + 1

    while j < len(right):
        array[k] = right[j]
        stats.swaps = stats.swaps + 1                # ADDED
        j = j + 1
        k = k + 1


def MergeSort(array, start, end, before, stats):
    # Only sort if there are at least 2 elements
    if start < end:
        middle = (start + end) // 2
        MergeSort(array, start, middle, before, stats)       # sort left half
        MergeSort(array, middle + 1, end, before, stats)     # sort right half
        Merge(array, start, middle, end, before, stats)      # join the two halves


def BubbleSort(array, start, end, before, stats):
    # Each pass pushes the biggest remaining value to the end
    for i in range(end, start, -1):
        swapped = False

        for j in range(start, i):
            # was: if array[j] > array[j + 1]:
            if before(array[j + 1], array[j]):
                # swap neighbours
                temp = array[j]
                array[j] = array[j + 1]
                array[j + 1] = temp
                stats.swaps = stats.swaps + 1        # ADDED
                swapped = True

        # If nothing was swapped, the array is already sorted
        if swapped == False:
            break


def SelectionSort(array, start, end, before, stats):
    for i in range(start, end):
        # Find the smallest value in the unsorted part
        smallest_index = i

        for j in range(i + 1, end + 1):
            # was: if array[j] < array[smallest_index]:
            if before(array[j], array[smallest_index]):
                smallest_index = j

        # Swap it into position i
        # CHANGED: only swap (and count) when the smallest is not already at i,
        # otherwise we would count "swaps" that move nothing.
        if smallest_index != i:
            temp = array[i]
            array[i] = array[smallest_index]
            array[smallest_index] = temp
            stats.swaps = stats.swaps + 1            # ADDED


# CHANGED (Partition + QuickSort): your version is the textbook one (last element
# as pivot, Lomuto partition, "<="). It is correct, but on our data it breaks:
#   * if the column is already sorted, or has many equal values (language is mostly
#     "en"), every partition is lopsided -> n levels of recursion -> Python raises
#     RecursionError at ~1000 levels (we sort 16,000 rows), and it becomes O(n^2).
# Two fixes, both small:
#   1. pick the pivot at RANDOM, so no input is reliably bad
#   2. split into THREE parts [smaller | equal | larger] and never touch the
#      equal part again, so thousands of equal values cost almost nothing.
def Partition(A, p, r, before, stats):
    pivot = A[random.randint(p, r)]     # CHANGED: random pivot (was A[r])
    lt = p      # A[p .. lt-1]   are smaller than the pivot
    i = p       # A[lt .. i-1]   are equal to the pivot
    gt = r      # A[gt+1 .. r]   are larger than the pivot; A[i .. gt] not looked at yet

    while i <= gt:
        if before(A[i], pivot):                 # smaller: move it into the left part
            if lt != i:
                A[lt], A[i] = A[i], A[lt]
                stats.swaps = stats.swaps + 1   # ADDED
            lt = lt + 1
            i = i + 1
        elif before(pivot, A[i]):               # larger: move it into the right part
            A[i], A[gt] = A[gt], A[i]
            stats.swaps = stats.swaps + 1       # ADDED
            gt = gt - 1                         # (don't advance i: the new A[i] is unchecked)
        else:                                   # equal to pivot: leave it in the middle
            i = i + 1

    return lt, gt       # CHANGED: returns TWO positions (was one: i+1)


def QuickSort(A, p, r, before, stats):
    if p < r:
        lt, gt = Partition(A, p, r, before, stats)
        QuickSort(A, p, lt - 1, before, stats)      # sort the "smaller" part
        QuickSort(A, gt + 1, r, before, stats)      # sort the "larger" part
        # the "equal" part A[lt..gt] is already in its final place


def CountingSort(A, before, stats):
    if len(A) == 0:
        return A

    # CHANGED: A holds (key, record) pairs, so the number is A[j][0]
    minimum = min(item[0] for item in A)
    maximum = max(item[0] for item in A)

    k = maximum - minimum + 1

    # ADDED: a column like budget goes up to hundreds of millions, so C would need
    # hundreds of millions of counters. Refuse instead of freezing the computer.
    if k > MAX_COUNTING_RANGE:
        raise ValueError(f"value range is {k:,}; counting sort supports at most "
                         f"{MAX_COUNTING_RANGE:,}. Use radix sort for this column.")

    C = [0] * k
    B = [0] * len(A)

    # Count Occurrences
    for j in range(len(A)):
        C[A[j][0] - minimum] = C[A[j][0] - minimum] + 1

    # Calculate cumulative counts
    for i in range(1, k):
        C[i] = C[i] + C[i - 1]

    # Output Array (right to left keeps equal items in their original order = stable)
    for j in range(len(A) - 1, -1, -1):
        index = A[j][0] - minimum
        B[C[index] - 1] = A[j]
        C[index] = C[index] - 1
        stats.swaps = stats.swaps + 1                # ADDED: one element placed

    return B


def CountingSortByDigit(A, place, stats):
    n = len(A)
    B = [0] * n
    C = [0] * 10

    # Count occurrences of each digit
    for j in range(n):
        digit = (A[j][0] // place) % 10              # CHANGED: A[j][0] (was A[j])
        C[digit] = C[digit] + 1

    # Calculate cumulative counts
    for i in range(1, 10):
        C[i] = C[i] + C[i - 1]

    # Build output array from right to left
    for j in range(n - 1, -1, -1):
        digit = (A[j][0] // place) % 10
        B[C[digit] - 1] = A[j]
        C[digit] = C[digit] - 1
        stats.swaps = stats.swaps + 1                # ADDED

    return B


def RadixSort(A, before, stats):
    if len(A) == 0:
        return A

    # CHANGED: your version only works for numbers >= 0. Descending order makes
    # our keys negative (we negate them), so subtract the minimum first: every key
    # becomes >= 0, and the ORDER of the keys does not change.
    minimum = min(item[0] for item in A)
    A = [(item[0] - minimum, item[1]) for item in A]

    maximum = max(item[0] for item in A)

    place = 1

    while maximum // place > 0:
        A = CountingSortByDigit(A, place, stats)
        place = place * 10

    return A


def BucketSort(A, before, stats):
    n = len(A)
    if n < 2:
        return A

    minimum = min(item[0] for item in A)
    maximum = max(item[0] for item in A)
    if minimum == maximum:          # ADDED: all keys equal, already sorted (avoids divide by 0)
        return A

    # Create n empty buckets
    B = []
    for i in range(n):
        B.append([])

    # Distribute elements into buckets
    for i in range(n):
        # CHANGED: your formula int(n * A[i]) assumes every value is between 0 and 1.
        # Our columns are not (years, ratings, budgets...), so first scale the key
        # into the range 0..1, then use your formula unchanged.
        scaled = (A[i][0] - minimum) / (maximum - minimum)
        index = int(n * scaled)

        # Handle the edge case where scaled = 1 (your original comment)
        if index == n:
            index = n - 1

        B[index].append(A[i])
        stats.swaps = stats.swaps + 1                # ADDED: one element placed

    # Sort each bucket using Insertion Sort
    # CHANGED: we use the one InsertionSort above (your file had two functions with
    # the same name, so the second silently replaced the first).
    for i in range(n):
        InsertionSort(B[i], 0, len(B[i]) - 1, before, stats)

    # Concatenate all buckets
    result = []
    for i in range(n):
        for j in range(len(B[i])):
            result.append(B[i][j])

    return result


# =====================================================================
# THE 2 EXTRA ALGORITHMS (same before/stats style as above)
# =====================================================================

def heap_sort(a, before, stats):
    """EXTRA 1. Build a max-heap (largest item at index 0), then repeatedly
    swap the root to the end of the array and repair the heap.
    Heap layout: children of index i are 2i+1 and 2i+2."""
    n = len(a)

    def sift_down(root, end):
        while True:
            child = 2 * root + 1
            if child >= end:
                break
            if child + 1 < end and before(a[child], a[child + 1]):
                child += 1                            # pick the larger child
            if before(a[root], a[child]):             # root smaller than child -> swap down
                a[root], a[child] = a[child], a[root]
                stats.swaps += 1
                root = child
            else:
                break

    for i in range(n // 2 - 1, -1, -1):               # build heap
        sift_down(i, n)
    for end in range(n - 1, 0, -1):                   # extract max one by one
        a[0], a[end] = a[end], a[0]
        stats.swaps += 1
        sift_down(0, end)
    return a


def shell_sort(a, before, stats):
    """EXTRA 2. Insertion sort that first compares items far apart (gap), then
    shrinks the gap down to 1. Big gaps move items long distances cheaply, so
    the final gap-1 pass (plain insertion sort) has little left to do.
    Gaps: ..., 40, 13, 4, 1 (Knuth: gap = 3*gap + 1)."""
    n = len(a)
    gap = 1
    while gap < n // 3:
        gap = 3 * gap + 1
    while gap >= 1:
        for i in range(gap, n):
            x = a[i]
            j = i
            while j >= gap and before(x, a[j - gap]):
                a[j] = a[j - gap]
                stats.swaps += 1
                j -= gap
            a[j] = x
        gap //= 3
    return a


# =====================================================================
# ADAPTERS - give your functions the one shape the registry/UI expects:
#            function(list_of_pairs, before, stats) -> sorted list
# =====================================================================

def run_insertion(a, before, stats):
    InsertionSort(a, 0, len(a) - 1, before, stats)
    return a


def run_selection(a, before, stats):
    SelectionSort(a, 0, len(a) - 1, before, stats)
    return a


def run_bubble(a, before, stats):
    BubbleSort(a, 0, len(a) - 1, before, stats)
    return a


def run_merge(a, before, stats):
    MergeSort(a, 0, len(a) - 1, before, stats)
    return a


def run_quick(a, before, stats):
    QuickSort(a, 0, len(a) - 1, before, stats)
    return a


# CountingSort, RadixSort and BucketSort already have the right shape.


# =====================================================================
# REGISTRY - the UI dropdown and the Benchmark button read from this
# =====================================================================
ALGORITHMS = {
    "Bubble Sort":    dict(func=run_bubble,     kind="comparison", stable=True,
                           best="O(n)",       average="O(n²)",       worst="O(n²)",       space="O(1)"),
    "Selection Sort": dict(func=run_selection,  kind="comparison", stable=False,
                           best="O(n²)",      average="O(n²)",       worst="O(n²)",       space="O(1)"),
    "Insertion Sort": dict(func=run_insertion,  kind="comparison", stable=True,
                           best="O(n)",       average="O(n²)",       worst="O(n²)",       space="O(1)"),
    "Merge Sort":     dict(func=run_merge,      kind="comparison", stable=True,
                           best="O(n log n)", average="O(n log n)",  worst="O(n log n)",  space="O(n)"),
    "Quick Sort":     dict(func=run_quick,      kind="comparison", stable=False,
                           best="O(n log n)", average="O(n log n)",  worst="O(n²)",       space="O(log n)"),
    "Heap Sort":      dict(func=heap_sort,      kind="comparison", stable=False,
                           best="O(n log n)", average="O(n log n)",  worst="O(n log n)",  space="O(1)"),
    "Shell Sort":     dict(func=shell_sort,     kind="comparison", stable=False,
                           best="O(n log n)", average="~O(n^1.3)",   worst="O(n^1.5)",    space="O(1)"),
    "Counting Sort":  dict(func=CountingSort,   kind="numeric", integers_only=True, stable=True,
                           best="O(n + k)",   average="O(n + k)",    worst="O(n + k)",    space="O(n + k)"),
    "Radix Sort":     dict(func=RadixSort,      kind="numeric", integers_only=True, stable=True,
                           best="O(d·n)",     average="O(d·n)",      worst="O(d·n)",      space="O(n + b)"),
    "Bucket Sort":    dict(func=BucketSort,     kind="numeric", integers_only=False, stable=True,
                           best="O(n + k)",   average="O(n + k)",    worst="O(n²)",       space="O(n + k)"),
}


def label(name):
    """Text for the dropdown, e.g. 'Merge Sort  |  O(n log n) avg, O(n log n) worst  |  stable'."""
    info = ALGORITHMS[name]
    return f"{name}  |  {info['average']} avg, {info['worst']} worst  |  {'stable' if info['stable'] else 'unstable'}"


def _check_numeric(items, integers_only, name):
    for key, _ in items:
        if isinstance(key, bool) or not isinstance(key, (int, float)):
            raise ValueError(f"{name} only works on numeric columns.")
        if integers_only and not isinstance(key, int):
            raise ValueError(f"{name} only works on integer columns (this one has decimals).")


def sort_records(records, column, algorithm, descending=False):
    """Sort a list of dict records by one column.

    Returns a dict: records, time_ms, comparisons, swaps, algorithm.
    Raises ValueError if the algorithm can't handle this column
    (e.g. radix sort on a text column)."""
    if algorithm not in ALGORITHMS:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    info = ALGORITHMS[algorithm]

    present, missing = [], []
    for rec in records:
        value = rec.get(column)
        if value is None or value == "":
            missing.append(rec)                       # empty cells always go last
        else:
            if isinstance(value, str):
                value = value.lower()                 # case-insensitive text sorting
            present.append((value, rec))

    stats = Stats()
    if info["kind"] == "numeric":
        _check_numeric(present, info["integers_only"], algorithm)
        if descending:
            present = [(-k, rec) for k, rec in present]
        before = make_before(stats, descending=False)  # keys already negated
    else:
        before = make_before(stats, descending)

    start = time.perf_counter()
    result = info["func"](present, before, stats)
    time_ms = (time.perf_counter() - start) * 1000

    return {
        "records": [rec for _, rec in result] + missing,
        "time_ms": time_ms,
        "comparisons": stats.comparisons,
        "swaps": stats.swaps,
        "algorithm": algorithm,
    }