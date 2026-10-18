"""Sorting algorithms, multi-level sort keys and the benchmark."""
import random
import time

HYBRID_CUTOFF = 16               # hybrid merge sort switches to insertion sort below this size

# Each sorting function takes a list of (key, row) pairs, sorts it in place and
# returns (comparisons, swaps). Only pair[0] (the key) is ever compared.
def bubble_sort(a):
    comps = swaps = 0
    n = len(a)
    for i in range(n - 1):
        swapped = False
        for j in range(n - 1 - i):
            comps += 1
            if a[j][0] > a[j + 1][0]:
                a[j], a[j + 1] = a[j + 1], a[j]
                swaps += 1
                swapped = True
        if not swapped:          # already sorted, stop early
            break
    return comps, swaps


def selection_sort(a):
    comps = swaps = 0
    n = len(a)
    for i in range(n - 1):
        smallest = i
        for j in range(i + 1, n):
            comps += 1
            if a[j][0] < a[smallest][0]:
                smallest = j
        if smallest != i:
            a[i], a[smallest] = a[smallest], a[i]
            swaps += 1
    return comps, swaps


def insertion_sort(a):
    comps = swaps = 0
    for i in range(1, len(a)):
        current = a[i]
        j = i - 1
        while j >= 0:
            comps += 1
            if a[j][0] > current[0]:
                a[j + 1] = a[j]          # shifting an element counts as a swap
                swaps += 1
                j -= 1
            else:
                break
        a[j + 1] = current
    return comps, swaps


def merge_sort(a):
    counts = [0, 0]                      # [comparisons, moves]

    def sort(part):
        if len(part) <= 1:
            return part
        mid = len(part) // 2
        left = sort(part[:mid])
        right = sort(part[mid:])
        merged = []
        i = j = 0
        while i < len(left) and j < len(right):
            counts[0] += 1
            if left[i][0] <= right[j][0]:        # <= keeps the sort stable
                merged.append(left[i])
                i += 1
            else:
                merged.append(right[j])
                j += 1
            counts[1] += 1
        while i < len(left):
            merged.append(left[i])
            i += 1
            counts[1] += 1
        while j < len(right):
            merged.append(right[j])
            j += 1
            counts[1] += 1
        return merged

    a[:] = sort(a)
    return counts[0], counts[1]          # merge sort has no swaps, so moves are reported


def hybrid_merge_sort(a):
    """Merge sort that uses insertion sort for small pieces."""
    counts = [0, 0]                      # [comparisons, moves]

    def small_sort(part):
        part = part[:]
        for i in range(1, len(part)):
            current = part[i]
            j = i - 1
            while j >= 0:
                counts[0] += 1
                if part[j][0] > current[0]:
                    part[j + 1] = part[j]
                    counts[1] += 1
                    j -= 1
                else:
                    break
            part[j + 1] = current
        return part

    def sort(part):
        if len(part) <= HYBRID_CUTOFF:
            return small_sort(part)
        mid = len(part) // 2
        left = sort(part[:mid])
        right = sort(part[mid:])
        merged = []
        i = j = 0
        while i < len(left) and j < len(right):
            counts[0] += 1
            if left[i][0] <= right[j][0]:
                merged.append(left[i])
                i += 1
            else:
                merged.append(right[j])
                j += 1
            counts[1] += 1
        while i < len(left):
            merged.append(left[i])
            i += 1
            counts[1] += 1
        while j < len(right):
            merged.append(right[j])
            j += 1
            counts[1] += 1
        return merged

    a[:] = sort(a)
    return counts[0], counts[1]


def quick_sort(a):
    """Iterative quick sort with a random pivot and 3-way partitioning
    (the 3-way split keeps it fast when many keys are equal)."""
    comps = swaps = 0
    stack = [(0, len(a) - 1)]
    while stack:
        lo, hi = stack.pop()
        if lo >= hi:
            continue
        pivot = a[random.randint(lo, hi)][0]
        lt, i, gt = lo, lo, hi
        while i <= gt:
            comps += 1
            if a[i][0] < pivot:
                if lt != i:
                    a[lt], a[i] = a[i], a[lt]
                    swaps += 1
                lt += 1
                i += 1
            else:
                comps += 1
                if a[i][0] > pivot:
                    a[i], a[gt] = a[gt], a[i]
                    swaps += 1
                    gt -= 1
                else:
                    i += 1
        stack.append((lo, lt - 1))
        stack.append((gt + 1, hi))
    return comps, swaps


def heap_sort(a):
    comps = swaps = 0
    n = len(a)

    def sift_down(root, end):
        nonlocal comps, swaps
        while True:
            child = 2 * root + 1
            if child >= end:
                break
            if child + 1 < end:
                comps += 1
                if a[child][0] < a[child + 1][0]:
                    child += 1
            comps += 1
            if a[root][0] < a[child][0]:
                a[root], a[child] = a[child], a[root]
                swaps += 1
                root = child
            else:
                break

    for start in range(n // 2 - 1, -1, -1):      # build the max heap
        sift_down(start, n)
    for end in range(n - 1, 0, -1):              # move the largest to the end
        a[0], a[end] = a[end], a[0]
        swaps += 1
        sift_down(0, end)
    return comps, swaps


def shell_sort(a):
    comps = swaps = 0
    n = len(a)
    gap = n // 2
    while gap > 0:
        for i in range(gap, n):
            current = a[i]
            j = i
            while j >= gap:
                comps += 1
                if a[j - gap][0] > current[0]:
                    a[j] = a[j - gap]
                    swaps += 1
                    j -= gap
                else:
                    break
            a[j] = current
        gap //= 2
    return comps, swaps


# --- non-comparison sorts: they only work on a single numeric column ---
def _require_ints(a):
    for key, _ in a:
        if isinstance(key, bool) or not isinstance(key, int):
            raise ValueError("needs a single integer column")


def counting_sort(a):
    """Counting sort. Does no key comparisons, so comparisons = 0 and
    'swaps' is the number of elements written to the output."""
    if not a:
        return 0, 0
    _require_ints(a)
    low = min(p[0] for p in a)
    high = max(p[0] for p in a)
    size = high - low + 1
    if size > 5_000_000:
        raise ValueError("value range is too large for counting sort")
    count = [0] * size
    for key, _ in a:
        count[key - low] += 1
    for i in range(1, size):
        count[i] += count[i - 1]
    output = [None] * len(a)
    moves = 0
    for i in range(len(a) - 1, -1, -1):          # backwards keeps it stable
        idx = a[i][0] - low
        count[idx] -= 1
        output[count[idx]] = a[i]
        moves += 1
    a[:] = output
    return 0, moves


def radix_sort(a):
    """LSD radix sort (base 10) using counting sort for every digit."""
    if not a:
        return 0, 0
    _require_ints(a)
    low = min(p[0] for p in a)
    biggest = max(p[0] for p in a) - low
    moves = 0
    exp = 1
    while biggest // exp > 0:
        count = [0] * 10
        for key, _ in a:
            count[((key - low) // exp) % 10] += 1
        for d in range(1, 10):
            count[d] += count[d - 1]
        output = [None] * len(a)
        for i in range(len(a) - 1, -1, -1):
            d = ((a[i][0] - low) // exp) % 10
            count[d] -= 1
            output[count[d]] = a[i]
            moves += 1
        a[:] = output
        exp *= 10
    return 0, moves


def bucket_sort(a):
    """Bucket sort: spread the keys over n buckets, sort each bucket with insertion sort."""
    n = len(a)
    if n < 2:
        return 0, 0
    for key, _ in a:
        if isinstance(key, bool) or not isinstance(key, (int, float)):
            raise ValueError("needs a single numeric column")
    low = min(p[0] for p in a)
    high = max(p[0] for p in a)
    if low == high:
        return 0, 0
    buckets = [[] for _ in range(n)]
    moves = 0
    for pair in a:
        idx = int((pair[0] - low) / (high - low) * (n - 1))
        buckets[idx].append(pair)
        moves += 1
    comps = 0
    result = []
    for bucket in buckets:
        for i in range(1, len(bucket)):
            current = bucket[i]
            j = i - 1
            while j >= 0:
                comps += 1
                if bucket[j][0] > current[0]:
                    bucket[j + 1] = bucket[j]
                    moves += 1
                    j -= 1
                else:
                    break
            bucket[j + 1] = current
        result.extend(bucket)
    a[:] = result
    return comps, moves


# name: (function, time complexity, stable?)
ALGORITHMS = {
    "Bubble Sort":       (bubble_sort,       "O(n^2)",                        True),
    "Selection Sort":    (selection_sort,    "O(n^2)",                        False),
    "Insertion Sort":    (insertion_sort,    "O(n^2)",                        True),
    "Merge Sort":        (merge_sort,        "O(n log n)",                    True),
    "Hybrid Merge Sort": (hybrid_merge_sort, "O(n log n)",                    True),
    "Quick Sort":        (quick_sort,        "O(n log n) avg, O(n^2) worst",  False),
    "Counting Sort":     (counting_sort,     "O(n + k)",                      True),
    "Radix Sort":        (radix_sort,        "O(d * (n + b))",                True),
    "Bucket Sort":       (bucket_sort,       "O(n + k) avg, O(n^2) worst",    True),
    "Heap Sort":         (heap_sort,         "O(n log n)",                    False),
    "Shell Sort":        (shell_sort,        "O(n^2) worst",                  False),
}
SLOW = {"Bubble Sort", "Selection Sort", "Insertion Sort"}
NUMERIC_ONLY = {"Counting Sort", "Radix Sort", "Bucket Sort"}


# ----------------------------------------------------------------------
# Sort keys, multi-level sorting and benchmark
# ----------------------------------------------------------------------
def make_level_key(value, descending):
    """Key for one sort level. For descending order numbers are negated and text becomes
    a tuple of negative character codes, so every algorithm can use the same > and < tests."""
    if not descending:
        return value.lower() if isinstance(value, str) else value
    if isinstance(value, str):
        return tuple(-ord(c) for c in value.lower()) + (1 << 30,)
    return -value


def build_key_func(levels):
    if len(levels) == 1:
        column, descending = levels[0]
        return lambda row: make_level_key(row[column], descending)
    return lambda row: tuple(make_level_key(row[c], d) for c, d in levels)


def describe_levels(levels):
    return ", ".join(f"{c} ({'desc' if d else 'asc'})" for c, d in levels)


def run_sort(rows, levels, algo_name):
    """levels = [(column, descending), ...] with 1 to 3 entries.
    Returns (sorted rows, comparisons, swaps, milliseconds)."""
    func = ALGORITHMS[algo_name][0]
    key_func = build_key_func(levels)
    pairs = [(key_func(r), r) for r in rows]
    start = time.perf_counter()
    comps, swaps = func(pairs)
    ms = (time.perf_counter() - start) * 1000
    return [p[1] for p in pairs], comps, swaps, ms


def benchmark(rows, levels, progress=None):
    """Run every algorithm on the same data.
    Returns (name, ms, comparisons, swaps, complexity, stable) per algorithm;
    the numbers are None when an algorithm cannot handle this column."""
    results = []
    for name, (_, complexity, stable) in ALGORITHMS.items():
        if progress:
            progress(name)
        try:
            _, comps, swaps, ms = run_sort(rows, levels, name)
            results.append((name, ms, comps, swaps, complexity, stable))
        except ValueError:
            results.append((name, None, None, None, complexity, stable))
    return results