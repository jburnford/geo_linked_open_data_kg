#!/usr/bin/env python3
"""
Fetch and cache Canadian Wikidata entries to local JSON file.

This creates a local "dump" of Canadian geographic data from Wikidata
that can be reused without hitting the Wikidata API repeatedly.
"""

import os
import json
import time
from typing import Dict, List
from SPARQLWrapper import SPARQLWrapper, JSON as SPARQL_JSON
from tqdm import tqdm


class WikidataCanadaDumper:
    """Fetch and cache all Canadian location data from Wikidata."""

    def __init__(self, cache_file: str = 'wikidata_canada_cache.json'):
        self.cache_file = cache_file
        self.sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
        self.sparql.setReturnFormat(SPARQL_JSON)
        self.sparql.setTimeout(300)
        self.user_agent = "CanadianHistoricalResearch/1.0 (Historical NER Reconciliation)"
        self.sparql.addCustomHttpHeader("User-Agent", self.user_agent)

    def fetch_canadian_places_batch(self, offset: int = 0, limit: int = 10000) -> List[Dict]:
        """
        Fetch a batch of Canadian places from Wikidata.

        Uses pagination to avoid timeouts on large queries.
        """

        query = f"""
        SELECT DISTINCT ?place ?placeLabel ?coords ?population
               ?geonamesId ?inception ?dissolved ?wikipedia
        WHERE {{
          # Located in Canada
          ?place wdt:P17 wd:Q16 .

          # Must have coordinates (filters out abstract entities)
          ?place wdt:P625 ?coords .

          # Must be a geographic entity
          ?place wdt:P31/wdt:P279* ?instanceOf .
          VALUES ?instanceOf {{
            wd:Q486972    # human settlement
            wd:Q515       # city
            wd:Q3957      # town
            wd:Q532       # village
            wd:Q5084      # hamlet
            wd:Q1549591   # big city
            wd:Q15063611  # ghost town
            wd:Q1637706   # unincorporated community
          }}

          OPTIONAL {{ ?place wdt:P1082 ?population . }}
          OPTIONAL {{ ?place wdt:P1566 ?geonamesId . }}
          OPTIONAL {{ ?place wdt:P571 ?inception . }}
          OPTIONAL {{ ?place wdt:P576 ?dissolved . }}
          OPTIONAL {{
            ?wikipedia schema:about ?place .
            ?wikipedia schema:inLanguage "en" .
            FILTER (SUBSTR(str(?wikipedia), 1, 25) = "https://en.wikipedia.org/")
          }}

          SERVICE wikibase:label {{
            bd:serviceParam wikibase:language "en,fr" .
          }}
        }}
        LIMIT {limit}
        OFFSET {offset}
        """

        self.sparql.setQuery(query)

        try:
            results = self.sparql.query().convert()
            bindings = results.get('results', {}).get('bindings', [])

            places = []
            for b in bindings:
                place = self._parse_binding(b)
                if place:
                    places.append(place)

            return places

        except Exception as e:
            print(f"Error fetching batch at offset {offset}: {e}")
            return []

    def _parse_binding(self, binding: Dict) -> Dict:
        """Parse SPARQL binding into clean dictionary."""

        try:
            place_uri = binding.get('place', {}).get('value', '')
            qid = place_uri.split('/')[-1]

            coords_str = binding.get('coords', {}).get('value', '')
            lat, lon = None, None
            if coords_str:
                try:
                    parts = coords_str.replace('Point(', '').replace(')', '').split()
                    lon = float(parts[0])
                    lat = float(parts[1])
                except:
                    pass

            return {
                'qid': qid,
                'name': binding.get('placeLabel', {}).get('value'),
                'latitude': lat,
                'longitude': lon,
                'population': binding.get('population', {}).get('value'),
                'geonamesId': binding.get('geonamesId', {}).get('value'),
                'inceptionDate': binding.get('inception', {}).get('value', '').split('T')[0] if binding.get('inception') else None,
                'dissolvedDate': binding.get('dissolved', {}).get('value', '').split('T')[0] if binding.get('dissolved') else None,
                'wikipediaUrl': binding.get('wikipedia', {}).get('value')
            }

        except Exception as e:
            print(f"Error parsing binding: {e}")
            return None

    def fetch_all_with_pagination(self) -> List[Dict]:
        """Fetch all Canadian places using pagination."""

        all_places = []
        offset = 0
        batch_size = 5000  # Smaller batches to avoid timeouts

        print("Fetching Canadian places from Wikidata in batches...")

        with tqdm(desc="Fetching batches") as pbar:
            while True:
                batch = self.fetch_canadian_places_batch(offset=offset, limit=batch_size)

                if not batch:
                    break

                all_places.extend(batch)
                pbar.update(len(batch))
                offset += batch_size

                # If we got fewer results than limit, we're done
                if len(batch) < batch_size:
                    break

                # Be nice to Wikidata
                time.sleep(2)

        print(f"\n✓ Fetched {len(all_places):,} places total")
        return all_places

    def save_cache(self, places: List[Dict]):
        """Save fetched data to JSON cache file."""

        cache_data = {
            'metadata': {
                'fetch_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_records': len(places),
                'source': 'Wikidata Query Service'
            },
            'places': places
        }

        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        # Also save compressed version
        import gzip
        compressed_file = self.cache_file + '.gz'
        with gzip.open(compressed_file, 'wt', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False)

        file_size = os.path.getsize(self.cache_file) / (1024 * 1024)
        compressed_size = os.path.getsize(compressed_file) / (1024 * 1024)

        print(f"\n✓ Saved cache to {self.cache_file} ({file_size:.1f} MB)")
        print(f"✓ Saved compressed to {compressed_file} ({compressed_size:.1f} MB)")

    def load_cache(self) -> List[Dict]:
        """Load places from cache file if it exists."""

        if not os.path.exists(self.cache_file):
            # Try compressed version
            compressed_file = self.cache_file + '.gz'
            if os.path.exists(compressed_file):
                import gzip
                with gzip.open(compressed_file, 'rt', encoding='utf-8') as f:
                    cache_data = json.load(f)
                print(f"✓ Loaded {cache_data['metadata']['total_records']:,} places from cache (compressed)")
                return cache_data['places']
            return None

        with open(self.cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)

        print(f"✓ Loaded {cache_data['metadata']['total_records']:,} places from cache")
        print(f"  Fetch date: {cache_data['metadata']['fetch_date']}")

        return cache_data['places']

    def fetch_or_load(self, force_refresh: bool = False) -> List[Dict]:
        """Load from cache if available, otherwise fetch from Wikidata."""

        if not force_refresh:
            cached = self.load_cache()
            if cached:
                return cached

        print("No cache found or refresh requested. Fetching from Wikidata...")
        places = self.fetch_all_with_pagination()
        self.save_cache(places)

        return places


def main():
    """Main execution."""

    print("="*60)
    print("Wikidata Canadian Places Dumper")
    print("="*60)

    dumper = WikidataCanadaDumper(cache_file='wikidata_canada_places.json')

    # Fetch or load cached data
    places = dumper.fetch_or_load(force_refresh=False)

    # Print statistics
    print(f"\n{'='*60}")
    print("Statistics")
    print("="*60)
    print(f"Total places: {len(places):,}")

    with_wikipedia = sum(1 for p in places if p.get('wikipediaUrl'))
    with_geonames = sum(1 for p in places if p.get('geonamesId'))
    with_population = sum(1 for p in places if p.get('population'))
    historical = sum(1 for p in places if p.get('dissolvedDate'))

    print(f"With Wikipedia: {with_wikipedia:,}")
    print(f"With GeoNames ID: {with_geonames:,}")
    print(f"With population: {with_population:,}")
    print(f"Historical (dissolved): {historical:,}")

    print("\n✓ Cache ready for loading into Neo4j!")


if __name__ == '__main__':
    main()
