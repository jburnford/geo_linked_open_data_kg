#!/usr/bin/env python3
"""Quick analysis of US feature codes in allCountries.txt"""

from collections import Counter
import sys

feature_counts = Counter()
us_total = 0

print("Analyzing US feature codes...")

with open('/home/jic823/CanadaNeo4j/allCountries.txt', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if i % 1000000 == 0:
            print(f"Processed {i:,} lines...", file=sys.stderr)

        fields = line.strip().split('\t')
        if len(fields) < 8:
            continue

        country = fields[8]  # country code
        if country == 'US':
            us_total += 1
            feature_class = fields[6]
            feature_code = fields[7]
            feature_counts[f"{feature_class}.{feature_code}"] += 1

print(f"\nTotal US records: {us_total:,}")
print(f"\nTop 50 Feature Codes:")
print("="*60)

for feature, count in feature_counts.most_common(50):
    pct = (count / us_total * 100) if us_total > 0 else 0
    print(f"{feature:20s} {count:>10,}  ({pct:5.1f}%)")
