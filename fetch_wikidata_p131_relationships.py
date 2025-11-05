#!/usr/bin/env python3
"""
Fetch Wikidata P131 (located in administrative territory) relationships.

This adds administrative containment data to complement our geographic linking.
For example:
- St. Mary's Church (Q123) P131 Montreal (Q456)
- High Park (Q789) P131 Toronto (Q62)

We'll fetch P131 relationships for all Canadian places in our existing cache
and store them as ADMINISTRATIVELY_LOCATED_IN relationships in Neo4j.

This is separate from our coordinate-based LOCATED_IN inference.
"""

import os
import json
from typing import List, Dict, Set, Optional
from SPARQLWrapper import SPARQLWrapper, JSON
from neo4j import GraphDatabase
from tqdm import tqdm
from dotenv import load_dotenv
import time

load_dotenv()


class WikidataP131Fetcher:
    """Fetch P131 (located in) relationships from Wikidata."""

    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
        self.sparql.setReturnFormat(JSON)
        self.sparql.addCustomHttpHeader('User-Agent', 'CanadianLODProject/1.0')

    def close(self):
        self.driver.close()

    def get_all_wikidata_ids(self) -> List[str]:
        """Get all Wikidata IDs from Neo4j."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Place)
                WHERE p.wikidataId IS NOT NULL
                RETURN DISTINCT p.wikidataId AS wikidataId
                ORDER BY p.wikidataId
            """)
            wikidata_ids = [record['wikidataId'] for record in result]

        print(f"Found {len(wikidata_ids):,} places with Wikidata IDs")
        return wikidata_ids

    def fetch_p131_batch(self, qids: List[str]) -> Dict[str, List[str]]:
        """
        Fetch P131 relationships for a batch of QIDs.

        Returns dict: {child_qid: [parent_qid1, parent_qid2, ...]}

        Note: Some places have multiple P131 values (e.g., overlapping jurisdictions).
        """
        # Convert list to VALUES clause
        qid_values = ' '.join([f'wd:{qid}' for qid in qids])

        query = f"""
        SELECT ?place ?locatedIn
        WHERE {{
          VALUES ?place {{ {qid_values} }}
          ?place wdt:P131 ?locatedIn .

          # Optional: only get Canadian places as parents
          # (removes some noise from cross-border relationships)
          OPTIONAL {{ ?locatedIn wdt:P17 ?country . }}
          FILTER(!BOUND(?country) || ?country = wd:Q16)  # Canada or unspecified
        }}
        """

        self.sparql.setQuery(query)

        try:
            results = self.sparql.query().convert()
            bindings = results.get('results', {}).get('bindings', [])

            # Build dict
            p131_map = {}
            for b in bindings:
                child = b['place']['value'].split('/')[-1]  # Extract Q123 from URI
                parent = b['locatedIn']['value'].split('/')[-1]

                if child not in p131_map:
                    p131_map[child] = []
                p131_map[child].append(parent)

            return p131_map

        except Exception as e:
            print(f"  Error querying batch: {e}")
            return {}

    def fetch_all_p131(self, wikidata_ids: List[str], batch_size: int = 100) -> Dict[str, List[str]]:
        """Fetch all P131 relationships in batches."""
        print(f"\nFetching P131 relationships in batches of {batch_size}...")

        all_p131 = {}
        total_relationships = 0

        for i in tqdm(range(0, len(wikidata_ids), batch_size), desc="Fetching P131"):
            batch = wikidata_ids[i:i+batch_size]
            p131_batch = self.fetch_p131_batch(batch)

            all_p131.update(p131_batch)
            total_relationships += sum(len(parents) for parents in p131_batch.values())

            # Rate limiting
            time.sleep(1)

        print(f"\n✓ Found {total_relationships:,} P131 relationships for {len(all_p131):,} places")
        return all_p131

    def create_p131_relationships(self, p131_map: Dict[str, List[str]], batch_size: int = 1000):
        """
        Create ADMINISTRATIVELY_LOCATED_IN relationships in Neo4j.

        Only creates relationships where both child and parent exist in our database.
        """
        print("\nCreating ADMINISTRATIVELY_LOCATED_IN relationships...")

        relationships = []
        for child_qid, parent_qids in p131_map.items():
            for parent_qid in parent_qids:
                relationships.append({
                    'childQid': child_qid,
                    'parentQid': parent_qid
                })

        print(f"Total P131 relationships to create: {len(relationships):,}")

        created = 0
        skipped = 0

        for i in tqdm(range(0, len(relationships), batch_size), desc="Creating relationships"):
            batch = relationships[i:i+batch_size]

            with self.driver.session() as session:
                result = session.run("""
                    UNWIND $rels AS rel
                    MATCH (child:Place {wikidataId: rel.childQid})
                    MATCH (parent:Place {wikidataId: rel.parentQid})
                    MERGE (child)-[r:ADMINISTRATIVELY_LOCATED_IN]->(parent)
                    SET r.source = 'wikidata_p131',
                        r.fetchedDate = datetime()
                    RETURN count(r) AS created
                """, rels=batch)

                created += result.single()['created']

        skipped = len(relationships) - created

        print(f"\n✓ Created {created:,} ADMINISTRATIVELY_LOCATED_IN relationships")
        print(f"  Skipped: {skipped:,} (parent/child not in database)")

    def print_statistics(self):
        """Print P131 relationship statistics."""
        print("\n" + "="*60)
        print("P131 (ADMINISTRATIVELY_LOCATED_IN) STATISTICS")
        print("="*60)

        with self.driver.session() as session:
            # Total relationships
            result = session.run("""
                MATCH ()-[r:ADMINISTRATIVELY_LOCATED_IN]->()
                RETURN count(r) AS count
            """)
            total = result.single()['count']

            # Places with P131 parents
            result = session.run("""
                MATCH (child:Place)-[:ADMINISTRATIVELY_LOCATED_IN]->(parent:Place)
                RETURN count(DISTINCT child) AS children,
                       count(DISTINCT parent) AS parents
            """)
            stats = result.single()
            children = stats['children']
            parents = stats['parents']

            print(f"\nTotal P131 relationships: {total:,}")
            print(f"  Places with parents: {children:,}")
            print(f"  Unique parent places: {parents:,}")

            # Top parent places (most children)
            result = session.run("""
                MATCH (child:Place)-[:ADMINISTRATIVELY_LOCATED_IN]->(parent:Place)
                RETURN parent.name AS parent_name,
                       parent.wikidataId AS parent_qid,
                       count(child) AS child_count
                ORDER BY child_count DESC
                LIMIT 10
            """)

            print(f"\nTop 10 Parent Places (most children):")
            for record in result:
                print(f"  {record['parent_name']} ({record['parent_qid']}): {record['child_count']:,} children")

            # Example: Places with both P131 and coordinate-based LOCATED_IN
            result = session.run("""
                MATCH (child:Place)-[:ADMINISTRATIVELY_LOCATED_IN]->(p131_parent:Place)
                MATCH (child)-[:LOCATED_IN]->(geo_parent:Place)
                WHERE p131_parent <> geo_parent
                RETURN child.name AS child_name,
                       p131_parent.name AS admin_parent,
                       geo_parent.name AS geo_parent
                LIMIT 10
            """)

            print(f"\nPlaces with different administrative vs geographic parents:")
            count = 0
            for record in result:
                print(f"  {record['child_name']}:")
                print(f"    Administrative (P131): {record['admin_parent']}")
                print(f"    Geographic (coords): {record['geo_parent']}")
                count += 1

            if count == 0:
                print("  (None found - run geographic linking first)")

        print("="*60)


def main():
    """Main execution."""
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

    print("="*60)
    print("Wikidata P131 (Located In) Relationship Fetcher")
    print("="*60)

    fetcher = WikidataP131Fetcher(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # Get all Wikidata IDs from Neo4j
        wikidata_ids = fetcher.get_all_wikidata_ids()

        # Fetch P131 relationships from Wikidata
        p131_map = fetcher.fetch_all_p131(wikidata_ids, batch_size=100)

        # Save to JSON cache (for future reference)
        cache_file = 'wikidata_p131_relationships.json'
        with open(cache_file, 'w') as f:
            json.dump(p131_map, f, indent=2)
        print(f"\n✓ Cached P131 data to {cache_file}")

        # Create relationships in Neo4j
        fetcher.create_p131_relationships(p131_map, batch_size=1000)

        # Print statistics
        fetcher.print_statistics()

        print("\n✓ P131 relationship import complete!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise

    finally:
        fetcher.close()


if __name__ == '__main__':
    main()
