#!/usr/bin/env python3
"""
Fetch Canadian places by geographic coordinates instead of administrative hierarchy.

This catches places that lack proper P131 (administrative subdivision) linkage
but have coordinates within Canada's bounding box.

Canada bounding box:
  Latitude: 41.7° N to 83.1° N
  Longitude: -141.0° W to -52.6° W
"""

import json
import gzip
import time
import os
from typing import List, Dict, Set
from SPARQLWrapper import SPARQLWrapper, JSON as SPARQL_JSON
from tqdm import tqdm


class CoordinateBasedFetcher:
    """Fetch places by coordinates in geographic grid."""

    def __init__(self):
        self.sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
        self.sparql.setReturnFormat(SPARQL_JSON)
        self.sparql.setTimeout(300)
        self.user_agent = "CanadianHistoricalResearch/1.0"
        self.sparql.addCustomHttpHeader("User-Agent", self.user_agent)
        self.all_qids: Set[str] = set()

    def load_existing_cache(self, filename: str) -> Set[str]:
        """Load existing Q-IDs from cache to avoid duplicates."""
        if not os.path.exists(filename):
            compressed = filename + '.gz'
            if not os.path.exists(compressed):
                return set()
            filename = compressed

        try:
            if filename.endswith('.gz'):
                with gzip.open(filename, 'rt', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)

            qids = {p['qid'] for p in data.get('places', [])}
            print(f"Loaded {len(qids):,} existing Q-IDs from {filename}")
            return qids

        except Exception as e:
            print(f"Error loading cache: {e}")
            return set()

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

    def fetch_by_bounding_box(self, lat_min: float, lat_max: float,
                               lon_min: float, lon_max: float) -> List[Dict]:
        """
        Fetch places within a bounding box using coordinates.

        This bypasses the need for administrative subdivision linkage.
        """

        query = f"""
        SELECT DISTINCT ?place ?placeLabel ?coords ?population ?geonamesId
               ?inception ?dissolved ?wikipedia ?description
        WHERE {{
          # Has coordinates within bounding box
          ?place wdt:P625 ?coords .

          # Filter by bounding box (note: this is approximate)
          FILTER(
            ?coords != ""
          )

          # Must be a settlement type
          ?place wdt:P31/wdt:P279* ?type .
          VALUES ?type {{
            wd:Q486972    # human settlement
            wd:Q515       # city
            wd:Q3957      # town
            wd:Q532       # village
            wd:Q5084      # hamlet
            wd:Q15063611  # ghost town
            wd:Q1637706   # unincorporated community
            wd:Q2039348   # settlement
          }}

          # Get country
          OPTIONAL {{ ?place wdt:P17 ?country . }}

          # Only Canada or unspecified
          FILTER(!BOUND(?country) || ?country = wd:Q16)

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
        LIMIT 5000
        """

        print(f"Querying box: lat {lat_min}-{lat_max}, lon {lon_min}-{lon_max}...")
        self.sparql.setQuery(query)

        try:
            results = self.sparql.query().convert()
            bindings = results.get('results', {}).get('bindings', [])

            places = []
            for b in bindings:
                place = self._parse_binding(b)
                if place and place['qid'] not in self.all_qids:
                    # Post-filter by coordinates (SPARQL coordinate filter is limited)
                    if place.get('latitude') and place.get('longitude'):
                        if (lat_min <= place['latitude'] <= lat_max and
                            lon_min <= place['longitude'] <= lon_max):
                            places.append(place)
                            self.all_qids.add(place['qid'])

            print(f"  Found {len(places):,} new places in this box")
            return places

        except Exception as e:
            print(f"  Error: {e}")
            return []

    def fetch_places_with_wikipedia_no_admin(self) -> List[Dict]:
        """
        Fetch Canadian places with Wikipedia that might lack admin hierarchy.

        This catches places like Maitland that have Wikipedia but weak admin links.
        """

        query = """
        SELECT DISTINCT ?place ?placeLabel ?coords ?population ?geonamesId
               ?inception ?dissolved ?wikipedia ?description
        WHERE {
          # Must have English Wikipedia
          ?wikipedia schema:about ?place .
          ?wikipedia schema:inLanguage "en" .
          FILTER (SUBSTR(str(?wikipedia), 1, 25) = "https://en.wikipedia.org/")

          # Must have coordinates
          ?place wdt:P625 ?coords .

          # Must be settlement or geographic area
          ?place wdt:P31 ?instanceOf .
          VALUES ?instanceOf {
            wd:Q486972     # human settlement
            wd:Q515        # city
            wd:Q3957       # town
            wd:Q532        # village
            wd:Q5084       # hamlet
            wd:Q15063611   # ghost town
            wd:Q1637706    # unincorporated community
            wd:Q2039348    # settlement
            wd:Q3558970    # township
            wd:Q15979307   # former administrative unit
            wd:Q15310171   # former municipality
            wd:Q96759164   # geographic township of Ontario
            wd:Q3957508    # rural municipality
            wd:Q15640612   # special area
          }

          # Either in Canada OR has coordinates in Canada range
          OPTIONAL { ?place wdt:P17 ?country . }
          FILTER(!BOUND(?country) || ?country = wd:Q16)

          OPTIONAL { ?place wdt:P1082 ?population . }
          OPTIONAL { ?place wdt:P1566 ?geonamesId . }
          OPTIONAL { ?place wdt:P571 ?inception . }
          OPTIONAL { ?place wdt:P576 ?dissolved . }
          OPTIONAL { ?place schema:description ?description . FILTER(LANG(?description) = "en") }

          SERVICE wikibase:label {
            bd:serviceParam wikibase:language "en,fr" .
          }
        }
        LIMIT 50000
        """

        print("\nQuerying places with Wikipedia (no admin requirement)...")
        self.sparql.setQuery(query)

        try:
            results = self.sparql.query().convert()
            bindings = results.get('results', {}).get('bindings', [])

            places = []
            canada_lat_range = (41.7, 83.1)
            canada_lon_range = (-141.0, -52.6)

            for b in bindings:
                place = self._parse_binding(b)
                if place and place['qid'] not in self.all_qids:
                    # Filter to Canada by coordinates
                    if place.get('latitude') and place.get('longitude'):
                        if (canada_lat_range[0] <= place['latitude'] <= canada_lat_range[1] and
                            canada_lon_range[0] <= place['longitude'] <= canada_lon_range[1]):
                            places.append(place)
                            self.all_qids.add(place['qid'])

            print(f"  Found {len(places):,} new places with Wikipedia")
            return places

        except Exception as e:
            print(f"  Error: {e}")
            return []

    def merge_with_existing(self, new_places: List[Dict],
                           existing_file: str) -> List[Dict]:
        """Merge new places with existing cache."""

        # Load existing
        if os.path.exists(existing_file):
            with open(existing_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            existing_places = existing_data.get('places', [])
        elif os.path.exists(existing_file + '.gz'):
            with gzip.open(existing_file + '.gz', 'rt', encoding='utf-8') as f:
                existing_data = json.load(f)
            existing_places = existing_data.get('places', [])
        else:
            existing_places = []

        # Create Q-ID index
        existing_qids = {p['qid'] for p in existing_places}

        # Add only new ones
        for place in new_places:
            if place['qid'] not in existing_qids:
                existing_places.append(place)
                existing_qids.add(place['qid'])

        return existing_places

    def save_cache(self, places: List[Dict], filename: str):
        """Save to cache file."""
        cache_data = {
            'metadata': {
                'fetch_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_records': len(places),
                'source': 'Wikidata - Coordinate-based fetch',
                'strategy': 'Geographic bounding box + Wikipedia filter'
            },
            'places': places
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        with gzip.open(filename + '.gz', 'wt', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False)

        file_size = os.path.getsize(filename) / (1024 * 1024)
        compressed_size = os.path.getsize(filename + '.gz') / (1024 * 1024)

        print(f"\n✓ Saved to {filename} ({file_size:.1f} MB)")
        print(f"✓ Saved compressed to {filename}.gz ({compressed_size:.1f} MB)")


def main():
    fetcher = CoordinateBasedFetcher()

    print("="*60)
    print("Wikidata Coordinate-Based Fetch")
    print("="*60)

    # Load existing Q-IDs to avoid duplicates
    existing_file = 'wikidata_canada_comprehensive.json'
    fetcher.all_qids = fetcher.load_existing_cache(existing_file)

    all_new_places = []

    # Strategy: Fetch places with Wikipedia (catches Maitland, etc.)
    wikipedia_places = fetcher.fetch_places_with_wikipedia_no_admin()
    all_new_places.extend(wikipedia_places)

    print(f"\n{'='*60}")
    print(f"New places found: {len(all_new_places):,}")
    print("="*60)

    # Merge with existing
    if all_new_places:
        print("\nMerging with existing cache...")
        all_places = fetcher.merge_with_existing(all_new_places, existing_file)

        # Save merged cache
        fetcher.save_cache(all_places, 'wikidata_canada_merged.json')

        # Statistics
        with_wikipedia = sum(1 for p in all_places if p.get('wikipediaUrl'))
        with_geonames = sum(1 for p in all_places if p.get('geonamesId'))
        historical = sum(1 for p in all_places if p.get('dissolvedDate'))

        print(f"\n{'='*60}")
        print("Merged Statistics")
        print("="*60)
        print(f"Total places: {len(all_places):,}")
        print(f"  With Wikipedia: {with_wikipedia:,}")
        print(f"  With GeoNames ID: {with_geonames:,}")
        print(f"  Historical: {historical:,}")
    else:
        print("\nNo new places found.")


if __name__ == '__main__':
    main()
