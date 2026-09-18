import sqlite3
import csv
import re
from collections import defaultdict

# -------------------------------------------------
# Connect to database
# -------------------------------------------------

conn = sqlite3.connect("corpus.sqlite")

# -------------------------------------------------
# Load notices
# -------------------------------------------------

notices = {}

rows = conn.execute(
    "SELECT notice_id, portal_id, title, body FROM notices"
).fetchall()

for notice_id, portal_id, title, body in rows:
    notices[notice_id] = {
        "portal_id": portal_id,
        "title": title or "",
        "body": body or ""
    }

print("Notices loaded:", len(notices))

# -------------------------------------------------
# Load labelled pairs
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
# Boilerplate removal
#
# Based on portal_profiles.md:
# P001/P002/P005 -> NATIONAL PROCUREMENT AGGREGATION SERVICE
# P003/P004/P006 -> STATE PROCUREMENT CELL
# -------------------------------------------------

NODAL_PORTALS = {
    "P001",
    "P002",
    "P003",
    "P004",
    "P005",
    "P006"
}

def remove_boilerplate(portal_id, text):

    if portal_id not in NODAL_PORTALS:
        return text

    patterns = [
        r"NATIONAL PROCUREMENT AGGREGATION SERVICE",
        r"STATE PROCUREMENT CELL"
    ]

    cleaned = text

    for pattern in patterns:
        cleaned = re.sub(
            pattern,
            " ",
            cleaned,
            flags=re.IGNORECASE
        )

    return cleaned

# -------------------------------------------------
# Simple character 5-gram representation
# -------------------------------------------------

def shingles(text, k=5):

    text = re.sub(r"\s+", " ", text.lower()).strip()

    if len(text) < k:
        return set()

    return {
        text[i:i+k]
        for i in range(len(text) - k + 1)
    }

# -------------------------------------------------
# Build cleaned representations
# -------------------------------------------------

representations = {}

for notice_id, data in notices.items():

    text = (
        data["title"]
        + " "
        + remove_boilerplate(
            data["portal_id"],
            data["body"]
        )
    )

    representations[notice_id] = shingles(text)

# -------------------------------------------------
# Build candidate buckets using a simple
# blocking key based on first several shingles.
#
# This is a measurement experiment, not the
# production replacement.
# -------------------------------------------------

buckets = defaultdict(set)

for notice_id, sh in representations.items():

    if not sh:
        continue

    # Deterministic blocking keys
    sorted_sh = sorted(sh)

    for key in sorted_sh[:8]:
        buckets[key].add(notice_id)

# -------------------------------------------------
# Generate candidates
# -------------------------------------------------

candidates = defaultdict(set)

for ids in buckets.values():

    ids = set(ids)

    for notice_id in ids:

        candidates[notice_id].update(
            x for x in ids
            if x != notice_id
        )

# -------------------------------------------------
# Candidate work
# -------------------------------------------------

total_work = sum(
    len(x)
    for x in candidates.values()
)

# -------------------------------------------------
# Labelled-pair survival
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
# Compare against measured original retrieval
# -------------------------------------------------

original_work = 27_552_440

reduction = (
    1 - total_work / original_work
) * 100

# -------------------------------------------------
# Output
# -------------------------------------------------

print()
print("=" * 70)
print("BOILERPLATE MITIGATION MEASUREMENT")
print("=" * 70)

print("Affected portals: P001-P006")

print()
print("ORIGINAL")
print("-" * 70)
print("Candidate work:", original_work)

print()
print("AFTER BOILERPLATE REMOVAL")
print("-" * 70)

print(
    "Candidate work:",
    total_work
)

print(
    "Candidate work reduction:",
    f"{reduction:.2f}%"
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

print()
print("=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)

conn.close()