import sqlite3
import csv
import glob
import numpy as np
import dedupe_pipeline as d

DB = "corpus.sqlite"


def fast_signature(values):
    """
    Optimized MinHash signature.

    Keeps the same:
    - 256 permutations
    - token_hash()
    - MINHASH_PRIME
    - mixing formula
    """

    base_hashes = np.array(
        [d.token_hash(value, 0) for value in values],
        dtype=np.int64
    )

    result = []

    for seed in range(d.NUM_PERMUTATIONS):
        # Use Python integers through object dtype to avoid
        # NumPy signed 64-bit overflow.
        mixed = (
            base_hashes.astype(object) * (2 * seed + 1)
            + seed * 0x9E3779B97F4A7C15
        ) % d.MINHASH_PRIME

        mixed = np.array(mixed, dtype=np.int64)

        result.append(int(np.min(mixed)))

    return tuple(result)


# Connect to SQLite
conn = sqlite3.connect(DB)

# Remove incomplete data from the previous run
print("Clearing previous partial notices...")
conn.execute("DELETE FROM notices")
conn.commit()

total = 0

# Process all CSV files
for filename in glob.glob("notices\\*.csv"):

    print("Processing:", filename)

    with open(filename, encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for r in reader:

            # Normalize notice
            normalized = d.normalize_notice(r)

            # Generate 5-character shingles
            shingle_set = d.shingles(normalized)

            # Generate 256-value MinHash
            sig = fast_signature(shingle_set)

            # Store signature as 2048-byte BLOB
            packed = d.pack_signature(sig)

            # Insert notice
            conn.execute(
                """
                INSERT INTO notices
                (
                    notice_id,
                    portal_id,
                    published_at,
                    title,
                    body,
                    estimated_value,
                    closing_date,
                    normalized_text,
                    shingle_count,
                    minhash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["notice_id"],
                    r["portal_id"],
                    r["published_at"],
                    r["title"],
                    r["body"],
                    r["estimated_value"],
                    r["closing_date"],
                    normalized,
                    len(shingle_set),
                    packed
                )
            )

            total += 1

            # Commit every 500 notices
            if total % 500 == 0:
                conn.commit()
                print("Inserted:", total)


# Final commit
conn.commit()

# Final verification
print()
print("==============================")
print("FINAL INSERTED:", total)
print(
    "DATABASE NOTICES:",
    conn.execute(
        "SELECT COUNT(*) FROM notices"
    ).fetchone()[0]
)
print("==============================")


conn.close()