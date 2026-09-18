import sqlite3
import csv
import time

DB = "corpus.sqlite"
MAX_CANDIDATES = 500

conn = sqlite3.connect(DB)

# -------------------------------------------------
# Load labelled pairs
# -------------------------------------------------

pairs = []

with open("labelled_pairs.csv", newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)

    for row in reader:
        pairs.append((
            row["notice_id_a"],
            row["notice_id_b"],
            row["label"]
        ))

print("Labelled pairs:", len(pairs))

# -------------------------------------------------
# Retrieve candidates using the ORIGINAL
# 32-band x 8-row LSH structure
# -------------------------------------------------

notice_ids = [
    r[0]
    for r in conn.execute(
        "SELECT notice_id FROM notices ORDER BY notice_id"
    )
]

candidate_cache = {}

start = time.perf_counter()

for i, notice_id in enumerate(notice_ids, 1):

    rows = conn.execute(
        """
        SELECT DISTINCT l2.notice_id
        FROM lsh_bands l1
        JOIN lsh_bands l2
          ON l2.band = l1.band
         AND l2.band_key = l1.band_key
        WHERE l1.notice_id = ?
          AND l2.notice_id <> ?
        LIMIT ?
        """,
        (notice_id, notice_id, MAX_CANDIDATES)
    ).fetchall()

    candidate_cache[notice_id] = {
        r[0] for r in rows
    }

    if i % 1000 == 0:
        print("Processed:", i)

elapsed = time.perf_counter() - start

# -------------------------------------------------
# Candidate work
# -------------------------------------------------

total_work = sum(
    len(v)
    for v in candidate_cache.values()
)

# -------------------------------------------------
# Labelled-pair survival
# -------------------------------------------------

same_total = 0
same_survived = 0

different_total = 0
different_survived = 0

for a, b, label in pairs:

    survived = (
        b in candidate_cache.get(a, set())
        or a in candidate_cache.get(b, set())
    )

    if label == "same":
        same_total += 1
        if survived:
            same_survived += 1

    elif label == "different":
        different_total += 1
        if survived:
            different_survived += 1

# -------------------------------------------------
# Results
# -------------------------------------------------

original_work = 27_552_440

reduction = (
    1 - total_work / original_work
) * 100

print()
print("=" * 70)
print("CANDIDATE CAP MITIGATION")
print("=" * 70)

print("Candidate cap per notice:", MAX_CANDIDATES)

print()
print("Candidate work:", total_work)

print(
    "Work reduction:",
    f"{reduction:.2f}%"
)

print(
    "Runtime:",
    f"{elapsed:.3f} seconds"
)

print()
print("LABELLED PAIRS")
print("-" * 70)

print(
    "SAME:",
    same_survived,
    "/",
    same_total,
    f"({same_survived / same_total:.4f})"
)

print(
    "DIFFERENT:",
    different_survived,
    "/",
    different_total,
    f"({different_survived / different_total:.4f})"
)

print()
print(
    "SAME candidate-stage recall:",
    f"{same_survived / same_total:.4f}"
)

print(
    "DIFFERENT candidate-stage survival:",
    f"{different_survived / different_total:.4f}"
)

conn.close()