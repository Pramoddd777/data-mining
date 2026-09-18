import sqlite3
from collections import defaultdict

conn = sqlite3.connect("corpus.sqlite")

# -------------------------------------------------
# 1. Read all LSH bucket memberships
# -------------------------------------------------

print("Reading LSH bands...")

rows = conn.execute(
    "SELECT band, band_key, notice_id FROM lsh_bands"
).fetchall()

print("LSH rows:", len(rows))

# -------------------------------------------------
# 2. Group notices by LSH bucket
# -------------------------------------------------

buckets = defaultdict(list)

for band, band_key, notice_id in rows:
    buckets[(band, band_key)].append(notice_id)

print("Buckets:", len(buckets))

# -------------------------------------------------
# 3. Calculate candidate work per notice
# -------------------------------------------------

work = defaultdict(set)

for ids in buckets.values():

    unique_ids = set(ids)

    for notice_id in unique_ids:
        for candidate in unique_ids:
            if candidate != notice_id:
                work[notice_id].add(candidate)

# -------------------------------------------------
# 4. Get portal for every notice
# -------------------------------------------------

notice_portals = dict(
    conn.execute(
        "SELECT notice_id, portal_id FROM notices"
    ).fetchall()
)

# -------------------------------------------------
# 5. Aggregate candidate work by portal
# -------------------------------------------------

portal_work = defaultdict(int)
portal_notices = defaultdict(int)

for notice_id, candidates in work.items():

    portal = notice_portals.get(notice_id)

    if portal is not None:
        portal_work[portal] += len(candidates)
        portal_notices[portal] += 1

# -------------------------------------------------
# 6. Print portal distribution
# -------------------------------------------------

print()
print("=" * 60)
print("TOP PORTALS BY CANDIDATE WORK")
print("=" * 60)

print("portal | notices | candidate_work")

for portal in sorted(
    portal_work,
    key=portal_work.get,
    reverse=True
)[:20]:

    print(
        portal,
        "|",
        portal_notices[portal],
        "|",
        portal_work[portal]
    )

# -------------------------------------------------
# 7. Calculate percentage of total work
# -------------------------------------------------

total_work = sum(portal_work.values())

print()
print("=" * 60)
print("WORK CONCENTRATION")
print("=" * 60)

print("Total candidate work:", total_work)

top5_work = sum(
    portal_work[p]
    for p in sorted(
        portal_work,
        key=portal_work.get,
        reverse=True
    )[:5]
)

top10_work = sum(
    portal_work[p]
    for p in sorted(
        portal_work,
        key=portal_work.get,
        reverse=True
    )[:10]
)

print(
    "Top 5 portals work:",
    top5_work,
    f"({top5_work / total_work * 100:.2f}%)"
)

print(
    "Top 10 portals work:",
    top10_work,
    f"({top10_work / total_work * 100:.2f}%)"
)

# -------------------------------------------------
# 8. Notice-level hotspots
# -------------------------------------------------

print()
print("=" * 60)
print("TOP 20 NOTICES BY CANDIDATE WORK")
print("=" * 60)

for notice_id, candidates in sorted(
    work.items(),
    key=lambda x: len(x[1]),
    reverse=True
)[:20]:

    portal = notice_portals.get(notice_id, "?")

    print(
        notice_id,
        "| portal:", portal,
        "| candidates:", len(candidates)
    )

conn.close()

print()
print("Analysis complete.")