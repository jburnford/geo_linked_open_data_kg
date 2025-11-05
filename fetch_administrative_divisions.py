#!/usr/bin/env python3
"""
Fetch Canadian administrative divisions from Wikidata.

These are stable across time periods and crucial for historical NER:
- Counties
- Townships (geographic and municipal)
- Rural municipalities
- Regional districts
- Census divisions
- Former administrative units

These provide context like "Westmeath Township" which has been stable since 1830s.
"""

import json
import gzip
import time
import os
from typing import List, Dict, Set
from SPARQLWrapper import SPARQLWrapper, JSON as SPARQL_JSON
from tqdm import tqdm


class AdminDivisionFetcher:
    """Fetch administrative divisions from Wikidata."""

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
                'description': binding.get('description', {}).get('value'),
                'instanceOfLabel': binding.get('instanceOfLabel', {}).get('value'),
                'instanceOfQid': binding.get('instanceOf', {}).get('value', '').split('/')[-1] if binding.get('instanceOf') else None
            }
        except Exception as e:
            return None

    def fetch_canadian_admin_divisions(self) -> List[Dict]:
        """
        Fetch all Canadian administrative divisions.

        This includes counties, townships, rural municipalities, regional districts,
        census divisions, and former administrative units.
        """

        query = """
        SELECT DISTINCT ?place ?placeLabel ?coords ?population ?geonamesId
               ?inception ?dissolved ?wikipedia ?description ?instanceOf ?instanceOfLabel
        WHERE {
          # Must be in Canada
          ?place wdt:P17 wd:Q16 .

          # Must be an administrative division type
          ?place wdt:P31 ?instanceOf .
          VALUES ?instanceOf {
            wd:Q13410428   # county of Canada
            wd:Q3558970    # township
            wd:Q96759164   # geographic township of Ontario
            wd:Q2989457    # census division of Canada
            wd:Q3957508    # rural municipality of Canada
            wd:Q3573124    # regional district municipality of British Columbia
            wd:Q15640612   # special area
            wd:Q15979307   # former administrative territorial entity
            wd:Q15310171   # former municipality
            wd:Q1907114    # metropolitan municipality
            wd:Q15617994   # district municipality of British Columbia
            wd:Q2598575    # regional county municipality
            wd:Q3327873    # municipal district of Alberta
            wd:Q21452648   # regional municipality of Ontario
            wd:Q3551781    # town municipality
            wd:Q3551776    # township municipality
            wd:Q3551774    # parish municipality
            wd:Q3551779    # village municipality
            wd:Q3551773    # canton municipality
          }

          OPTIONAL { ?place wdt:P625 ?coords . }
          OPTIONAL { ?place wdt:P1082 ?population . }
          OPTIONAL { ?place wdt:P1566 ?geonamesId . }
          OPTIONAL { ?place wdt:P571 ?inception . }
          OPTIONAL { ?place wdt:P576 ?dissolved . }
          OPTIONAL {
            ?wikipedia schema:about ?place .
            ?wikipedia schema:inLanguage "en" .
            FILTER (SUBSTR(str(?wikipedia), 1, 25) = "https://en.wikipedia.org/")
          }
          OPTIONAL { ?place schema:description ?description . FILTER(LANG(?description) = "en") }

          SERVICE wikibase:label {
            bd:serviceParam wikibase:language "en,fr" .
          }
        }
        """

        print("Querying Canadian administrative divisions...")
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

            print(f"  Found {len(places):,} administrative divisions")
            return places

        except Exception as e:
            print(f"  Error: {e}")
            return []

    def fetch_by_province(self, province_qid: str, province_name: str) -> List[Dict]:
        """
        Fetch administrative divisions by province.

        Some divisions might not be properly linked to Canada but are linked to provinces.
        """

        query = f"""
        SELECT DISTINCT ?place ?placeLabel ?coords ?population ?geonamesId
               ?inception ?dissolved ?wikipedia ?description ?instanceOf ?instanceOfLabel
        WHERE {{
          # Located in specific province
          ?place wdt:P131 wd:{province_qid} .

          # Must be an administrative division type
          ?place wdt:P31 ?instanceOf .
          VALUES ?instanceOf {{
            wd:Q13410428   # county of Canada
            wd:Q3558970    # township
            wd:Q96759164   # geographic township of Ontario
            wd:Q2989457    # census division of Canada
            wd:Q3957508    # rural municipality of Canada
            wd:Q3573124    # regional district municipality of British Columbia
            wd:Q15640612   # special area
            wd:Q15979307   # former administrative territorial entity
            wd:Q15310171   # former municipality
            wd:Q1907114    # metropolitan municipality
            wd:Q15617994   # district municipality of British Columbia
            wd:Q2598575    # regional county municipality
            wd:Q3327873    # municipal district of Alberta
            wd:Q21452648   # regional municipality of Ontario
            wd:Q3551781    # town municipality
            wd:Q3551776    # township municipality
            wd:Q3551774    # parish municipality
            wd:Q3551779    # village municipality
            wd:Q3551773    # canton municipality
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

            print(f"  Found {len(places):,} new divisions in {province_name}")
            return places

        except Exception as e:
            print(f"  Error querying {province_name}: {e}")
            return []

    def fetch_comprehensive(self) -> List[Dict]:
        """Fetch using multiple strategies."""

        all_divisions = []

        # Strategy 1: All Canadian admin divisions
        divisions = self.fetch_canadian_admin_divisions()
        all_divisions.extend(divisions)
        time.sleep(2)

        # Strategy 2: By province (catches divisions not directly linked to Canada)
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
        ]

        for qid, name in provinces:
            province_divisions = self.fetch_by_province(qid, name)
            all_divisions.extend(province_divisions)
            time.sleep(2)

        return all_divisions

    def merge_with_existing(self, new_divisions: List[Dict],
                           existing_file: str) -> List[Dict]:
        """Merge administrative divisions with existing places cache."""

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
        added = 0
        for division in new_divisions:
            if division['qid'] not in existing_qids:
                existing_places.append(division)
                existing_qids.add(division['qid'])
                added += 1

        print(f"\nAdded {added:,} new administrative divisions")
        print(f"Total places: {len(existing_places):,}")

        return existing_places

    def save_cache(self, places: List[Dict], filename: str):
        """Save to cache file."""
        cache_data = {
            'metadata': {
                'fetch_date': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_records': len(places),
                'source': 'Wikidata - Administrative Divisions + Places',
                'strategy': 'Admin divisions by type + province'
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
    fetcher = AdminDivisionFetcher()

    print("="*60)
    print("Canadian Administrative Divisions Fetcher")
    print("="*60)

    # Fetch all administrative divisions
    divisions = fetcher.fetch_comprehensive()

    print(f"\n{'='*60}")
    print(f"Administrative divisions found: {len(divisions):,}")
    print("="*60)

    # Merge with existing places cache
    existing_file = 'wikidata_canada_merged.json'
    all_places = fetcher.merge_with_existing(divisions, existing_file)

    # Save
    fetcher.save_cache(all_places, 'wikidata_canada_with_admin.json')

    # Statistics
    with_wikipedia = sum(1 for p in all_places if p.get('wikipediaUrl'))
    with_geonames = sum(1 for p in all_places if p.get('geonamesId'))
    historical = sum(1 for p in all_places if p.get('dissolvedDate'))

    # Count by type
    admin_types = {}
    for p in all_places:
        if p.get('instanceOfLabel'):
            admin_types[p['instanceOfLabel']] = admin_types.get(p['instanceOfLabel'], 0) + 1

    print(f"\n{'='*60}")
    print("Final Statistics")
    print("="*60)
    print(f"Total entries: {len(all_places):,}")
    print(f"  With Wikipedia: {with_wikipedia:,}")
    print(f"  With GeoNames ID: {with_geonames:,}")
    print(f"  Historical (dissolved): {historical:,}")

    print(f"\nTop Administrative Division Types:")
    sorted_types = sorted(admin_types.items(), key=lambda x: x[1], reverse=True)
    for admin_type, count in sorted_types[:15]:
        if admin_type and any(term in admin_type.lower() for term in ['county', 'township', 'municipality', 'district', 'division']):
            print(f"  {admin_type}: {count:,}")


if __name__ == '__main__':
    main()
