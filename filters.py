"""filters.py - filter operators: contains / starts with / ends with / equals for text,
and equals / greater / less / between for numbers.

The text matching is written by hand (nested loops) instead of using Python's
`in`, startswith() and endswith(), so you can explain exactly how it works.
Text is compared ignoring upper/lower case. Empty cells never match.

A filter looks at every row once, so its comparisons count = rows examined.
(The 'equals' operator is handled by the search algorithms in searching.py.)
"""
import time

TEXT_OPERATORS = ["equals", "contains", "starts with", "ends with"]
NUMERIC_OPERATORS = ["equals", "greater than", "greater or equal",
                     "less than", "less or equal", "between"]


def parse_value(kind, text):
    """Turn what the user typed into the right type for the column.
    kind is "text", "int" or "float". Raises ValueError with a friendly message."""
    text = text.strip()
    if text == "":
        raise ValueError("Please enter a value to search for.")
    if kind == "text":
        return text
    cleaned = text.replace(",", "")
    try:
        return int(cleaned) if kind == "int" else float(cleaned)
    except ValueError:
        what = "a whole number" if kind == "int" else "a number"
        raise ValueError(f"'{text}' is not {what}.")


# ---------------------------------------------------------------------
# hand-written text matching (both arguments already lower-case)
# ---------------------------------------------------------------------
def contains_text(text, pattern):
    """Try every start position in text; at each one compare the pattern letter by letter."""
    n, m = len(text), len(pattern)
    for start in range(n - m + 1):
        j = 0
        while j < m and text[start + j] == pattern[j]:
            j += 1
        if j == m:                      # every letter matched
            return True
    return False


def starts_with_text(text, pattern):
    m = len(pattern)
    if m > len(text):
        return False
    for j in range(m):
        if text[j] != pattern[j]:
            return False
    return True


def ends_with_text(text, pattern):
    m, n = len(pattern), len(text)
    if m > n:
        return False
    offset = n - m                      # where the last m letters of text begin
    for j in range(m):
        if text[offset + j] != pattern[j]:
            return False
    return True


def build_matcher(operator, value, value2=None):
    """Return a function cell_value -> True/False for the chosen operator."""
    if isinstance(value, str):                                   # ----- text column
        pattern = value.lower()
        if operator == "equals":
            return lambda cell: cell.lower() == pattern
        if operator == "contains":
            return lambda cell: contains_text(cell.lower(), pattern)
        if operator == "starts with":
            return lambda cell: starts_with_text(cell.lower(), pattern)
        if operator == "ends with":
            return lambda cell: ends_with_text(cell.lower(), pattern)
    else:                                                        # ----- numeric column
        if operator == "equals":
            return lambda cell: cell == value
        if operator == "greater than":
            return lambda cell: cell > value
        if operator == "greater or equal":
            return lambda cell: cell >= value
        if operator == "less than":
            return lambda cell: cell < value
        if operator == "less or equal":
            return lambda cell: cell <= value
        if operator == "between":
            if value2 is None:
                raise ValueError("'between' needs two values.")
            low, high = (value, value2) if value <= value2 else (value2, value)
            return lambda cell: low <= cell <= high
    raise ValueError(f"Unknown operator: {operator}")


def filter_records(records, column, operator, value, value2=None):
    """Keep the records whose `column` passes the operator. Same result shape as
    search_records() so the UI can show both the same way."""
    matcher = build_matcher(operator, value, value2)
    matches = []
    rows = 0
    start = time.perf_counter()
    for rec in records:
        cell = rec.get(column)
        if cell is None or cell == "":
            continue                    # empty cells never match
        rows += 1
        if matcher(cell):
            matches.append(rec)
    time_ms = (time.perf_counter() - start) * 1000
    return {
        "records": matches,
        "matches": len(matches),
        "time_ms": time_ms,
        "comparisons": rows,
        "algorithm": "Linear scan (filter)",
        "rows": rows,
        "presort": None,
    }