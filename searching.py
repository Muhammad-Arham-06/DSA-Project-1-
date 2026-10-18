"""Search algorithms and composite (AND / OR / NOT) filters."""
import time

from sorting import merge_sort

OPERATORS = ["contains", "starts with", "ends with", "equals", ">", "<", ">=", "<="]
SEARCH_ALGOS = ["Linear Search", "Binary Search"]


def normalize(value):
    return value.lower() if isinstance(value, str) else value


def parse_query(sample_value, query, op):
    """Convert the query text to the column's type (raises ValueError for a bad number)."""
    if op in ("contains", "starts with", "ends with"):
        return query.lower()
    if isinstance(sample_value, (int, float)):
        try:
            return int(query)
        except ValueError:
            return float(query)
    return query.lower()


def matches(value, op, q):
    if op == "contains":
        return q in str(value).lower()
    if op == "starts with":
        return str(value).lower().startswith(q)
    if op == "ends with":
        return str(value).lower().endswith(q)
    v = normalize(value)
    if op == "equals":
        return v == q
    if op == ">":
        return v > q
    if op == "<":
        return v < q
    if op == ">=":
        return v >= q
    return v <= q


def linear_search(rows, col, op, q):
    """Check every row. Returns (set of matching row indexes, comparisons)."""
    found = set()
    comps = 0
    for i, row in enumerate(rows):
        comps += 1
        if matches(row[col], op, q):
            found.add(i)
    return found, comps


def binary_search_equals(rows, col, q):
    """Sort (key, index) pairs with merge sort, binary-search the first match and collect
    all equal keys after it. Only the search comparisons are counted."""
    pairs = [(normalize(r[col]), i) for i, r in enumerate(rows)]
    merge_sort(pairs)
    comps = 0
    lo, hi = 0, len(pairs)
    while lo < hi:
        mid = (lo + hi) // 2
        comps += 1
        if pairs[mid][0] < q:
            lo = mid + 1
        else:
            hi = mid
    found = set()
    k = lo
    while k < len(pairs):
        comps += 1
        if pairs[k][0] == q:
            found.add(pairs[k][1])
            k += 1
        else:
            break
    return found, comps


def evaluate_condition(rows, cond, algo):
    col, op = cond["col"], cond["op"]
    q = parse_query(rows[0][col], cond["query"], op)
    if algo == "Binary Search" and op == "equals":
        found, comps = binary_search_equals(rows, col, q)
    else:
        found, comps = linear_search(rows, col, op, q)
    if cond["negate"]:                           # NOT
        found = set(range(len(rows))) - found
    return found, comps


def apply_conditions(rows, conds, algo):
    """conds: list of {"connector": "AND"/"OR", "negate": bool, "col", "op", "query"}.
    Conditions are combined from left to right (the first connector is ignored).
    Returns (matching rows, comparisons, milliseconds)."""
    start = time.perf_counter()
    result = None
    total = 0
    for cond in conds:
        found, comps = evaluate_condition(rows, cond, algo)
        total += comps
        if result is None:
            result = found
        elif cond["connector"] == "OR":
            result = result | found
        else:
            result = result & found
    out = [rows[i] for i in sorted(result or [])]
    ms = (time.perf_counter() - start) * 1000
    return out, total, ms