#!/usr/bin/env python3
"""
Comprehensive Canadian Wikidata Fetcher

Strategy: Query by different criteria to avoid timeout issues and get
complete coverage, especially for historically important places.

Approaches:
1. Query by province/territory (13 separate queries)
2. Query by type (cities, towns, villages, historical places separately)
3. Query places with Wikipedia articles (high priority)
4. Query places with GeoNames IDs (for matching)
"""

import json
import gzip
import time
from typing import List, Dict, Set
from SPARQLWrapper import SPARQLWrapper, JSON as SPARQL_JSON
from tqdm import tqdm


class ComprehensiveWikidataFetcher:
    """Fetch Canadian places by multiple strategies."""

    def __init__(self):
        self.sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
        self.sparql.setReturnFormat(SPARQL_JSON)
        self.sparql.setTimeout(300)
        self.user_agent = "CanadianHistoricalResearch/1.0"
        self.sparql.addCustomHttpHeader("User-Agent", self.user_agent)
        self.all_qids: Set[str] = set()

    def _parse_binding(self, binding: Dict) -> Dict:
        """Parse SPARQL binding."""
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
                'wikipediaUrl': binding.get('wikipedia', {}).get('value'),
                'description': binding.get('description', {}).get('value')
            }
        except Exception as e:
            return None

    def fetch_by_province(self, province_qid: str, province_name: str) -> List[Dict]:
        """Fetch all places in a specific province/territory."""

        query = f"""
        SELECT DISTINCT ?place ?placeLabel ?coords ?population ?geonamesId
               ?inception ?dissolved ?wikipedia ?description
        WHERE {{
          # Located in specific province/territory
          ?place wdt:P131* wd:{province_qid} .
          ?place wdt:P17 wd:Q16 .  # Canada

          # Must be a settlement
          ?place wdt:P31/wdt:P279* ?type .
          VALUES ?type {{
            wd:Q486972    # human settlement
            wd:Q515       # city
            wd:Q3957      # town
            wd:Q532       # village
            wd:Q5084      # hamlet
            wd:Q15063611  # ghost town
            wd:Q1637706   # unincorporated community
          }}

          OPTIONAL {{ ?place wdt:P625 ?coords . }}
          OPTIONAL {{ ?place wdt:P1082 ?population . }}
          OPTIONAL {{ ?place wdt:P1566 ?geonamesId . }}
          OPTIONAL {{ ?place wdt:P571 ?inception . }}
          OPTIONAL {{ ?place wdt:P576 ?dissolved . }}
          OPTIONAL {{
            ?wikipedia schema:about ?place .
            ?wikipedia schema:inLanguage "en" .
            FILTER (SUBSTR(str(?wikipedia), 1, 25) = "https://en.wikipedia.org/")
          }}
          OPTIONAL {{ ?place schema:description ?description . FILTER(LANG(?description) = "en") }}

          SERVICE wikibase:label {{
            bd:serviceParam wikibase:language "en,fr" .
          }}
        }}
        """

        print(f"\nQuerying {province_name}...")
        self.sparql.setQuery(query)

        try:
            results = self.sparql.query().convert()
            bindings = results.get('results', {}).get('bindings', [])

            places = []
            for b in bindings:
                place = self._parse_binding(b)
                if place and place['qid'] not in self.all_qids:
                    places.append(place)
                    self.all_qids.add(place['qid'])

            print(f"  Found {len(places):,} new places in {province_name}")
            return places

        except Exception as e:
            print(f"  Error querying {province_name}: {e}")
            return []

    def fetch_places_with_wikipedia(self) -> List[Dict]:
        """Fetch places that have English Wikipedia articles (high priority)."""

        query = """
        SELECT DISTINCT ?place ?placeLabel ?coords ?population ?geonamesId
               ?inception ?dissolved ?wikipedia ?description
        WHERE {
          ?place wdt:P17 wd:Q16 .  # Canada

          # Must have Wikipedia article
          ?wikipedia schema:about ?place .
          ?wikipedia schema:inLanguage "en" .
          FILTER (SUBSTR(str(?wikipedia), 1, 25) = "https://en.wikipedia.org/")

          # Must be a settlement
          ?place wdt:P31/wdt:P279* ?type .
          VALUES ?type {
            wd:Q486972    # human settlement
            wd:Q515       # city
            wd:Q3957      # town
            wd:Q532       # village
            wd:Q5084      # hamlet
            wd:Q15063611  # ghost town
            wd:Q1637706   # unincorporated community
          }

          OPTIONAL { ?place wdt:P625 ?coords . }
          OPTIONAL { ?place wdt:P1082 ?population . }
          OPTIONAL { ?place wdt:P1566 ?geonamesId . }
          OPTIONAL { ?place wdt:P571 ?inception . }
          OPTIONAL { ?place wdt:P576 ?dissolved . }
          OPTIONAL { ?place schema:description ?description . FILTER(LANG(?description) = "en") }

          SERVICE wikibase:label {
            bd:serviceParam wikibase:language "en,fr" .
          }
        }
        LIMIT 25000
        """

        print("\nQuerying places with Wikipedia articles (high priority)...")
        self.sparql.setQuery(query)

        try:
            results = self.sparql.query().convert()
            bindings = results.get('results', {}).get('bindings', [])

            places = []
            for b in bindings:
                place = self._parse_binding(b)
                if place and place['qid'] not in self.all_qids:
                    places.append(place)
                    self.all_qids.add(place['qid'])

            print(f"  Found {len(places):,} new places with Wikipedia")
            return places

        except Exception as e:
            print(f"  Error: {e}")
            return []

    def fetch_all_comprehensive(self) -> List[Dict]:
        """Fetch comprehensively using multiple strategies."""

        all_places = []

        # Canadian provinces and territories with Wikidata IDs
        provinces = [
            ('Q1904', 'Ontario'),
            ('Q176', 'Quebec'),
            ('Q1951', 'Nova Scotia'),
            ('Q1965', 'New Brunswick'),
            ('Q1140', 'Manitoba'),
            ('Q1948', 'British Columbia'),
            ('Q1979', 'Prince Edward Island'),
            ('Q1989', 'Saskatchewan'),
            ('Q1951', 'Alberta'),
            ('Q2007', 'Newfoundland and Labrador'),
            ('Q2009', 'Northwest Territories'),
            ('Q2023', 'Yukon'),
            ('Q2023', 'Nunavut')
        ]

        print("="*60)
        print("Comprehensive Canadian Wikidata Fetch")
        print("="*60)

        # Strategy 1: Fetch places with Wikipedia first (most important)
        wikipedia_places = self.fetch_places_with_wikipedia()
        all_places.extend(wikipedia_places)
        time.sleep(2)

        # Strategy 2: Fetch by province
        for qid, name in provinces:
            province_places = self.fetch_by_province(qid, name)
            all_places.extend(province_places)
            time.sleep(2)  # Be nice to Wikidata

        print(f"\n{'='*60}")
        print(f"Total unique places fetched: {len(self.all_qids):,}")
        print("="*60)

        return all_places

    def save_cache(self, places: List[Dict], filename: str):
        """Save to cache file."""
        cache_data = {
            'metadata': {
                'fetch_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_records': len(places),
                'source': 'Wikidata Query Service - Comprehensive',
                'strategy': 'Wikipedia + Province queries'
            },
            'places': places
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        with gzip.open(filename + '.gz', 'wt', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False)

        import os
        file_size = os.path.getsize(filename) / (1024 * 1024)
        compressed_size = os.path.getsize(filename + '.gz') / (1024 * 1024)

        print(f"\n✓ Saved cache to {filename} ({file_size:.1f} MB)")
        print(f"✓ Saved compressed to {filename}.gz ({compressed_size:.1f} MB)")


def main():
    fetcher = ComprehensiveWikidataFetcher()

    places = fetcher.fetch_all_comprehensive()

    # Save to new cache file
    fetcher.save_cache(places, 'wikidata_canada_comprehensive.json')

    # Print statistics
    with_wikipedia = sum(1 for p in places if p.get('wikipediaUrl'))
    with_geonames = sum(1 for p in places if p.get('geonamesId'))
    with_population = sum(1 for p in places if p.get('population'))
    historical = sum(1 for p in places if p.get('dissolvedDate'))

    print(f"\n{'='*60}")
    print("Final Statistics")
    print("="*60)
    print(f"Total places: {len(places):,}")
    print(f"  With Wikipedia: {with_wikipedia:,} ({(with_wikipedia/len(places))*100:.1f}%)")
    print(f"  With GeoNames ID: {with_geonames:,} ({(with_geonames/len(places))*100:.1f}%)")
    print(f"  With population: {with_population:,}")
    print(f"  Historical (dissolved): {historical:,}")


if __name__ == '__main__':
    main()
