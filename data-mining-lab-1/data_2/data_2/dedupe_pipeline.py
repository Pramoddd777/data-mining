from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sqlite3
import struct
import time
from collections import Counter, defaultdict
from pathlib import Path

NUM_PERMUTATIONS = 256
SHINGLE_SIZE = 5
BANDS = 32
ROWS_PER_BAND = NUM_PERMUTATIONS // BANDS
MAX_CANDIDATES_PER_NOTICE = 500
MINHASH_PRIME = (1 << 61) - 1

REFERENCE_RE = re.compile(r"\b(?:[A-Z]{2,}[A-Z0-9]*(?:[-/][A-Z0-9]+)+|\d{6,})\b", re.I)
NUMBER_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")
SPACE_RE = re.compile(r"\s+")

BOILERPLATE_START = (
    "GOVERNMENT OF INDIA -- NATIONAL PROCUREMENT AGGREGATION SERVICE",
    "STATE PROCUREMENT CELL -- CONSOLIDATED TENDER BULLETIN",
)


def read_notices(root: Path) -> list[dict[str, str]]:
    notices = []
    for path in sorted((root / "notices").glob("*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                notices.append(row)
    return notices


def read_labels(root: Path) -> list[dict[str, str]]:
    with (root / "labelled_pairs.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def strip_boilerplate(text: str) -> str:
    lowered = text.lower()
    starts = [lowered.find(marker.lower()) for marker in BOILERPLATE_START]
    starts = [position for position in starts if position >= 0]
    if starts:
        details = lowered.find("notice details follow")
        name_of_work = lowered.find("name of work:")
        boundary = details if details >= 0 else name_of_work
        if boundary >= 0:
            text = text[boundary:]
    disclaimer = text.lower().find("disclaimer:")
    if disclaimer >= 0:
        text = text[:disclaimer]
    return text


def normalize_notice(row: dict[str, str], cleaned: bool = True) -> str:
    title = row.get("title", "") or ""
    body = row.get("body", "") or ""
    if cleaned:
        body = strip_boilerplate(body)
        lines = []
        skip_dates = False
        for line in body.splitlines():
            stripped = line.strip()
            lower = stripped.lower()
            if lower == "key dates":
                skip_dates = True
                continue
            if skip_dates and (lower.startswith("contact") or lower.startswith("general conditions")):
                skip_dates = False
            if skip_dates:
                continue
            if lower.startswith((
                "tender reference number:",
                "estimated cost put to tender:",
                "estimated cost:",
                "earnest money deposit:",
                "cost of tender document:",
                "minimum average annual turnover:",
                "experience of at least one similar completed work:",
                "publication of notice:",
                "last date and time:",
                "date of opening:",
            )):
                continue
            lines.append(line)
        body = "\n".join(lines)
        title = re.sub(r"\s*\[[^]]+\]", "", title)
    text = f"{title} {body}".lower()
    text = REFERENCE_RE.sub(" <ref> ", text)
    text = NUMBER_RE.sub(" <num> ", text)
    text = re.sub(r"[^a-z<]+", " ", text)
    return SPACE_RE.sub(" ", text).strip()


def shingles(text: str) -> set[str]:
    padded = f"  {text}  "
    if len(padded) <= SHINGLE_SIZE:
        return {padded}
    return {padded[index:index + SHINGLE_SIZE] for index in range(len(padded) - SHINGLE_SIZE + 1)}


def token_hash(value: str, seed: int) -> int:
    digest = hashlib.blake2b(f"{seed}:{value}".encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % MINHASH_PRIME


def signature(values: set[str]) -> tuple[int, ...]:
    # Hash each shingle once, then derive the permutation family with cheap
    # integer mixing. This keeps the fixed-size estimator without 256 BLAKE2
    # calls per shingle.
    base_hashes = [token_hash(value, 0) for value in values]
    result = []
    for seed in range(NUM_PERMUTATIONS):
        minimum = MINHASH_PRIME
        for base_hash in base_hashes:
            mixed = (base_hash * (2 * seed + 1) + seed * 0x9E3779B97F4A7C15) % MINHASH_PRIME
            if mixed < minimum:
                minimum = mixed
        result.append(minimum)
    return tuple(result)


def pack_signature(values: tuple[int, ...]) -> bytes:
    return struct.pack(f"<{len(values)}Q", *values)


def unpack_signature(blob: bytes) -> tuple[int, ...]:
    return struct.unpack(f"<{len(blob) // 8}Q", blob)


def minhash_similarity(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    return sum(a == b for a, b in zip(left, right)) / len(left)


def exact_jaccard(left: set[str], right: set[str]) -> float:
    union = len(left | right)
    return len(left & right) / union if union else 1.0


def title_tokens(title: str) -> set[str]:
    return set(re.findall(r"[a-z]{3,}", title.lower()))


def pair_score(left: dict, right: dict) -> float:
    sig_score = minhash_similarity(left["signature"], right["signature"])
    title_left = title_tokens(left["title"])
    title_right = title_tokens(right["title"])
    title_union = len(title_left | title_right)
    title_score = len(title_left & title_right) / title_union if title_union else 0.0
    value_score = 1.0 if left["estimated_value"] == right["estimated_value"] else 0.0
    close_score = 1.0 if left["closing_date"] == right["closing_date"] else 0.0
    return 0.70 * sig_score + 0.20 * title_score + 0.05 * value_score + 0.05 * close_score


def init_db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS notices (
            notice_id TEXT PRIMARY KEY,
            portal_id TEXT NOT NULL,
            published_at TEXT,
            title TEXT,
            body TEXT,
            estimated_value TEXT,
            closing_date TEXT,
            normalized_text TEXT NOT NULL,
            shingle_count INTEGER NOT NULL,
            minhash BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS lsh_bands (
            band INTEGER NOT NULL,
            band_key BLOB NOT NULL,
            notice_id TEXT NOT NULL REFERENCES notices(notice_id),
            PRIMARY KEY (band, band_key, notice_id)
        );
        CREATE INDEX IF NOT EXISTS ix_lsh_lookup ON lsh_bands(band, band_key);
        CREATE TABLE IF NOT EXISTS candidate_pairs (
            notice_id_a TEXT NOT NULL,
            notice_id_b TEXT NOT NULL,
            minhash_score REAL NOT NULL,
            pair_score REAL NOT NULL,
            PRIMARY KEY (notice_id_a, notice_id_b)
        );
        CREATE TABLE IF NOT EXISTS clusters (
            notice_id TEXT PRIMARY KEY,
            cluster_id TEXT NOT NULL
        );
        """
    )
    return connection


def ingest(connection: sqlite3.Connection, notices: list[dict[str, str]]) -> dict[str, dict]:
    records = {}
    connection.execute("DELETE FROM notices")
    connection.execute("DELETE FROM lsh_bands")
    for row in notices:
        normalized = normalize_notice(row)
        shingle_set = shingles(normalized)
        sig = signature(shingle_set)
        record = {
            **row,
            "normalized_text": normalized,
            "shingles": shingle_set,
            "signature": sig,
        }
        records[row["notice_id"]] = record
        connection.execute(
            "INSERT INTO notices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["notice_id"], row["portal_id"], row.get("published_at"),
                row.get("title"), row.get("body"), row.get("estimated_value"),
                row.get("closing_date"), normalized, len(shingle_set), pack_signature(sig),
            ),
        )
        for band in range(BANDS):
            start = band * ROWS_PER_BAND
            key = hashlib.sha1(pack_signature(sig[start:start + ROWS_PER_BAND])).digest()
            connection.execute("INSERT INTO lsh_bands VALUES (?, ?, ?)", (band, key, row["notice_id"]))
    connection.commit()
    return records


def retrieve_candidates(connection: sqlite3.Connection, records: dict[str, dict]) -> tuple[dict[str, set[str]], int]:
    candidates = defaultdict(set)
    candidate_rows = 0
    connection.execute("DELETE FROM candidate_pairs")
    band_lookup = defaultdict(list)
    for band, key, notice_id in connection.execute("SELECT band, band_key, notice_id FROM lsh_bands"):
        band_lookup[(band, key)].append(notice_id)
    for notice_id, record in records.items():
        ids = set()
        for band in range(BANDS):
            start = band * ROWS_PER_BAND
            key = hashlib.sha1(pack_signature(record["signature"][start:start + ROWS_PER_BAND])).digest()
            ids.update(value for value in band_lookup.get((band, key), []) if value != notice_id)
            if len(ids) >= MAX_CANDIDATES_PER_NOTICE:
                ids = set(sorted(ids)[:MAX_CANDIDATES_PER_NOTICE])
        candidates[notice_id] = ids
        for other_id in ids:
            if notice_id < other_id:
                other = records[other_id]
                mh = minhash_similarity(record["signature"], other["signature"])
                score = pair_score(record, other)
                connection.execute(
                    "INSERT OR REPLACE INTO candidate_pairs VALUES (?, ?, ?, ?)",
                    (notice_id, other_id, mh, score),
                )
                candidate_rows += 1
    connection.commit()
    return candidates, candidate_rows


def union_find(records: dict[str, dict], connection: sqlite3.Connection, threshold: float) -> int:
    parent = {notice_id: notice_id for notice_id in records}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def join(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for left, right, _, score in connection.execute("SELECT * FROM candidate_pairs"):
        if score >= threshold:
            join(left, right)
    groups = defaultdict(list)
    for notice_id in sorted(records):
        groups[find(notice_id)].append(notice_id)
    connection.execute("DELETE FROM clusters")
    for ordinal, root in enumerate(sorted(groups), start=1):
        cluster_id = f"OPP{ordinal:06d}"
        for notice_id in groups[root]:
            connection.execute("INSERT INTO clusters VALUES (?, ?)", (notice_id, cluster_id))
    connection.commit()
    return len(groups)


def choose_threshold(labels: list[dict], records: dict[str, dict]) -> tuple[float, list[dict]]:
    scored = []
    for label in labels:
        left, right = records[label["notice_id_a"]], records[label["notice_id_b"]]
        scored.append({**label, "score": pair_score(left, right), "similarity": exact_jaccard(left["shingles"], right["shingles"])})
    best = (0.75, -1.0, 0, 0)
    for index in range(20, 96):
        threshold = index / 100
        false_merges = sum(row["label"] == "different" and row["score"] >= threshold for row in scored)
        false_splits = sum(row["label"] == "same" and row["score"] < threshold for row in scored)
        cost = 10 * false_merges + false_splits
        if best[1] < 0 or cost < best[1]:
            best = (threshold, cost, false_merges, false_splits)
    return best[0], scored


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_report(root: Path, elapsed: float, notices: list[dict[str, str]], labels: list[dict[str, str]],
                 records: dict[str, dict], candidates: dict[str, set[str]], candidate_rows: int,
                 threshold: float, scored: list[dict], cluster_count: int, db_path: Path) -> None:
    label_counts = Counter(row["label"] for row in labels)
    same_scores = [row["score"] for row in scored if row["label"] == "same"]
    different_scores = [row["score"] for row in scored if row["label"] == "different"]
    false_merges = sum(row["label"] == "different" and row["score"] >= threshold for row in scored)
    false_splits = sum(row["label"] == "same" and row["score"] < threshold for row in scored)
    same_retrieved = sum(row["label"] == "same" and row["notice_id_b"] in candidates[row["notice_id_a"]] or row["label"] == "same" and row["notice_id_a"] in candidates[row["notice_id_b"]] for row in scored)
    same_total = label_counts["same"]
    retrieval_recall = same_retrieved / same_total if same_total else 0.0
    portal_counts = Counter(row["portal_id"] for row in notices)
    biggest = portal_counts.most_common(10)
    query_plan = "EXPLAIN QUERY PLAN SELECT notice_id FROM lsh_bands WHERE band=? AND band_key=?;"
    with sqlite3.connect(db_path) as connection:
        plan = " ".join(str(row) for row in connection.execute(query_plan, (0, b"x")).fetchall())
    report = f"""# SetuBid deduplication experiment

## Corpus and labels

- Notices: **{len(notices):,}** across {len(portal_counts):,} portals.
- Labelled pairs: **{len(labels):,}**; same={label_counts['same']:,}, different={label_counts['different']:,}.
- Label base rate: {label_counts['same'] / len(labels):.3f} same. This is not the corpus base rate, which is much lower, so accuracy alone is not used.
- Top portals by notice count: {biggest}.

## A(a-b): representation and estimator

The signal is title plus body after removing known nodal preambles, disclaimers,
reference-number lines, money fields, and key-date blocks. Lowercase character
5-grams preserve wording and spelling variation while avoiding word-boundary
fragility. The reduced form is a fixed **256-value MinHash signature** (2,048
bytes of uint64 values) over the 5-gram set. Its expected Jaccard estimation
standard error is at most about `sqrt(p(1-p)/256)`, approximately 0.031 at p=0.5.

A pair score is 0.70 MinHash similarity + 0.20 title-token Jaccard + 0.05
estimated-value agreement + 0.05 closing-date agreement. Threshold selection
uses an explicit asymmetric cost: a false merge costs 10 and a false split costs
1, reflecting the product owner's legal-risk instruction.

On the labelled pairs, same scores ranged from {min(same_scores):.3f} to {max(same_scores):.3f}; different scores ranged from {min(different_scores):.3f} to {max(different_scores):.3f}. The selected threshold is **{threshold:.2f}**, producing false merges={false_merges} and false splits={false_splits} on these labels.

## A(c): candidate retrieval

The candidate index uses 32 LSH bands of 8 signature values. A pair survives if
at least one band is equal. The chosen operating point retrieved **{retrieval_recall:.3f}** of labelled same pairs, with {candidate_rows:,} unique candidate pairs over {len(notices):,} notices, before final scoring. The average candidate-list size was {sum(len(v) for v in candidates.values()) / len(notices):.1f}; the maximum was {max(map(len, candidates.values()))}.

This is sublinear candidate retrieval: the final scorer never compares every
notice with every other notice. The full pair space would be 71,994,000 pairs.

## B(d): persistent relational access

SQLite database: `{db_path.name}`. Tables are `notices`, `lsh_bands`,
`candidate_pairs`, and `clusters`; `lsh_bands` has an index on `(band, band_key)`.
The lookup plan is:

```text
{plan}
```

The rejected alternative is a scan of every signature for each query. It has no
selective access path and would approach the 71,994,000-pair baseline.

## A(e): skew and mitigation

Portal skew is mechanically dangerous because common boilerplate creates shared
5-grams, causing large LSH buckets and candidate lists. The chosen normalization
removes the known nodal boilerplate and volatile fields before hashing. The
largest portal counts are reported above; candidate-list distribution is stored
in `candidate_distribution.csv`. The pipeline runtime was {elapsed:.1f} seconds
on this machine, versus a quadratic comparison design whose pair count is
71,994,000 before text scoring. Candidate cap is {MAX_CANDIDATES_PER_NOTICE}
per notice to prevent a single pathological bucket from consuming the nightly
window; the labelled same-pair retrieval recall is reported above as the cost of
that mitigation.

## Stable IDs

Cluster IDs are assigned from sorted notice IDs and stored in SQLite. A production
version should persist the cluster membership and never renumber existing roots;
new copies should attach to an existing cluster while old `OPP######` values are
kept immutable for bookmarks.

## Result

Clusters written: **{cluster_count:,}**. The full machine-readable evidence is in
`label_metrics.csv`, `candidate_distribution.csv`, `candidate_pairs.csv`, and
`corpus.sqlite`.
"""
    (root / "DEDUPLICATION_REPORT.md").write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--threshold", type=float, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    started = time.perf_counter()
    notices = read_notices(root)
    labels = read_labels(root)
    db_path = root / "corpus.sqlite"
    connection = init_db(db_path)
    records = ingest(connection, notices)
    threshold, scored = choose_threshold(labels, records)
    if args.threshold is not None:
        threshold = args.threshold
    candidates, candidate_rows = retrieve_candidates(connection, records)
    cluster_count = union_find(records, connection, threshold)
    elapsed = time.perf_counter() - started
    write_csv(root / "label_metrics.csv", scored, ["notice_id_a", "notice_id_b", "label", "score", "similarity"])
    write_csv(
        root / "candidate_distribution.csv",
        [{"notice_id": notice_id, "portal_id": records[notice_id]["portal_id"], "candidate_count": len(values)} for notice_id, values in candidates.items()],
        ["notice_id", "portal_id", "candidate_count"],
    )
    write_csv(root / "candidate_pairs.csv", [dict(row) for row in connection.execute("SELECT * FROM candidate_pairs")], ["notice_id_a", "notice_id_b", "minhash_score", "pair_score"])
    write_report(root, elapsed, notices, labels, records, candidates, candidate_rows, threshold, scored, cluster_count, db_path)
    print(f"notices={len(notices)} labels={len(labels)} candidates={candidate_rows} clusters={cluster_count} threshold={threshold:.2f} seconds={elapsed:.1f}")
    print(f"database={db_path}")


if __name__ == "__main__":
    main()
