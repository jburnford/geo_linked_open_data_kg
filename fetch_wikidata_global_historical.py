#!/usr/bin/env python3
"""
Global Wikidata Fetcher with Historical Colonies Support

Strategy for avoiding timeouts while capturing historical context:
1. Query by country + entity type (small batches)
2. Prioritize historical colonial entities
3. Cache everything incrementally
4. Resume-friendly (skip already cached countries)

Historical Entity Types to Include:
- Settlements (current, historical, dissolved)
- Colonial entities (colonies, trading posts, forts, missions)
- Historical administrative divisions (territories, protectorates)
- Indigenous settlements and reserves
"""

import json
import gzip
import time
import os
from typing import List, Dict, Set, Optional
from SPARQLWrapper import SPARQLWrapper, JSON as SPARQL_JSON
from tqdm import tqdm
from datetime import datetime


class GlobalHistoricalWikidataFetcher:
    """Fetch global places with historical colonial context."""

    def __init__(self, cache_dir: str = 'wikidata_cache'):
        self.sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
        self.sparql.setReturnFormat(SPARQL_JSON)
        self.sparql.setTimeout(180)  # Reduced to 3 minutes
        self.user_agent = "GlobalHistoricalKnowledgeGraph/1.0"
        self.sparql.addCustomHttpHeader("User-Agent", self.user_agent)

        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

        self.all_qids: Set[str] = set()

    def _parse_binding(self, binding: Dict) -> Optional[Dict]:
        """Parse SPARQL binding with comprehensive properties."""
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

            # Parse instance types
            instance_uri = binding.get('instanceOf', {}).get('value', '')
            instance_qid = instance_uri.split('/')[-1] if instance_uri else None

            # Parse alternate names (concatenated with |)
            alt_names_str = binding.get('altNames', {}).get('value', '')
            alt_names = [n.strip() for n in alt_names_str.split('|') if n.strip()] if alt_names_str else []

            official_names_str = binding.get('officialNames', {}).get('value', '')
            official_names = [n.strip() for n in official_names_str.split('|') if n.strip()] if official_names_str else []

            # Helper function to extract QID from URI
            def extract_qid(uri_str):
                if not uri_str:
                    return None
                return uri_str.split('/')[-1] if '/' in uri_str else None

            return {
                'qid': qid,
                'name': binding.get('placeLabel', {}).get('value'),
                'latitude': lat,
                'longitude': lon,
                'population': binding.get('population', {}).get('value'),
                'geonamesId': binding.get('geonamesId', {}).get('value'),

                # Temporal data
                'inceptionDate': binding.get('inception', {}).get('value', '').split('T')[0] if binding.get('inception') else None,
                'dissolvedDate': binding.get('dissolved', {}).get('value', '').split('T')[0] if binding.get('dissolved') else None,
                'abolishedDate': binding.get('abolished', {}).get('value', '').split('T')[0] if binding.get('abolished') else None,

                # Context
                'wikipediaUrl': binding.get('wikipedia', {}).get('value'),
                'description': binding.get('description', {}).get('value'),
                'instanceOfQid': instance_qid,
                'instanceOfLabel': binding.get('instanceOfLabel', {}).get('value'),
                'countryQid': binding.get('country', {}).get('value', '').split('/')[-1] if binding.get('country') else None,

                # NEW: Alternate names
                'alternateNames': alt_names,
                'officialNames': official_names,
                'nativeLabel': binding.get('nativeLabel', {}).get('value'),
                'nickname': binding.get('nickname', {}).get('value'),

                # NEW: Historical succession
                'replacesQid': extract_qid(binding.get('replaces', {}).get('value')),
                'replacedByQid': extract_qid(binding.get('replacedBy', {}).get('value')),
                'followsQid': extract_qid(binding.get('follows', {}).get('value')),
                'followedByQid': extract_qid(binding.get('followedBy', {}).get('value')),

                # NEW: Colonial/founding context
                'foundedByQid': extract_qid(binding.get('foundedBy', {}).get('value')),
                'foundedByLabel': binding.get('foundedByLabel', {}).get('value'),
                'ownedByQid': extract_qid(binding.get('ownedBy', {}).get('value')),
                'ownedByLabel': binding.get('ownedByLabel', {}).get('value'),
                'capitalOfQid': extract_qid(binding.get('capitalOf', {}).get('value')),
                'capitalOfLabel': binding.get('capitalOfLabel', {}).get('value'),

                # NEW: Cross-database identifiers
                'gndId': binding.get('gndId', {}).get('value'),
                'viafId': binding.get('viafId', {}).get('value'),
                'locId': binding.get('locId', {}).get('value'),
                'tgnId': binding.get('tgnId', {}).get('value'),
                'osmId': binding.get('osmId', {}).get('value'),
                'wofId': binding.get('wofId', {}).get('value'),

                # NEW: Historic context
                'historicCountyQid': extract_qid(binding.get('historicCounty', {}).get('value')),
                'historicCountyLabel': binding.get('historicCountyLabel', {}).get('value'),
                'officialWebsite': binding.get('officialWebsite', {}).get('value'),
            }
        except Exception as e:
            print(f"      Warning: Error parsing place: {e}")
            return None

    def get_historical_colonial_types(self) -> str:
        """Return SPARQL VALUES clause for historical colonial entity types."""
        return """
            wd:Q486972    # human settlement
            wd:Q515       # city
            wd:Q3957      # town
            wd:Q532       # village
            wd:Q5084      # hamlet
            wd:Q15063611  # ghost town
            wd:Q1637706   # unincorporated community

            # Colonial entities
            wd:Q133156    # colony
            wd:Q1750636   # colonial trading post
            wd:Q1785071   # fort
            wd:Q44613     # monastery/mission
            wd:Q1620908   # British overseas territory
            wd:Q202216    # French colonial empire entity
            wd:Q1195098   # Spanish colonial entity
            wd:Q174844    # Portuguese colonial entity

            # Historical administrative
            wd:Q82794     # geographic region
            wd:Q1907114   # historical country
            wd:Q1620908   # British overseas territory
            wd:Q15284     # municipality (historical)
            wd:Q1852859   # protectorate
            wd:Q1145276   # dependent territory

            # Indigenous settlements
            wd:Q12223     # Indian reserve
            wd:Q17326919  # Indigenous territory
        """

    def fetch_country_places(self, country_qid: str, country_name: str, limit: int = 5000) -> List[Dict]:
        """
        Fetch all historical and current places for a specific country with comprehensive properties.

        Uses LIMIT to avoid timeouts on large countries.
        """
        query = f"""
        SELECT DISTINCT ?place ?placeLabel ?coords ?population ?geonamesId
               ?inception ?dissolved ?abolished ?wikipedia ?description
               ?instanceOf ?instanceOfLabel ?country

               # Alternate names (aggregated)
               (GROUP_CONCAT(DISTINCT ?altLabel; separator="|") AS ?altNames)
               (GROUP_CONCAT(DISTINCT ?officialName; separator="|") AS ?officialNames)
               ?nativeLabel ?nickname

               # Historical succession
               ?replaces ?replacedBy ?follows ?followedBy

               # Colonial/founding context
               ?foundedBy ?foundedByLabel ?ownedBy ?ownedByLabel
               ?capitalOf ?capitalOfLabel

               # Cross-database identifiers
               ?gndId ?viafId ?locId ?tgnId ?osmId ?wofId

               # Historic context
               ?historicCounty ?historicCountyLabel ?officialWebsite

        WHERE {{
          # Country filter
          ?place wdt:P17 wd:{country_qid} .

          # Must be a relevant entity type
          ?place wdt:P31 ?instanceOf .
          VALUES ?instanceOf {{
            {self.get_historical_colonial_types()}
          }}

          # Basic properties
          OPTIONAL {{ ?place wdt:P625 ?coords . }}
          OPTIONAL {{ ?place wdt:P1082 ?population . }}
          OPTIONAL {{ ?place wdt:P1566 ?geonamesId . }}
          OPTIONAL {{ ?place wdt:P571 ?inception . }}
          OPTIONAL {{ ?place wdt:P576 ?dissolved . }}
          OPTIONAL {{ ?place wdt:P576 ?abolished . }}

          # Wikipedia and description
          OPTIONAL {{
            ?wikipedia schema:about ?place .
            ?wikipedia schema:inLanguage "en" .
            FILTER (SUBSTR(str(?wikipedia), 1, 25) = "https://en.wikipedia.org/")
          }}
          OPTIONAL {{ ?place schema:description ?description . FILTER(LANG(?description) = "en") }}

          # Alternate names - critical for NER matching
          OPTIONAL {{ ?place skos:altLabel ?altLabel . FILTER(LANG(?altLabel) = "en") }}
          OPTIONAL {{ ?place wdt:P1448 ?officialName . }}
          OPTIONAL {{ ?place wdt:P1705 ?nativeLabel . }}
          OPTIONAL {{ ?place wdt:P1449 ?nickname . }}

          # Historical succession
          OPTIONAL {{ ?place wdt:P1365 ?replaces . }}
          OPTIONAL {{ ?place wdt:P1366 ?replacedBy . }}
          OPTIONAL {{ ?place wdt:P155 ?follows . }}
          OPTIONAL {{ ?place wdt:P156 ?followedBy . }}

          # Colonial/founding context
          OPTIONAL {{ ?place wdt:P112 ?foundedBy . }}
          OPTIONAL {{ ?place wdt:P127 ?ownedBy . }}
          OPTIONAL {{ ?place wdt:P1376 ?capitalOf . }}

          # Cross-database identifiers
          OPTIONAL {{ ?place wdt:P227 ?gndId . }}
          OPTIONAL {{ ?place wdt:P214 ?viafId . }}
          OPTIONAL {{ ?place wdt:P244 ?locId . }}
          OPTIONAL {{ ?place wdt:P1667 ?tgnId . }}
          OPTIONAL {{ ?place wdt:P402 ?osmId . }}
          OPTIONAL {{ ?place wdt:P6766 ?wofId . }}

          # Historic context
          OPTIONAL {{ ?place wdt:P7959 ?historicCounty . }}
          OPTIONAL {{ ?place wdt:P856 ?officialWebsite . }}

          SERVICE wikibase:label {{
            bd:serviceParam wikibase:language "en" .
          }}
        }}
        GROUP BY ?place ?placeLabel ?coords ?population ?geonamesId
                 ?inception ?dissolved ?abolished ?wikipedia ?description
                 ?instanceOf ?instanceOfLabel ?country
                 ?nativeLabel ?nickname
                 ?replaces ?replacedBy ?follows ?followedBy
                 ?foundedBy ?foundedByLabel ?ownedBy ?ownedByLabel
                 ?capitalOf ?capitalOfLabel
                 ?gndId ?viafId ?locId ?tgnId ?osmId ?wofId
                 ?historicCounty ?historicCountyLabel ?officialWebsite
        LIMIT {limit}
        """

        print(f"  Querying {country_name} ({country_qid})...")
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

            print(f"    Found {len(places):,} new places in {country_name}")
            return places

        except Exception as e:
            print(f"    Error querying {country_name}: {e}")
            return []

    def get_cached_countries(self) -> Set[str]:
        """Get list of countries already cached."""
        cached = set()
        for filename in os.listdir(self.cache_dir):
            if filename.startswith('wikidata_') and filename.endswith('.json'):
                # Extract country code from filename like wikidata_US.json
                country_code = filename.replace('wikidata_', '').replace('.json', '')
                cached.add(country_code)
        return cached

    def save_country_cache(self, country_code: str, places: List[Dict]):
        """Save country data to individual cache file."""
        cache_file = os.path.join(self.cache_dir, f'wikidata_{country_code}.json')

        cache_data = {
            'metadata': {
                'country_code': country_code,
                'fetch_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total_records': len(places),
                'source': 'Wikidata Query Service - Historical',
                'strategy': 'Country + Historical Colonial Types'
            },
            'places': places
        }

        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        print(f"    ✓ Cached to {cache_file}")

    def fetch_priority_countries(self, countries: List[tuple], batch_limit: int = 10000):
        """
        Fetch places for priority countries.

        Args:
            countries: List of (country_code, country_qid, country_name) tuples
            batch_limit: Max records per country query (prevents timeout)
        """
        cached_countries = self.get_cached_countries()

        for country_code, country_qid, country_name in countries:
            # Skip if already cached
            if country_code in cached_countries:
                print(f"  ✓ {country_name} already cached, skipping")
                continue

            # Fetch places
            places = self.fetch_country_places(country_qid, country_name, limit=batch_limit)

            # Save to cache
            if places:
                self.save_country_cache(country_code, places)

            # Rate limiting - be nice to Wikidata
            time.sleep(3)

    def consolidate_caches(self, output_file: str):
        """Consolidate all country caches into single file."""
        print("\nConsolidating country caches...")

        all_places = []
        all_qids = set()

        for filename in sorted(os.listdir(self.cache_dir)):
            if not filename.startswith('wikidata_') or not filename.endswith('.json'):
                continue

            filepath = os.path.join(self.cache_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for place in data['places']:
                if place['qid'] not in all_qids:
                    all_places.append(place)
                    all_qids.add(place['qid'])

        # Save consolidated file
        consolidated = {
            'metadata': {
                'fetch_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total_records': len(all_places),
                'source': 'Wikidata Query Service - Global Historical',
                'countries_included': len([f for f in os.listdir(self.cache_dir) if f.startswith('wikidata_')])
            },
            'places': all_places
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(consolidated, f, indent=2, ensure_ascii=False)

        with gzip.open(output_file + '.gz', 'wt', encoding='utf-8') as f:
            json.dump(consolidated, f, ensure_ascii=False)

        print(f"✓ Consolidated {len(all_places):,} places from {len(all_qids)} unique entities")
        print(f"✓ Saved to {output_file} and {output_file}.gz")


def get_colonial_priority_countries():
    """
    Return list of countries with significant colonial history.

    Format: (country_code, country_qid, country_name)
    """
    return [
        # Former British colonies
        ('US', 'Q30', 'United States'),
        ('CA', 'Q16', 'Canada'),
        ('GB', 'Q145', 'United Kingdom'),
        ('AU', 'Q408', 'Australia'),
        ('NZ', 'Q664', 'New Zealand'),
        ('IN', 'Q668', 'India'),
        ('PK', 'Q843', 'Pakistan'),
        ('ZA', 'Q258', 'South Africa'),
        ('KE', 'Q114', 'Kenya'),
        ('NG', 'Q1033', 'Nigeria'),
        ('HK', 'Q8646', 'Hong Kong'),
        ('SG', 'Q334', 'Singapore'),
        ('MY', 'Q833', 'Malaysia'),

        # Former French colonies
        ('FR', 'Q142', 'France'),
        ('DZ', 'Q262', 'Algeria'),
        ('MA', 'Q1028', 'Morocco'),
        ('TN', 'Q948', 'Tunisia'),
        ('SN', 'Q1041', 'Senegal'),
        ('CI', 'Q1008', 'Ivory Coast'),
        ('HT', 'Q790', 'Haiti'),

        # Former Spanish colonies
        ('ES', 'Q29', 'Spain'),
        ('MX', 'Q96', 'Mexico'),
        ('AR', 'Q414', 'Argentina'),
        ('CL', 'Q298', 'Chile'),
        ('PE', 'Q419', 'Peru'),
        ('CO', 'Q739', 'Colombia'),
        ('PH', 'Q928', 'Philippines'),

        # Former Portuguese colonies
        ('PT', 'Q45', 'Portugal'),
        ('BR', 'Q155', 'Brazil'),
        ('AO', 'Q916', 'Angola'),
        ('MZ', 'Q1029', 'Mozambique'),

        # Former Dutch colonies
        ('NL', 'Q55', 'Netherlands'),
        ('ID', 'Q252', 'Indonesia'),
        ('SR', 'Q730', 'Suriname'),

        # Other colonial powers
        ('IT', 'Q38', 'Italy'),
        ('DE', 'Q183', 'Germany'),
        ('BE', 'Q31', 'Belgium'),
        ('RU', 'Q159', 'Russia'),
        ('CN', 'Q148', 'China'),
        ('JP', 'Q17', 'Japan'),
    ]


def main():
    """Main execution."""
    print("="*60)
    print("Global Historical Wikidata Fetcher")
    print("="*60)

    fetcher = GlobalHistoricalWikidataFetcher(cache_dir='wikidata_global_cache')

    # Get priority countries
    countries = get_colonial_priority_countries()

    print(f"\nFetching data for {len(countries)} countries with colonial history")
    print("This will take ~3 hours (3 seconds per country x 50 countries)")
    print("\nCaching strategy: One file per country (resume-friendly)")

    # Fetch all priority countries
    fetcher.fetch_priority_countries(countries, batch_limit=10000)

    # Consolidate into single file
    fetcher.consolidate_caches('wikidata_global_historical.json')

    print("\n✓ Global historical Wikidata fetch complete!")
    print("\nNext steps:")
    print("  1. Run load_wikidata_from_cache.py to load into Neo4j")
    print("  2. Check for historical colonial entities (dissolvedDate IS NOT NULL)")


if __name__ == '__main__':
    main()
