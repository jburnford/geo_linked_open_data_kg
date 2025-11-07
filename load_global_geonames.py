#!/usr/bin/env python3
"""
Global GeoNames Data Loader for Neo4j LOD Knowledge Graph

Loads allCountries.txt dataset into Neo4j with intelligent deduplication:
- SKIPS records already in database (cities500.txt, CA.txt)
- Adds NEW country-specific features (rivers, mountains, regions, etc.)
- Efficient batch processing with progress tracking
- Country-by-country filtering for incremental expansion

Current Database State:
  - cities500.txt: 225K global cities (pop ≥500) ✓ LOADED
  - CA.txt: 316K Canadian features ✓ LOADED
  - Wikidata CA: 27K Canadian places ✓ LOADED
  Total: 556,626 unique places

Strategy:
  1. Load allCountries.txt country-by-country (NOT cities500 which is already loaded)
  2. Neo4j MERGE ensures deduplication by geonameId
  3. Focus on adding geographic features (not duplicate cities)

Usage:
  # Load specific countries incrementally
  python3 load_global_geonames.py --countries US,GB,FR,DE

  # Load all countries except Canada (already loaded via CA.txt)
  python3 load_global_geonames.py --exclude-countries CA

  # Resume from offset (if interrupted)
  python3 load_global_geonames.py --offset 5000000
"""

import os
import csv
import argparse
from typing import Dict, List, Optional, Set
from neo4j import GraphDatabase
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

# GeoNames field mapping (tab-delimited)
GEONAMES_FIELDS = [
    'geonameid', 'name', 'asciiname', 'alternatenames',
    'latitude', 'longitude', 'feature_class', 'feature_code',
    'country_code', 'cc2', 'admin1_code', 'admin2_code',
    'admin3_code', 'admin4_code', 'population', 'elevation',
    'dem', 'timezone', 'modification_date'
]


class GlobalGeoNamesLoader:
    """Load global GeoNames data into Neo4j efficiently."""

    def __init__(self, uri: str, user: str, password: str, batch_size: int = 10000):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.batch_size = batch_size

    def close(self):
        self.driver.close()

    def parse_geonames_row(self, row: Dict, include_codes: Optional[Set[str]] = None) -> Optional[Dict]:
        """Parse a GeoNames row into Neo4j-friendly format."""
        try:
            # Parse alternate names into list
            alt_names = []
            if row.get('alternatenames'):
                alt_names = [n.strip() for n in row['alternatenames'].split(',') if n.strip()]

            # Convert numeric fields
            try:
                population = int(row.get('population', 0) or 0)
            except ValueError:
                population = 0

            try:
                elevation = int(row.get('elevation', 0) or 0)
            except ValueError:
                elevation = 0

            try:
                latitude = float(row['latitude'])
                longitude = float(row['longitude'])
            except (ValueError, KeyError):
                latitude = None
                longitude = None

            # Skip records without coordinates (useless for NER reconciliation)
            if latitude is None or longitude is None:
                return None

            feature_class = row['feature_class']
            feature_code = row['feature_code']
            full_code = f"{feature_class}.{feature_code}"

            return {
                'geonameId': int(row['geonameid']),
                'name': row['name'],
                'asciiName': row['asciiname'],
                'alternateNames': alt_names,
                'latitude': latitude,
                'longitude': longitude,
                'featureClass': feature_class,
                'featureCode': feature_code,
                'fullFeatureCode': full_code,
                'countryCode': row['country_code'],
                'admin1Code': row.get('admin1_code', ''),
                'admin2Code': row.get('admin2_code', ''),
                'admin3Code': row.get('admin3_code', ''),
                'admin4Code': row.get('admin4_code', ''),
                'population': population,
                'elevation': elevation,
                'timezone': row.get('timezone', ''),
                'modifiedDate': row.get('modification_date', ''),
            }
        except Exception as e:
            print(f"Error parsing geonameId {row.get('geonameid')}: {e}")
            return None

    def load_places_batch(self, places: List[Dict]):
        """Load a batch of places into Neo4j using MERGE (deduplication)."""
        with self.driver.session() as session:
            session.run("""
                UNWIND $places AS place
                MERGE (p:Place {geonameId: place.geonameId})
                SET p.name = place.name,
                    p.asciiName = place.asciiName,
                    p.alternateNames = place.alternateNames,
                    p.latitude = place.latitude,
                    p.longitude = place.longitude,
                    p.location = point({latitude: place.latitude, longitude: place.longitude}),
                    p.featureClass = place.featureClass,
                    p.featureCode = place.featureCode,
                    p.countryCode = place.countryCode,
                    p.admin1Code = place.admin1Code,
                    p.admin2Code = place.admin2Code,
                    p.admin3Code = place.admin3Code,
                    p.admin4Code = place.admin4Code,
                    p.population = place.population,
                    p.elevation = place.elevation,
                    p.timezone = place.timezone,
                    p.modifiedDate = place.modifiedDate

                // Create or link to country
                MERGE (c:Country {code: place.countryCode})
                MERGE (p)-[:LOCATED_IN_COUNTRY]->(c)
            """, places=places)

    def load_allcountries_file(
        self,
        filepath: str,
        country_filter: Optional[Set[str]] = None,
        exclude_countries: Optional[Set[str]] = None,
        include_codes: Optional[Set[str]] = None,
        offset: int = 0,
        dry_run: bool = False
    ) -> int:
        """
        Load allCountries.txt into Neo4j with optional filtering.

        Args:
            filepath: Path to allCountries.txt
            country_filter: Set of country codes to INCLUDE (e.g., {'US', 'GB'})
            exclude_countries: Set of country codes to EXCLUDE (e.g., {'CA'})
            include_codes: Set of feature codes to INCLUDE (e.g., {'P', 'A', 'S.CMTY', 'S.PO'})
                          Supports both class-level (P) and specific codes (S.CMTY)
            offset: Skip first N records (for resuming interrupted loads)
            dry_run: Count records without loading

        Returns:
            Number of places loaded (or would be loaded in dry-run mode)
        """
        mode = "DRY RUN - Counting" if dry_run else "Loading"
        print(f"\n{mode} global GeoNames data from {filepath}")
        if country_filter:
            print(f"Including countries: {', '.join(sorted(country_filter))}")
        if exclude_countries:
            print(f"Excluding countries: {', '.join(sorted(exclude_countries))}")
        if include_codes:
            print(f"Including feature codes: {', '.join(sorted(include_codes))}")
        if offset > 0:
            print(f"Resuming from offset: {offset:,}")

        # Parse include_codes into classes and specific codes
        include_classes = set()
        include_specific = set()
        if include_codes:
            for code in include_codes:
                if '.' in code:
                    # Specific code like "S.CMTY"
                    include_specific.add(code)
                else:
                    # Class-level like "P"
                    include_classes.add(code)

        # Count total lines for progress bar
        print("Counting records...")
        with open(filepath, 'r', encoding='utf-8') as f:
            total_lines = sum(1 for _ in f)

        print(f"Total records in file: {total_lines:,}")

        batch = []
        loaded_count = 0
        skipped_count = 0
        current_line = 0

        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, fieldnames=GEONAMES_FIELDS, delimiter='\t')

            with tqdm(total=total_lines, desc="Loading places", unit=" records") as pbar:
                for row in reader:
                    current_line += 1

                    # Skip to offset
                    if current_line <= offset:
                        pbar.update(1)
                        continue

                    country_code = row.get('country_code', '')

                    # Apply exclusion filter
                    if exclude_countries and country_code in exclude_countries:
                        skipped_count += 1
                        pbar.update(1)
                        continue

                    # Apply inclusion filter if specified
                    if country_filter and country_code not in country_filter:
                        skipped_count += 1
                        pbar.update(1)
                        continue

                    # Parse row
                    place = self.parse_geonames_row(row, include_codes=include_codes)
                    if place is None:
                        skipped_count += 1
                        pbar.update(1)
                        continue

                    # Apply feature code filtering
                    if include_codes:
                        feature_class = place['featureClass']
                        full_code = place['fullFeatureCode']

                        # Check if either class or specific code matches
                        if feature_class not in include_classes and full_code not in include_specific:
                            skipped_count += 1
                            pbar.update(1)
                            continue

                    batch.append(place)

                    # Load batch when full (skip in dry-run mode)
                    if len(batch) >= self.batch_size:
                        if not dry_run:
                            self.load_places_batch(batch)
                        loaded_count += len(batch)
                        pbar.set_postfix({
                            'would_load' if dry_run else 'loaded': f"{loaded_count:,}",
                            'skipped': f"{skipped_count:,}"
                        })
                        batch = []

                    pbar.update(1)

                # Load remaining batch (skip in dry-run mode)
                if batch:
                    if not dry_run:
                        self.load_places_batch(batch)
                    loaded_count += len(batch)

        if dry_run:
            print(f"\n✓ Would load {loaded_count:,} places (dry-run)")
        else:
            print(f"\n✓ Loaded {loaded_count:,} places")
        print(f"  Skipped {skipped_count:,} records (no coords or filtered)")
        return loaded_count

    def print_country_statistics(self):
        """Print statistics by country."""
        print("\n" + "="*60)
        print("GLOBAL DATABASE STATISTICS")
        print("="*60)

        with self.driver.session() as session:
            # Total places
            result = session.run("MATCH (p:Place) RETURN count(p) AS count")
            total_places = result.single()['count']
            print(f"\nTotal Places: {total_places:,}")

            # Places by country (all countries)
            result = session.run("""
                MATCH (p:Place)
                RETURN p.countryCode AS country, count(p) AS count
                ORDER BY count DESC
            """)

            print("\nPlaces by Country:")
            countries = list(result)
            for i, record in enumerate(countries, 1):
                print(f"  {i:3d}. {record['country']}: {record['count']:>10,}")

            # Countries with data
            print(f"\nTotal Countries: {len(countries)}")

            # Feature class distribution
            result = session.run("""
                MATCH (p:Place)
                RETURN p.featureClass AS class, count(p) AS count
                ORDER BY count DESC
            """)
            print("\nPlaces by Feature Class:")
            for record in result:
                print(f"  {record['class']}: {record['count']:,}")

            # Places with location points (spatial index ready)
            result = session.run("""
                MATCH (p:Place)
                WHERE p.location IS NOT NULL
                RETURN count(p) AS count
            """)
            with_location = result.single()['count']
            print(f"\nPlaces with spatial index: {with_location:,} ({with_location/total_places*100:.1f}%)")

        print("="*60)


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Load global GeoNames data into Neo4j",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Load US with settlements + admin + communities + post offices only
  python3 load_global_geonames.py --countries US --include-codes P,A,S.CMTY,S.PO

  # Load UK with settlements and admin only
  python3 load_global_geonames.py --countries GB --include-codes P,A

  # Dry-run to see counts before loading
  python3 load_global_geonames.py --countries US --include-codes P,A,S.CMTY,S.PO --dry-run

  # Resume from line 5 million (if interrupted)
  python3 load_global_geonames.py --offset 5000000

  # Load with smaller batches (lower memory)
  python3 load_global_geonames.py --batch-size 5000
        """
    )

    parser.add_argument(
        '--countries',
        type=str,
        help='Comma-separated list of country codes to INCLUDE (e.g., US,GB,FR,DE)'
    )
    parser.add_argument(
        '--exclude-countries',
        type=str,
        default='CA',
        help='Comma-separated list of country codes to EXCLUDE (default: CA, already loaded)'
    )
    parser.add_argument(
        '--include-codes',
        type=str,
        help='Comma-separated feature codes to INCLUDE (e.g., P,A,S.CMTY,S.PO). '
             'Use class (P) for all in class, or specific codes (S.CMTY) for individual types'
    )
    parser.add_argument(
        '--offset',
        type=int,
        default=0,
        help='Skip first N records (for resuming interrupted loads)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10000,
        help='Batch size for Neo4j transactions (default: 10000)'
    )
    parser.add_argument(
        '--file',
        type=str,
        default='allCountries.txt',
        help='Path to allCountries.txt (default: ./allCountries.txt)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Count records that would be loaded without actually loading'
    )

    args = parser.parse_args()

    # Configuration
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

    DATA_DIR = os.path.dirname(os.path.abspath(__file__))
    ALLCOUNTRIES_FILE = os.path.join(DATA_DIR, args.file)

    # Parse country filters
    country_filter = None
    if args.countries:
        country_filter = set(args.countries.upper().split(','))

    exclude_countries = None
    if args.exclude_countries:
        exclude_countries = set(args.exclude_countries.upper().split(','))

    include_codes = None
    if args.include_codes:
        include_codes = set(args.include_codes.upper().split(','))

    print("="*60)
    print("Global GeoNames LOD Knowledge Graph Loader")
    print("="*60)
    print(f"\nConfiguration:")
    print(f"  Neo4j URI: {NEO4J_URI}")
    print(f"  Batch size: {args.batch_size:,}")
    print(f"  Data file: {ALLCOUNTRIES_FILE}")

    # Check file exists
    if not os.path.exists(ALLCOUNTRIES_FILE):
        print(f"\n✗ Error: File not found: {ALLCOUNTRIES_FILE}")
        print("\nDownload from: https://download.geonames.org/export/dump/allCountries.zip")
        return

    # Initialize loader
    loader = GlobalGeoNamesLoader(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, args.batch_size)

    try:
        # Load data
        loaded_count = loader.load_allcountries_file(
            ALLCOUNTRIES_FILE,
            country_filter=country_filter,
            exclude_countries=exclude_countries,
            include_codes=include_codes,
            offset=args.offset,
            dry_run=args.dry_run
        )

        # Print statistics (skip in dry-run mode)
        if not args.dry_run:
            loader.print_country_statistics()

        if args.dry_run:
            print("\n✓ Dry-run complete!")
            print(f"\nWould add {loaded_count:,} new places to database")
            print("\nTo actually load, run without --dry-run flag")
        else:
            print("\n✓ Global GeoNames data loaded successfully!")
            print("\nNext steps:")
            print("  1. Run link_by_geography.py to create spatial relationships")
            print("  2. Test NER reconciliation queries")
            print("  3. Monitor query performance with spatial indexes")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise

    finally:
        loader.close()


if __name__ == '__main__':
    main()
