#!/usr/bin/env python3
"""
Load Canadian Post Office data into Neo4j.

CONSERVATIVE MATCHING STRATEGY:
- Without coordinates, we must be very careful about name matching
- Only match when name + province combination is unique
- Flag ambiguous matches for manual review
- Keep post office data separate from Place nodes to avoid corruption

Data Structure:
- Create PostOffice nodes separate from Place nodes
- Link PostOffice -> Place only when match is confident
- Preserve all post office data even without matches
"""

import os
import pandas as pd
from typing import Dict, List, Optional, Tuple
from neo4j import GraphDatabase
from tqdm import tqdm
from dotenv import load_dotenv
import re

load_dotenv()


class PostOfficeLoader:
    """Load post office data with conservative matching."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def load_post_office_csv(self, filepath: str) -> pd.DataFrame:
        """Load CSV with proper encoding for French accents."""
        print(f"Loading post office data from {filepath}...")

        # Read with UTF-8 encoding
        df = pd.read_csv(filepath, encoding='utf-8')

        # Clean up dates (handle parsing errors)
        df['EstablishedDate'] = pd.to_datetime(
            df['EstablishedDate'],
            errors='coerce',
            format='mixed'
        )
        df['ClosingDate'] = pd.to_datetime(
            df['ClosingDate'],
            errors='coerce',
            format='mixed'
        )

        # Extract just the year for easier querying
        df['EstablishedYear'] = df['EstablishedDate'].dt.year
        df['ClosingYear'] = df['ClosingDate'].dt.year

        print(f"✓ Loaded {len(df):,} post offices")
        print(f"  With established dates: {df['EstablishedDate'].notna().sum():,}")
        print(f"  With closing dates: {df['ClosingDate'].notna().sum():,}")

        return df

    def normalize_name(self, name: str) -> str:
        """Normalize place name for matching (case-insensitive, no punctuation)."""
        if not name:
            return ""
        # Convert to lowercase, remove extra spaces
        normalized = name.lower().strip()
        # Remove common suffixes/prefixes that might differ
        normalized = re.sub(r'\s+(post office|p\.?o\.?|m\.?p\.?o\.?).*$', '', normalized)
        return normalized

    def check_name_ambiguity(self, df: pd.DataFrame) -> Dict[str, List[int]]:
        """
        Check for ambiguous name + province combinations.

        Returns dict of name+province -> list of IDs where there are duplicates.
        """
        df['normalized_key'] = df.apply(
            lambda row: f"{self.normalize_name(row['Name'])}|{row['Province']}",
            axis=1
        )

        # Find duplicates
        ambiguous = {}
        for key, group in df.groupby('normalized_key'):
            if len(group) > 1:
                ambiguous[key] = group['IdNumber'].tolist()

        print(f"\nAmbiguous name+province combinations: {len(ambiguous):,}")
        if ambiguous:
            print("Sample ambiguous entries:")
            for key, ids in list(ambiguous.items())[:5]:
                name, prov = key.split('|')
                print(f"  '{name}' in {prov}: {len(ids)} entries (IDs: {ids})")

        return ambiguous

    def create_post_office_nodes(self, df: pd.DataFrame, batch_size: int = 1000):
        """
        Create PostOffice nodes in Neo4j.

        Keep separate from Place nodes to avoid corruption.
        """
        print("\nCreating PostOffice nodes...")

        # Create constraint
        with self.driver.session() as session:
            session.run("""
                CREATE CONSTRAINT postoffice_id IF NOT EXISTS
                FOR (po:PostOffice) REQUIRE po.idNumber IS UNIQUE
            """)

        records = []
        for _, row in df.iterrows():
            record = {
                'idNumber': int(row['IdNumber']),
                'name': row['Name'],
                'province': row['Province'],
                'establishedDate': row['EstablishedDate'].isoformat() if pd.notna(row['EstablishedDate']) else None,
                'closingDate': row['ClosingDate'].isoformat() if pd.notna(row['ClosingDate']) else None,
                'establishedYear': int(row['EstablishedYear']) if pd.notna(row['EstablishedYear']) else None,
                'closingYear': int(row['ClosingYear']) if pd.notna(row['ClosingYear']) else None,
                'isOpen': pd.isna(row['ClosingDate']),
                'normalizedName': self.normalize_name(row['Name'])
            }
            records.append(record)

            if len(records) >= batch_size:
                self._create_batch(records)
                records = []

        # Create remaining
        if records:
            self._create_batch(records)

        print(f"✓ Created {len(df):,} PostOffice nodes")

    def _create_batch(self, records: List[Dict]):
        """Create a batch of PostOffice nodes."""
        with self.driver.session() as session:
            session.run("""
                UNWIND $records AS po
                MERGE (p:PostOffice {idNumber: po.idNumber})
                SET p.name = po.name,
                    p.province = po.province,
                    p.establishedDate = po.establishedDate,
                    p.closingDate = po.closingDate,
                    p.establishedYear = po.establishedYear,
                    p.closingYear = po.closingYear,
                    p.isOpen = po.isOpen,
                    p.normalizedName = po.normalizedName
            """, records=records)

    def match_to_places_conservative(self, ambiguous_names: Dict[str, List[int]]):
        """
        Match PostOffices to Places ONLY when confident.

        Conservative rules:
        1. Name must normalize to same value
        2. Province must match (using province code mapping)
        3. Name+Province combination must be unique (not in ambiguous list)
        4. Create POSSIBLE_MATCH relationship with confidence score
        """
        print("\nMatching post offices to places (conservative)...")

        # Province name to code mapping
        province_map = {
            'Ontario': ['ON', '08'],
            'Quebec': ['QC', 'PQ', '10'],
            'Nova Scotia': ['NS', '07'],
            'New Brunswick': ['NB', '04'],
            'Manitoba': ['MB', '03'],
            'British Columbia': ['BC', '02'],
            'Prince Edward Island': ['PE', 'PEI', '09'],
            'Saskatchewan': ['SK', '11'],
            'Alberta': ['AB', '01'],
            'Newfoundland': ['NL', 'NF', '05'],
            'Yukon': ['YT', '14'],
            'Northwest Territories': ['NT', '13'],
            'Nunavut': ['NU', '12']
        }

        with self.driver.session() as session:
            # Get all post offices
            result = session.run("""
                MATCH (po:PostOffice)
                RETURN po.idNumber AS id,
                       po.name AS name,
                       po.province AS province,
                       po.normalizedName AS normalized
            """)

            post_offices = [dict(record) for record in result]

        matched = 0
        ambiguous = 0
        unmatched = 0

        for po in tqdm(post_offices, desc="Matching"):
            # Skip if ambiguous
            key = f"{po['normalized']}|{po['province']}"
            if key in ambiguous_names:
                ambiguous += 1
                continue

            # Get province codes
            prov_codes = province_map.get(po['province'], [])
            if not prov_codes:
                continue

            # Try to match
            with self.driver.session() as session:
                # Try exact name match first
                result = session.run("""
                    MATCH (p:Place)
                    WHERE toLower(p.name) = $normalized
                      AND p.countryCode = 'CA'
                      AND (p.admin1Code IN $provCodes OR $province IN [p.admin1Code])
                    RETURN p.geonameId AS geonameId,
                           p.name AS name,
                           p.latitude AS lat,
                           p.longitude AS lon
                    LIMIT 5
                """,
                    normalized=po['normalized'],
                    provCodes=prov_codes,
                    province=po['province']
                )

                matches = list(result)

                if len(matches) == 1:
                    # Unique match - create relationship with high confidence
                    match = matches[0]
                    session.run("""
                        MATCH (po:PostOffice {idNumber: $poId})
                        MATCH (p:Place {geonameId: $geonameId})
                        MERGE (po)-[r:POSSIBLY_LOCATED_AT]->(p)
                        SET r.confidence = 0.9,
                            r.matchMethod = 'exact_name_province',
                            r.matchedDate = datetime()
                    """,
                        poId=po['id'],
                        geonameId=match['geonameId']
                    )
                    matched += 1

                elif len(matches) > 1:
                    # Multiple matches - flag as ambiguous
                    ambiguous += 1

                else:
                    unmatched += 1

        print(f"\n✓ Matching complete:")
        print(f"  Confidently matched: {matched:,}")
        print(f"  Ambiguous (not matched): {ambiguous:,}")
        print(f"  Unmatched: {unmatched:,}")
        print(f"  Total: {len(post_offices):,}")

    def print_statistics(self):
        """Print post office statistics."""
        print("\n" + "="*60)
        print("POST OFFICE STATISTICS")
        print("="*60)

        with self.driver.session() as session:
            # Total post offices
            result = session.run("MATCH (po:PostOffice) RETURN count(po) AS count")
            total = result.single()['count']

            # By province
            result = session.run("""
                MATCH (po:PostOffice)
                RETURN po.province AS province, count(po) AS count
                ORDER BY count DESC
                LIMIT 10
            """)
            print(f"\nTotal Post Offices: {total:,}")
            print("\nTop 10 Provinces:")
            for record in result:
                print(f"  {record['province']}: {record['count']:,}")

            # Still open vs closed
            result = session.run("""
                MATCH (po:PostOffice)
                RETURN po.isOpen AS isOpen, count(po) AS count
            """)
            print("\nStatus:")
            for record in result:
                status = "Open" if record['isOpen'] else "Closed"
                print(f"  {status}: {record['count']:,}")

            # Matched to places
            result = session.run("""
                MATCH (po:PostOffice)-[:POSSIBLY_LOCATED_AT]->(p:Place)
                RETURN count(DISTINCT po) AS matched
            """)
            matched = result.single()['matched']
            print(f"\nMatched to Places: {matched:,} ({(matched/total)*100:.1f}%)")

        print("="*60)


def main():
    """Main execution."""
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

    CSV_FILE = '/home/jic823/CanadaNeo4j/post-office-data-with-founding-date).csv'

    print("="*60)
    print("Canadian Post Office Data Loader")
    print("="*60)

    loader = PostOfficeLoader(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # Load CSV
        df = loader.load_post_office_csv(CSV_FILE)

        # Check for ambiguous names
        ambiguous = loader.check_name_ambiguity(df)

        # Create PostOffice nodes
        loader.create_post_office_nodes(df)

        # Match to existing places (conservative)
        loader.match_to_places_conservative(ambiguous)

        # Print statistics
        loader.print_statistics()

        print("\n✓ Post office data loaded successfully!")
        print("\nNOTE: Only confident matches were linked.")
        print("Ambiguous cases preserved as separate PostOffice nodes.")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise

    finally:
        loader.close()


if __name__ == '__main__':
    main()
