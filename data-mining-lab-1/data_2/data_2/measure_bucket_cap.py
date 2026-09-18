import sqlite3
import csv
from collections import defaultdict

conn = sqlite3.connect("corpus.sqlite")

# -------------------------------------------------
# 1. Load all LSH bucket memberships
# -------------------------------------------------

print("Reading LSH bands...")

rows = conn.execute(
    "SELECT band, band_key, notice_id FROM lsh_bands"
).fetchall()

print("LSH rows:", len(rows))

# -------------------------------------------------
# 2. Group notices by LSH bucket
# -------------------------------------------------

buckets = defaultdict(set)

for band, band_key, notice_id in rows:
    buckets[(band, band_key)].add(notice_id)

print("Buckets:", len(buckets))

# -------------------------------------------------
# 3. Load labelled pairs
# -------------------------------------------------

pairs = []

with open(
    "labelled_pairs.csv",
    newline="",
    encoding="utf-8-sig"
) as f:

    reader = csv.DictReader(f)

    for row in reader:
        pairs.append(
            (
                row["notice_id_a"],
                row["notice_id_b"],
                row["label"]
            )
        )

print("Labelled pairs:", len(pairs))

# -------------------------------------------------
# 4. Build candidate sets with bucket cap
# -------------------------------------------------

def build_candidates(cap):

    candidates = defaultdict(set)

    capped_buckets = 0
    original_memberships = 0
    retained_memberships = 0

    for key, ids in buckets.items():

        ids = sorted(ids)

        original_memberships += len(ids)

        if len(ids) > cap:
            capped_buckets += 1

            # Keep only the first CAP notices
            ids = ids[:cap]

        retained_memberships += len(ids)

        ids_set = set(ids)

        for notice_id in ids_set:

            candidates[notice_id].update(
                x
                for x in ids_set
                if x != notice_id
            )

    return (
        candidates,
        capped_buckets,
        original_memberships,
        retained_memberships
    )

# -------------------------------------------------
# 5. Run mitigation with bucket cap
# -------------------------------------------------

CAP = 100000

print()
print("Testing bucket cap:", CAP)

(
    candidates,
    capped,
    original,
    retained
) = build_candidates(CAP)

# -------------------------------------------------
# 6. Measure labelled-pair survival
# -------------------------------------------------

same_total = 0
same_survived = 0

different_total = 0
different_survived = 0

for n1, n2, label in pairs:

    survived = (
        n2 in candidates.get(n1, set())
        or n1 in candidates.get(n2, set())
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
# 7. Calculate candidate work
# -------------------------------------------------

total_work = sum(
    len(candidate_set)
    for candidate_set in candidates.values()
)

# Original measured candidate work
original_work = 27_552_440

work_reduction = (
    1 - total_work / original_work
) * 100

# -------------------------------------------------
# 8. Print results
# -------------------------------------------------

print()
print("=" * 70)
print("BUCKET CAP MITIGATION MEASUREMENT")
print("=" * 70)

print("Bucket cap:", CAP)

print(
    "Total buckets:",
    len(buckets)
)

print(
    "Buckets capped:",
    capped
)

print(
    "Original bucket memberships:",
    original
)

print(
    "Retained bucket memberships:",
    retained
)

print()
print("CANDIDATE WORK")
print("-" * 70)

print(
    "Original candidate work:",
    original_work
)

print(
    "Candidate work after cap:",
    total_work
)

print(
    "Candidate work reduction:",
    f"{work_reduction:.2f}%"
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
    "CANDIDATE-STAGE SAME RECALL:",
    f"{same_survived / same_total:.4f}"
)

print(
    "CANDIDATE-STAGE DIFFERENT SURVIVAL:",
    f"{different_survived / different_total:.4f}"
)

print()
print("=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)

conn.close()