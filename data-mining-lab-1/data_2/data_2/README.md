\# SetuBid Tender Deduplication – Question 2



\## Project Overview



This project implements and evaluates a scalable tender deduplication system for the SetuBid procurement corpus.



The system uses:



\- Text normalization

\- Character 5-gram shingles

\- MinHash

\- Locality-Sensitive Hashing (LSH)

\- SQLite relational storage

\- Indexed candidate retrieval

\- Labelled-pair evaluation

\- Candidate-work measurement

\- Stable opportunity identity



\---



\## Corpus



Measured corpus:



\- \*\*12,000 notices\*\*

\- \*\*260 portals\*\*

\- \*\*900 labelled pairs\*\*

\- SAME: \*\*279 (31.0%)\*\*

\- DIFFERENT: \*\*621 (69.0%)\*\*



The labelled sample is therefore skewed toward DIFFERENT pairs.



\### Directory



```text

data\_2/

├── corpus.sqlite

├── dedupe\_pipeline.py

├── labelled\_pairs.csv

├── notices/

│   ├── part-000.csv

│   ├── part-001.csv

│   ├── part-002.csv

│   ├── part-003.csv

│   ├── part-004.csv

│   ├── part-005.csv

│   ├── part-006.csv

│   └── part-007.csv

├── portal\_profiles.md

├── lsh\_survival\_curve.png

├── measure\_minhash.py

├── measure\_lsh.py

├── measure\_retrieval.py

├── analyze\_hotspots.py

├── analyze\_buckets.py

├── measure\_bucket\_cap.py

├── measure\_boilerplate\_mitigation.py

└── measure\_candidate\_cap.py

