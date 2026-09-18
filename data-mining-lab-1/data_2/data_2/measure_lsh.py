import csv
import glob
import re
import hashlib
import numpy as np
import matplotlib.pyplot as plt

# -----------------------------
# Load labelled pairs
# -----------------------------
with open("labelled_pairs.csv", encoding="utf-8") as f:
    pairs = list(csv.DictReader(f))

ids = {x for p in pairs for x in (p["notice_id_a"], p["notice_id_b"])}

# -----------------------------
# Load required notices
# -----------------------------
notices = {}

for filename in glob.glob("notices/*.csv"):
    with open(filename, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["notice_id"] in ids:
                notices[row["notice_id"]] = row

print("Labelled pairs:", len(pairs))
print("Unique notices:", len(notices))

# -----------------------------
# Normalize
# -----------------------------
def clean(text):
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def shingles(text):
    text = "  " + text + "  "
    return {
        text[i:i+5]
        for i in range(max(1, len(text)-4))
    }

def hash_shingle(value):
    return int.from_bytes(
        hashlib.blake2b(
            value.encode("utf-8"),
            digest_size=8
        ).digest(),
        "little"
    )

# -----------------------------
# Create shingle hashes once
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

# -----------------------------
# Create 256-value signatures
# -----------------------------
print("Creating signatures...")

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

signatures = {}

for notice_id, hashes in shingle_hashes.items():
    sig = np.empty(256, dtype=np.uint64)

    for i in range(256):
        sig[i] = np.min(hashes * A[i] + B[i])

    signatures[notice_id] = sig

print("Signatures ready.")

# -----------------------------
# Exact Jaccard
# -----------------------------
def exact_jaccard(a, b):
    sa = set(shingle_hashes[a].tolist())
    sb = set(shingle_hashes[b].tolist())

    union = len(sa | sb)

    if union == 0:
        return 1.0

    return len(sa & sb) / union

# -----------------------------
# LSH survival test
# 32 bands x 8 rows
# -----------------------------
BANDS = 32
ROWS = 8

def survives_lsh(a, b):
    sa = signatures[a]
    sb = signatures[b]

    for band in range(BANDS):
        start = band * ROWS
        end = start + ROWS

        if np.array_equal(sa[start:end], sb[start:end]):
            return True

    return False

# -----------------------------
# Measure all labelled pairs
# -----------------------------
results = []

print("Testing LSH survival...")

for p in pairs:
    a = p["notice_id_a"]
    b = p["notice_id_b"]

    exact = exact_jaccard(a, b)
    survived = survives_lsh(a, b)

    results.append({
        "exact_similarity": exact,
        "label": p["label"],
        "survived": survived
    })

# -----------------------------
# Similarity bins
# -----------------------------
bins = [
    (0.0, 0.1),
    (0.1, 0.2),
    (0.2, 0.3),
    (0.3, 0.4),
    (0.4, 0.5),
    (0.5, 0.6),
    (0.6, 0.7),
    (0.7, 0.8),
    (0.8, 0.9),
    (0.9, 1.0)
]

print()
print("==========================================")
print("LSH SURVIVAL PROBABILITY")
print("==========================================")
print("Similarity | P(survive) | pairs")

plot_x = []
plot_y = []

for low, high in bins:

    selected = [
        r for r in results
        if low <= r["exact_similarity"] < high
        or (high == 1.0 and low <= r["exact_similarity"] <= high)
    ]

    if selected:
        probability = sum(
            r["survived"] for r in selected
        ) / len(selected)

        print(
            f"{low:.1f}-{high:.1f}     | "
            f"{probability:.4f}       | "
            f"{len(selected)}"
        )

        plot_x.append((low + high) / 2)
        plot_y.append(probability)

# -----------------------------
# Operating point
# -----------------------------
operating_threshold = 0.75

operating_pairs = [
    r for r in results
    if r["label"] == "same"
    and r["exact_similarity"] >= operating_threshold
]

operating_survived = sum(
    r["survived"] for r in operating_pairs
)

operating_recall = (
    operating_survived / len(operating_pairs)
    if operating_pairs else 0
)

print()
print("OPERATING POINT")
print("Threshold:", operating_threshold)
print("High-similarity SAME pairs:", len(operating_pairs))
print("Survived:", operating_survived)
print("Candidate-stage recall:", round(operating_recall, 4))

# -----------------------------
# Plot
# -----------------------------
plt.figure(figsize=(9, 6))
plt.plot(plot_x, plot_y, marker="o")
plt.axvline(
    operating_threshold,
    linestyle="--",
    label="Operating point = 0.75"
)

plt.xlabel("True Jaccard similarity")
plt.ylabel("Probability pair survives LSH")
plt.title("LSH Candidate Survival vs True Similarity")
plt.ylim(0, 1.05)
plt.grid(True)
plt.legend()
plt.tight_layout()

plt.savefig(
    "lsh_survival_curve.png",
    dpi=200
)

print()
print("Plot saved as: lsh_survival_curve.png")