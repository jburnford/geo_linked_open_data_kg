#!/usr/bin/env python3
"""
Resume Wikidata fetching from where we left off.

Appends to existing cache instead of replacing it.
"""

import json
import gzip
import time
from fetch_wikidata_dump import WikidataCanadaDumper

def main():
    cache_file = 'wikidata_canada_places.json'

    dumper = WikidataCanadaDumper(cache_file=cache_file)

    # Load existing cache
    print("Loading existing cache...")
    existing_places = dumper.load_cache()
    existing_count = len(existing_places)
    print(f"Found {existing_count:,} places in cache")

    # Fetch more starting from offset
    offset = existing_count
    batch_size = 5000
    max_batches = 10  # Fetch up to 50k more places

    print(f"\nFetching more places starting at offset {offset:,}...")

    for batch_num in range(max_batches):
        print(f"\nBatch {batch_num + 1}/{max_batches}")
        batch = dumper.fetch_canadian_places_batch(offset=offset, limit=batch_size)

        if not batch:
            print("No more results. Done!")
            break

        existing_places.extend(batch)
        offset += len(batch)
        print(f"  Fetched {len(batch):,} places. Total: {len(existing_places):,}")

        # Save after each batch
        dumper.save_cache(existing_places)

        if len(batch) < batch_size:
            print("Received fewer than batch size. Likely at end of results.")
            break

        time.sleep(2)  # Be nice to Wikidata

    print(f"\n✓ Total places in cache: {len(existing_places):,}")

if __name__ == '__main__':
    main()
