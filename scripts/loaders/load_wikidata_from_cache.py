#!/usr/bin/env python3
"""
Load Wikidata enrichment from cached JSON file.

Reads the wikidata_canada_places.json cache and enriches Neo4j
with Wikipedia links, alternate names, and historical data.
"""

import os
import json
import gzip
from typing import Dict, List
from neo4j import GraphDatabase
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()


class WikidataCacheLoader:
    """Load Wikidata from cache into Neo4j."""

    def __init__(self, uri: str, user: str, password: str, cache_file: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.cache_file = cache_file

    def close(self):
        self.driver.close()

    def load_cache(self) -> List[Dict]:
        """Load places from cache file."""
        # Try compressed first
        if os.path.exists(self.cache_file + '.gz'):
            print(f"Loading from {self.cache_file}.gz...")
            with gzip.open(self.cache_file + '.gz', 'rt', encoding='utf-8') as f:
                cache_data = json.load(f)
        elif os.path.exists(self.cache_file):
            print(f"Loading from {self.cache_file}...")
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
        else:
            raise FileNotFoundError(f"Cache file not found: {self.cache_file}")

        print(f"✓ Loaded {cache_data['metadata']['total_records']:,} places from cache")
        print(f"  Fetch date: {cache_data['metadata']['fetch_date']}")

        return cache_data['places']

    def match_and_enrich_by_geonames_id(self, places: List[Dict]) -> int:
        """Match Wikidata to existing GeoNames places and enrich."""

        matched = 0
        batch = []
        batch_size = 500

        places_with_geonames = [p for p in places if p.get('geonamesId')]

        print(f"\nEnriching {len(places_with_geonames):,} places with GeoNames IDs...")

        for place in tqdm(places_with_geonames, desc="Matching by GeoNames ID"):
            try:
                geonames_id = int(place['geonamesId'])
            except (ValueError, TypeError):
                continue

            enrichment_data = {
                'geonameId': geonames_id,
                'wikidataId': place.get('qid'),
                'wikipediaUrl': place.get('wikipediaUrl'),
                'wikidataPopulation': place.get('population'),
                'inceptionDate': place.get('inceptionDate'),
                'dissolvedDate': place.get('dissolvedDate'),
                'abolishedDate': place.get('abolishedDate'),
                'wikidataLatitude': place.get('latitude'),
                'wikidataLongitude': place.get('longitude'),

                # NEW: Alternate names for NER matching
                'alternateNames': place.get('alternateNames', []),
                'officialNames': place.get('officialNames', []),
                'nativeLabel': place.get('nativeLabel'),
                'nickname': place.get('nickname'),

                # NEW: Historical succession
                'replacesQid': place.get('replacesQid'),
                'replacedByQid': place.get('replacedByQid'),
                'followsQid': place.get('followsQid'),
                'followedByQid': place.get('followedByQid'),

                # NEW: Colonial context
                'foundedByQid': place.get('foundedByQid'),
                'foundedByLabel': place.get('foundedByLabel'),
                'ownedByQid': place.get('ownedByQid'),
                'ownedByLabel': place.get('ownedByLabel'),
                'capitalOfQid': place.get('capitalOfQid'),
                'capitalOfLabel': place.get('capitalOfLabel'),

                # NEW: Cross-database IDs
                'gndId': place.get('gndId'),
                'viafId': place.get('viafId'),
                'locId': place.get('locId'),
                'tgnId': place.get('tgnId'),
                'osmId': place.get('osmId'),
                'wofId': place.get('wofId'),

                # NEW: Historic context
                'historicCountyQid': place.get('historicCountyQid'),
                'historicCountyLabel': place.get('historicCountyLabel'),
                'officialWebsite': place.get('officialWebsite'),
                'instanceOfQid': place.get('instanceOfQid'),
                'instanceOfLabel': place.get('instanceOfLabel'),
            }

            batch.append(enrichment_data)

            if len(batch) >= batch_size:
                matched += self._update_batch(batch)
                batch = []

        # Update remaining
        if batch:
            matched += self._update_batch(batch)

        return matched

    def _update_batch(self, batch: List[Dict]) -> int:
        """Update a batch of places."""
        with self.driver.session() as session:
            result = session.run("""
                UNWIND $batch AS item
                MATCH (p:Place {geonameId: item.geonameId})
                SET p.wikidataId = item.wikidataId,
                    p.wikipediaUrl = item.wikipediaUrl,
                    p.wikidataPopulation = item.wikidataPopulation,
                    p.inceptionDate = item.inceptionDate,
                    p.dissolvedDate = item.dissolvedDate,
                    p.abolishedDate = item.abolishedDate,
                    p.wikidataLatitude = item.wikidataLatitude,
                    p.wikidataLongitude = item.wikidataLongitude,

                    // Alternate names for NER matching
                    p.alternateNames = item.alternateNames,
                    p.officialNames = item.officialNames,
                    p.nativeLabel = item.nativeLabel,
                    p.nickname = item.nickname,

                    // Historical succession
                    p.replacesQid = item.replacesQid,
                    p.replacedByQid = item.replacedByQid,
                    p.followsQid = item.followsQid,
                    p.followedByQid = item.followedByQid,

                    // Colonial context
                    p.foundedByQid = item.foundedByQid,
                    p.foundedByLabel = item.foundedByLabel,
                    p.ownedByQid = item.ownedByQid,
                    p.ownedByLabel = item.ownedByLabel,
                    p.capitalOfQid = item.capitalOfQid,
                    p.capitalOfLabel = item.capitalOfLabel,

                    // Cross-database IDs
                    p.gndId = item.gndId,
                    p.viafId = item.viafId,
                    p.locId = item.locId,
                    p.tgnId = item.tgnId,
                    p.osmId = item.osmId,
                    p.wofId = item.wofId,

                    // Historic context
                    p.historicCountyQid = item.historicCountyQid,
                    p.historicCountyLabel = item.historicCountyLabel,
                    p.officialWebsite = item.officialWebsite,
                    p.instanceOfQid = item.instanceOfQid,
                    p.instanceOfLabel = item.instanceOfLabel

                RETURN count(p) AS updated
            """, batch=batch)

            return result.single()['updated']

    def create_wikidata_only_places(self, places: List[Dict]) -> int:
        """Create Place nodes for Wikidata entries not in GeoNames."""

        # Filter to places without GeoNames ID but with coordinates
        wikidata_only = [
            p for p in places
            if not p.get('geonamesId')
            and p.get('latitude')
            and p.get('longitude')
            and p.get('name')
        ]

        print(f"\nCreating {len(wikidata_only):,} Wikidata-only places...")

        created = 0
        batch = []
        batch_size = 500

        for place in tqdm(wikidata_only, desc="Creating Wikidata-only places"):
            place_data = {
                'wikidataId': place['qid'],
                'name': place['name'],
                'latitude': place['latitude'],
                'longitude': place['longitude'],
                'countryCode': place.get('countryQid', 'CA'),  # Use actual country if available
                'wikipediaUrl': place.get('wikipediaUrl'),
                'wikidataPopulation': place.get('population'),
                'inceptionDate': place.get('inceptionDate'),
                'dissolvedDate': place.get('dissolvedDate'),
                'abolishedDate': place.get('abolishedDate'),
                'source': 'wikidata',

                # Alternate names
                'alternateNames': place.get('alternateNames', []),
                'officialNames': place.get('officialNames', []),
                'nativeLabel': place.get('nativeLabel'),
                'nickname': place.get('nickname'),

                # Historical succession
                'replacesQid': place.get('replacesQid'),
                'replacedByQid': place.get('replacedByQid'),
                'followsQid': place.get('followsQid'),
                'followedByQid': place.get('followedByQid'),

                # Colonial context
                'foundedByQid': place.get('foundedByQid'),
                'foundedByLabel': place.get('foundedByLabel'),
                'ownedByQid': place.get('ownedByQid'),
                'ownedByLabel': place.get('ownedByLabel'),
                'capitalOfQid': place.get('capitalOfQid'),
                'capitalOfLabel': place.get('capitalOfLabel'),

                # Cross-database IDs
                'gndId': place.get('gndId'),
                'viafId': place.get('viafId'),
                'locId': place.get('locId'),
                'tgnId': place.get('tgnId'),
                'osmId': place.get('osmId'),
                'wofId': place.get('wofId'),

                # Historic context
                'historicCountyQid': place.get('historicCountyQid'),
                'historicCountyLabel': place.get('historicCountyLabel'),
                'officialWebsite': place.get('officialWebsite'),
                'instanceOfQid': place.get('instanceOfQid'),
                'instanceOfLabel': place.get('instanceOfLabel'),
            }

            batch.append(place_data)

            if len(batch) >= batch_size:
                created += self._create_batch(batch)
                batch = []

        # Create remaining
        if batch:
            created += self._create_batch(batch)

        return created

    def _create_batch(self, batch: List[Dict]) -> int:
        """Create a batch of new places."""
        with self.driver.session() as session:
            result = session.run("""
                UNWIND $batch AS item
                MERGE (p:Place {wikidataId: item.wikidataId})
                ON CREATE SET
                    p.name = item.name,
                    p.latitude = item.latitude,
                    p.longitude = item.longitude,
                    p.countryCode = item.countryCode,
                    p.source = item.source,
                    p.featureClass = 'P',
                    p.featureCode = 'PPL'
                SET p.wikipediaUrl = item.wikipediaUrl,
                    p.wikidataPopulation = item.wikidataPopulation,
                    p.inceptionDate = item.inceptionDate,
                    p.dissolvedDate = item.dissolvedDate,
                    p.abolishedDate = item.abolishedDate,

                    // Alternate names
                    p.alternateNames = item.alternateNames,
                    p.officialNames = item.officialNames,
                    p.nativeLabel = item.nativeLabel,
                    p.nickname = item.nickname,

                    // Historical succession
                    p.replacesQid = item.replacesQid,
                    p.replacedByQid = item.replacedByQid,
                    p.followsQid = item.followsQid,
                    p.followedByQid = item.followedByQid,

                    // Colonial context
                    p.foundedByQid = item.foundedByQid,
                    p.foundedByLabel = item.foundedByLabel,
                    p.ownedByQid = item.ownedByQid,
                    p.ownedByLabel = item.ownedByLabel,
                    p.capitalOfQid = item.capitalOfQid,
                    p.capitalOfLabel = item.capitalOfLabel,

                    // Cross-database IDs
                    p.gndId = item.gndId,
                    p.viafId = item.viafId,
                    p.locId = item.locId,
                    p.tgnId = item.tgnId,
                    p.osmId = item.osmId,
                    p.wofId = item.wofId,

                    // Historic context
                    p.historicCountyQid = item.historicCountyQid,
                    p.historicCountyLabel = item.historicCountyLabel,
                    p.officialWebsite = item.officialWebsite,
                    p.instanceOfQid = item.instanceOfQid,
                    p.instanceOfLabel = item.instanceOfLabel

                MERGE (c:Country {code: item.countryCode})
                MERGE (p)-[:LOCATED_IN_COUNTRY]->(c)

                RETURN count(p) AS created
            """, batch=batch)

            return result.single()['created']

    def print_statistics(self):
        """Print enrichment statistics."""
        print("\n" + "="*60)
        print("WIKIDATA ENRICHMENT STATISTICS")
        print("="*60)

        with self.driver.session() as session:
            # Total Canadian places
            result = session.run("""
                MATCH (p:Place)
                WHERE p.countryCode = 'CA'
                RETURN count(p) AS total
            """)
            total = result.single()['total']

            # Places with Wikidata
            result = session.run("""
                MATCH (p:Place)
                WHERE p.countryCode = 'CA' AND p.wikidataId IS NOT NULL
                RETURN count(p) AS count
            """)
            with_wikidata = result.single()['count']

            # Places with Wikipedia
            result = session.run("""
                MATCH (p:Place)
                WHERE p.countryCode = 'CA' AND p.wikipediaUrl IS NOT NULL
                RETURN count(p) AS count
            """)
            with_wikipedia = result.single()['count']

            # Historical places
            result = session.run("""
                MATCH (p:Place)
                WHERE p.countryCode = 'CA' AND p.dissolvedDate IS NOT NULL
                RETURN count(p) AS count
            """)
            historical = result.single()['count']

            # Wikidata-only places
            result = session.run("""
                MATCH (p:Place)
                WHERE p.countryCode = 'CA' AND p.source = 'wikidata'
                RETURN count(p) AS count
            """)
            wikidata_only = result.single()['count']

            print(f"\nTotal Canadian Places: {total:,}")
            print(f"  With Wikidata: {with_wikidata:,} ({(with_wikidata/total)*100:.1f}%)")
            print(f"  With Wikipedia: {with_wikipedia:,} ({(with_wikipedia/total)*100:.1f}%)")
            print(f"  Historical (dissolved): {historical:,}")
            print(f"  Wikidata-only (not in GeoNames): {wikidata_only:,}")

        print("="*60)


def main():
    """Main execution."""
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

    CACHE_FILE = '/home/jic823/CanadaNeo4j/wikidata_canada_with_admin.json'

    print("="*60)
    print("Wikidata Enrichment from Cache")
    print("="*60)

    loader = WikidataCacheLoader(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, CACHE_FILE)

    try:
        # Load cache
        places = loader.load_cache()

        # Enrich existing GeoNames places
        matched = loader.match_and_enrich_by_geonames_id(places)
        print(f"\n✓ Enriched {matched:,} existing GeoNames places")

        # Create new places for Wikidata-only entries
        created = loader.create_wikidata_only_places(places)
        print(f"✓ Created {created:,} new Wikidata-only places")

        # Print statistics
        loader.print_statistics()

        print("\n✓ Wikidata enrichment complete!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise

    finally:
        loader.close()


if __name__ == '__main__':
    main()
