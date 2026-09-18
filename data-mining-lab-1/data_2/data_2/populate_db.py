import sqlite3
import csv
import glob
import dedupe_pipeline as d

conn = sqlite3.connect("corpus.sqlite")
total = 0

for f in glob.glob("notices\\*.csv"):
    print("Processing:", f)

    with open(f, encoding="utf-8") as file:
        rows = csv.DictReader(file)

        for r in rows:
            normalized = d.normalize_notice(r)
            shingle_set = d.shingles(normalized)
            sig = d.signature(shingle_set)
            packed = d.pack_signature(sig)

            conn.execute(
                """
                INSERT INTO notices
                (notice_id, portal_id, published_at, title, body,
                 estimated_value, closing_date, normalized_text,
                 shingle_count, minhash)
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

            if total % 100 == 0:
                conn.commit()
                print("Inserted:", total)

conn.commit()

print()
print("FINAL INSERTED:", total)
print(
    "DATABASE NOTICES:",
    conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0]
)

conn.close()