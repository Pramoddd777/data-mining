import sqlite3
import struct
import time
from collections import Counter

DB = "corpus.sqlite"

BANDS = 32
ROWS_PER_BAND = 8

conn = sqlite3.connect(DB)

# Make sure SQLite has the required index
conn.execute(
    "CREATE INDEX IF NOT EXISTS ix_lsh_lookup "
    "ON lsh_bands(band, band_key)"
)
conn.commit()

notices = conn.execute(
    "SELECT notice_id, minhash FROM notices ORDER BY notice_id"
).fetchall()

print("Notices:", len(notices))

candidate_counts = []
total_candidates = 0

start_all = time.perf_counter()

for i, (notice_id, packed) in enumerate(notices, 1):

    signature = struct.unpack("<256Q", packed)

    candidates = set()

    for band in range(BANDS):

        start = band * ROWS_PER_BAND
        end = start + ROWS_PER_BAND

        band_key = struct.pack(
            "<8Q",
            *signature[start:end]
        )

        rows = conn.execute(
            """
            SELECT notice_id
            FROM lsh_bands
            WHERE band = ? AND band_key = ?
            """,
            (band, band_key)
        ).fetchall()

        for (candidate_id,) in rows:
            if candidate_id != notice_id:
                candidates.add(candidate_id)

    count = len(candidates)

    candidate_counts.append((notice_id, count))
    total_candidates += count

    if i % 1000 == 0:
        print("Processed:", i)

elapsed = time.perf_counter() - start_all

counts = [x[1] for x in candidate_counts]

print()
print("==============================")
print("FULL CORPUS RETRIEVAL")
print("==============================")
print("Notices processed:", len(notices))
print("Total candidate links:", total_candidates)
print("Average candidates/notice:", round(total_candidates / len(notices), 2))
print("Maximum candidates/notice:", max(counts))
print("Minimum candidates/notice:", min(counts))
print("Wall clock seconds:", round(elapsed, 3))
print("Wall clock minutes:", round(elapsed / 60, 3))

# Distribution
print()
print("CANDIDATE COUNT DISTRIBUTION")

for limit in [0, 10, 25, 50, 100, 250, 500, 1000]:
    n = sum(1 for x in counts if x <= limit)
    print("<= %4d candidates: %5d notices (%.2f%%)"
          % (limit, n, 100 * n / len(counts)))

# Top 20 expensive notices
print()
print("TOP 20 NOTICES BY CANDIDATE COUNT")

for notice_id, count in sorted(
    candidate_counts,
    key=lambda x: x[1],
    reverse=True
)[:20]:
    print(notice_id, count)

# Portal aggregation for expensive notices
portal_counts = Counter()

for notice_id, count in candidate_counts:
    portal = conn.execute(
        "SELECT portal_id FROM notices WHERE notice_id = ?",
        (notice_id,)
    ).fetchone()[0]

    portal_counts[portal] += count

print()
print("TOP PORTALS BY TOTAL CANDIDATE WORK")

for portal, work in portal_counts.most_common(20):
    print(portal, work)

conn.close()