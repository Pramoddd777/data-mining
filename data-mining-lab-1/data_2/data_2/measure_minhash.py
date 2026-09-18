import csv
import glob
import re
import hashlib
import numpy as np

# -----------------------------
# Load labelled pairs
# -----------------------------
with open("labelled_pairs.csv", encoding="utf-8") as f:
    pairs = list(csv.DictReader(f))

ids = {x for p in pairs for x in (p["notice_id_a"], p["notice_id_b"])}

# -----------------------------
# Load only notices needed
# -----------------------------
notices = {}

for filename in glob.glob("notices/*.csv"):
    with open(filename, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["notice_id"] in ids:
                notices[row["notice_id"]] = row

print("Labelled pairs:", len(pairs))
print("Unique notices needed:", len(notices))

# -----------------------------
# Normalization
# -----------------------------
def clean(text):
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# -----------------------------
# Character 5-gram shingles
# -----------------------------
def shingles(text):
    text = "  " + text + "  "
    return {
        text[i:i+5]
        for i in range(max(1, len(text)-4))
    }

# -----------------------------
# Stable 64-bit hash
# -----------------------------
def hash_shingle(value):
    return int.from_bytes(
        hashlib.blake2b(
            value.encode("utf-8"),
            digest_size=8
        ).digest(),
        "little"
    )

# -----------------------------
# Create shingle hashes ONCE
# -----------------------------
print("Creating shingle hashes...")

shingle_hashes = {}

for notice_id, row in notices.items():
    text = clean(row["title"] + " " + row["body"])
    sh = shingles(text)

    shingle_hashes[notice_id] = np.array(
        [hash_shingle(x) for x in sh],
        dtype=np.uint64
    )

print("Shingle hashes created.")

# -----------------------------
# Fixed random hash parameters
# -----------------------------
PRIME = np.uint64(18446744073709551557)

rng = np.random.default_rng(42)

A = rng.integers(
    1,
    2**64 - 1,
    size=256,
    dtype=np.uint64
)

B = rng.integers(
    0,
    2**64 - 1,
    size=256,
    dtype=np.uint64
)

# -----------------------------
# Calculate signature ONCE
# -----------------------------
print("Creating 256-value signatures...")

signatures = {}

for notice_id, hashes in shingle_hashes.items():

    sig = np.empty(256, dtype=np.uint64)

    for i in range(256):
        transformed = hashes * A[i] + B[i]
        sig[i] = np.min(transformed)

    signatures[notice_id] = sig

print("Signatures created.")

# -----------------------------
# Exact Jaccard using hashes
# -----------------------------
def exact_jaccard(a, b):
    sa = set(shingle_hashes[a].tolist())
    sb = set(shingle_hashes[b].tolist())

    union = len(sa | sb)

    if union == 0:
        return 1.0

    return len(sa & sb) / union

# -----------------------------
# Measure error
# -----------------------------
print()
print("======================================")
print("MINHASH ACCURACY MEASUREMENT")
print("======================================")

for k in [64, 128, 256]:

    errors = []

    for p in pairs:

        a = p["notice_id_a"]
        b = p["notice_id_b"]

        estimated = np.mean(
            signatures[a][:k] == signatures[b][:k]
        )

        exact = exact_jaccard(a, b)

        errors.append(abs(estimated - exact))

    mae = np.mean(errors)

    print(
        f"{k} permutations: "
        f"MAE={mae:.6f} "
        f"MaxError={max(errors):.6f}"
    )