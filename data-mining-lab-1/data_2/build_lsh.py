import sqlite3
import struct

DB = "corpus.sqlite"

BANDS = 32
ROWS_PER_BAND = 8

conn = sqlite3.connect(DB)

# Clear any previous LSH data
conn.execute("DELETE FROM lsh_bands")
conn.commit()

rows = conn.execute(
    "SELECT notice_id, minhash FROM notices"
).fetchall()

print("Notices found:", len(rows))

total = 0

for notice_id, packed in rows:

    # 256 uint64 values
    signature = struct.unpack(
        "<256Q",
        packed
    )

    for band in range(BANDS):

        start = band * ROWS_PER_BAND
        end = start + ROWS_PER_BAND

        # 8 MinHash values make one band key
        band_values = signature[start:end]

        band_key = struct.pack(
            "<8Q",
            *band_values
        )

        conn.execute(
            """
            INSERT INTO lsh_bands
            (band, band_key, notice_id)
            VALUES (?, ?, ?)
            """,
            (
                band,
                band_key,
                notice_id
            )
        )

        total += 1

    if total % 32000 == 0:
        conn.commit()
        print("LSH rows:", total)

conn.commit()

print()
print("==============================")
print("FINAL LSH ROWS:", total)
print(
    "DATABASE LSH ROWS:",
    conn.execute(
        "SELECT COUNT(*) FROM lsh_bands"
    ).fetchone()[0]
)
print("==============================")

conn.close()