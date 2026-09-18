import sqlite3
from collections import defaultdict

conn = sqlite3.connect("corpus.sqlite")

rows = conn.execute(
    "SELECT band, band_key, notice_id FROM lsh_bands"
).fetchall()

buckets = defaultdict(set)

for band, band_key, notice_id in rows:
    buckets[(band, band_key)].add(notice_id)

sizes = []

for (band, band_key), ids in buckets.items():
    sizes.append((len(ids), band, band_key))

sizes.sort(reverse=True)

print("=" * 70)
print("LSH BUCKET SIZE ANALYSIS")
print("=" * 70)

print("Total buckets:", len(sizes))
print()

total = sum(size for size, _, _ in sizes)

print("Total bucket memberships:", total)
print()

print("TOP 20 LARGEST BUCKETS")
print("-" * 70)
print("rank | band | bucket_size")

for i, (size, band, key) in enumerate(sizes[:20], 1):
    print(i, "|", band, "|", size)

print()
print("=" * 70)
print("BUCKET SIZE DISTRIBUTION")
print("=" * 70)

for limit in [10, 25, 50, 100, 250, 500, 1000, 2000, 5000]:
    count = sum(1 for size, _, _ in sizes if size <= limit)
    print(
        f"<= {limit:5} notices:",
        f"{count:6} buckets",
        f"({count / len(sizes) * 100:.2f}%)"
    )

print()
print("BUCKETS > 1000:", sum(1 for size, _, _ in sizes if size > 1000))
print("BUCKETS > 2000:", sum(1 for size, _, _ in sizes if size > 2000))
print("BUCKETS > 5000:", sum(1 for size, _, _ in sizes if size > 5000))

conn.close()