#!/usr/bin/env python3
"""
Comprehensive Canadian Wikidata Integration

Fetches ALL Wikidata entries for Canadian locations and enriches the
Neo4j knowledge graph with text-based metadata (no images).

Strategy:
1. Query Wikidata for all Canadian geographic entities
2. Match to GeoNames by coordinates and names
3. Enrich with alternate names, historical data, Wikipedia links
4. Store as text properties in Neo4j (minimal space)
"""

import os
import time
import json
from typing import Dict, List, Optional, Set
from neo4j import GraphDatabase
from SPARQLWrapper import SPARQLWrapper, JSON as SPARQL_JSON
import requests
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()


class CanadaWikidataEnricher:
    """Comprehensive Wikidata enrichment for Canadian locations."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
        self.sparql.setReturnFormat(SPARQL_JSON)
        self.sparql.setTimeout(300)  # 5 minute timeout for large queries
        self.request_delay = 1.0  # Be nice to Wikidata

    def close(self):
        self.driver.close()

    def fetch_all_canadian_places_from_wikidata(self) -> List[Dict]:
        """
        Fetch ALL Canadian geographic places from Wikidata.

        This includes populated places, former settlements, geographic features, etc.
        Returns comprehensive text metadata without images.
        """

        # Query for Canadian geographic entities
        # P17 = country, Q16 = Canada
        # P625 = coordinate location
        query = """
        SELECT DISTINCT ?place ?placeLabel ?placeAltLabel ?coords ?population
               ?geonamesId ?inception ?dissolved ?wikipedia ?description
        WHERE {
          # Must be located in Canada
          ?place wdt:P17 wd:Q16 .

          # Must be a geographic/populated place (various types)
          ?place wdt:P31 ?instanceOf .
          VALUES ?instanceOf {
            wd:Q486972    # human settlement
            wd:Q515       # city
            wd:Q3957      # town
            wd:Q532       # village
            wd:Q5084      # hamlet
            wd:Q1549591   # big city
            wd:Q15979307  # former administrative unit
            wd:Q15063611  # ghost town
            wd:Q62049     # neighbourhood
            wd:Q15310171  # former municipality
            wd:Q7930989   # city/town
            wd:Q82794     # geographic region
            wd:Q1637706   # unincorporated community
            wd:Q2039348   # settlement
          }

          # Get coordinates if available
          OPTIONAL { ?place wdt:P625 ?coords . }

          # Get population if available
          OPTIONAL { ?place wdt:P1082 ?population . }

          # Get GeoNames ID if available (for matching)
          OPTIONAL { ?place wdt:P1566 ?geonamesId . }

          # Get temporal data
          OPTIONAL { ?place wdt:P571 ?inception . }      # founding date
          OPTIONAL { ?place wdt:P576 ?dissolved . }      # dissolution date

          # Get Wikipedia link (English)
          OPTIONAL {
            ?wikipedia schema:about ?place .
            ?wikipedia schema:inLanguage "en" .
            FILTER (SUBSTR(str(?wikipedia), 1, 25) = "https://en.wikipedia.org/")
          }

          # Get description
          OPTIONAL { ?place schema:description ?description . FILTER(LANG(?description) = "en") }

          # Get labels
          SERVICE wikibase:label {
            bd:serviceParam wikibase:language "en,fr" .
          }
        }
        """

        print("Querying Wikidata for ALL Canadian places (this may take several minutes)...")
        print("Note: Wikidata may timeout on very large queries. If so, we'll fetch in batches.")

        self.sparql.setQuery(query)

        try:
            results = self.sparql.query().convert()
            bindings = results.get('results', {}).get('bindings', [])

            print(f"✓ Retrieved {len(bindings):,} Canadian places from Wikidata")

            # Parse results
            places = []
            for b in bindings:
                place_data = self._parse_wikidata_binding(b)
                if place_data:
                    places.append(place_data)

            return places

        except Exception as e:
            print(f"✗ Error querying Wikidata: {e}")
            print("Falling back to batch fetching by GeoNames IDs...")
            return self._fetch_by_geonames_ids()

    def _parse_wikidata_binding(self, binding: Dict) -> Optional[Dict]:
        """Parse a Wikidata SPARQL result binding into structured data."""

        try:
            # Extract Q-number from URI
            place_uri = binding.get('place', {}).get('value', '')
            qid = place_uri.split('/')[-1] if place_uri else None

            if not qid or not qid.startswith('Q'):
                return None

            # Parse coordinates
            coords_str = binding.get('coords', {}).get('value', '')
            lat, lon = None, None
            if coords_str:
                # Format: "Point(longitude latitude)"
                try:
                    coords_parts = coords_str.replace('Point(', '').replace(')', '').split()
                    lon = float(coords_parts[0])
                    lat = float(coords_parts[1])
                except:
                    pass

            # Parse alternate labels (comes as single string, space-separated)
            alt_labels = binding.get('placeAltLabel', {}).get('value', '')
            alt_names = [a.strip() for a in alt_labels.split(',') if a.strip()] if alt_labels else []

            return {
                'qid': qid,
                'name': binding.get('placeLabel', {}).get('value'),
                'alternateNames': alt_names,
                'description': binding.get('description', {}).get('value'),
                'latitude': lat,
                'longitude': lon,
                'population': binding.get('population', {}).get('value'),
                'geonamesId': binding.get('geonamesId', {}).get('value'),
                'inceptionDate': binding.get('inception', {}).get('value'),
                'dissolvedDate': binding.get('dissolved', {}).get('value'),
                'wikipediaUrl': binding.get('wikipedia', {}).get('value')
            }

        except Exception as e:
            print(f"Error parsing binding: {e}")
            return None

    def _fetch_by_geonames_ids(self) -> List[Dict]:
        """
        Fallback method: Fetch Wikidata entries by querying for all
        GeoNames IDs that exist in our Neo4j database.
        """

        print("Fetching by GeoNames IDs from Neo4j...")

        # Get all Canadian GeoNames IDs from our database
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Place)
                WHERE p.countryCode = 'CA'
                RETURN p.geonameId AS geonameId
            """)
            geonames_ids = [record['geonameId'] for record in result]

        print(f"Found {len(geonames_ids):,} Canadian places in Neo4j")

        # Query Wikidata in batches
        batch_size = 1000
        all_places = []

        for i in tqdm(range(0, len(geonames_ids), batch_size), desc="Fetching Wikidata batches"):
            batch_ids = geonames_ids[i:i+batch_size]

            # Create VALUES clause for batch
            values_clause = ' '.join([f'"{gid}"' for gid in batch_ids])

            query = f"""
            SELECT DISTINCT ?place ?placeLabel ?placeAltLabel ?coords ?population
                   ?geonamesId ?inception ?dissolved ?wikipedia ?description
            WHERE {{
              VALUES ?geonamesId {{ {values_clause} }}
              ?place wdt:P1566 ?geonamesId .

              OPTIONAL {{ ?place wdt:P625 ?coords . }}
              OPTIONAL {{ ?place wdt:P1082 ?population . }}
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

            self.sparql.setQuery(query)

            try:
                results = self.sparql.query().convert()
                bindings = results.get('results', {}).get('bindings', [])

                for b in bindings:
                    place_data = self._parse_wikidata_binding(b)
                    if place_data:
                        all_places.append(place_data)

                time.sleep(self.request_delay)  # Be nice to Wikidata

            except Exception as e:
                print(f"Error fetching batch {i}: {e}")
                continue

        print(f"✓ Retrieved {len(all_places):,} places from Wikidata")
        return all_places

    def get_additional_alternate_names(self, qid: str) -> List[str]:
        """
        Fetch comprehensive alternate names for a Wikidata entity.
        Includes historical names, alternate spellings, names in different languages.
        """

        query = f"""
        SELECT ?altLabel ?language WHERE {{
          wd:{qid} skos:altLabel ?altLabel .
          BIND(LANG(?altLabel) AS ?language)
          FILTER(?language IN ("en", "fr", ""))
        }}
        """

        self.sparql.setQuery(query)

        try:
            results = self.sparql.query().convert()
            bindings = results.get('results', {}).get('bindings', [])
            return list(set([b['altLabel']['value'] for b in bindings if 'altLabel' in b]))
        except:
            return []

    def match_and_update_by_geonames_id(self, wikidata_places: List[Dict]) -> int:
        """Match Wikidata entries to Neo4j places by GeoNames ID and update."""

        matched = 0

        for wd_place in tqdm(wikidata_places, desc="Matching by GeoNames ID"):
            geonames_id = wd_place.get('geonamesId')

            if not geonames_id:
                continue

            try:
                geonames_id_int = int(geonames_id)
            except:
                continue

            # Get additional alternate names
            if wd_place.get('qid'):
                additional_names = self.get_additional_alternate_names(wd_place['qid'])
                all_alt_names = list(set(wd_place.get('alternateNames', []) + additional_names))
            else:
                all_alt_names = wd_place.get('alternateNames', [])

            # Update Neo4j
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (p:Place {geonameId: $geonameId})
                    SET p.wikidataId = $qid,
                        p.wikipediaUrl = $wikipediaUrl,
                        p.wikidataDescription = $description,
                        p.wikidataPopulation = $population,
                        p.inceptionDate = $inceptionDate,
                        p.dissolvedDate = $dissolvedDate,
                        p.wikidataAlternateNames = $altNames,
                        p.wikidataLatitude = $lat,
                        p.wikidataLongitude = $lon
                    RETURN count(p) AS updated
                """,
                    geonameId=geonames_id_int,
                    qid=wd_place.get('qid'),
                    wikipediaUrl=wd_place.get('wikipediaUrl'),
                    description=wd_place.get('description'),
                    population=wd_place.get('population'),
                    inceptionDate=wd_place.get('inceptionDate'),
                    dissolvedDate=wd_place.get('dissolvedDate'),
                    altNames=all_alt_names,
                    lat=wd_place.get('latitude'),
                    lon=wd_place.get('longitude')
                )

                if result.single()['updated'] > 0:
                    matched += 1

        return matched

    def create_wikidata_only_places(self, wikidata_places: List[Dict]) -> int:
        """
        Create Place nodes for Wikidata entries that don't have GeoNames matches.
        These might be historical places, neighbourhoods, etc. not in GeoNames.
        """

        created = 0

        for wd_place in tqdm(wikidata_places, desc="Creating Wikidata-only places"):
            # Skip if already matched via GeoNames ID
            if wd_place.get('geonamesId'):
                continue

            # Must have coordinates and name to be useful
            if not (wd_place.get('latitude') and wd_place.get('longitude') and wd_place.get('name')):
                continue

            # Get additional alternate names
            if wd_place.get('qid'):
                additional_names = self.get_additional_alternate_names(wd_place['qid'])
                all_alt_names = list(set(wd_place.get('alternateNames', []) + additional_names))
            else:
                all_alt_names = wd_place.get('alternateNames', [])

            with self.driver.session() as session:
                session.run("""
                    MERGE (p:Place {wikidataId: $qid})
                    ON CREATE SET
                        p.name = $name,
                        p.countryCode = 'CA',
                        p.latitude = $lat,
                        p.longitude = $lon,
                        p.source = 'wikidata',
                        p.featureClass = 'P',
                        p.featureCode = 'PPL'
                    SET p.wikipediaUrl = $wikipediaUrl,
                        p.wikidataDescription = $description,
                        p.wikidataPopulation = $population,
                        p.inceptionDate = $inceptionDate,
                        p.dissolvedDate = $dissolvedDate,
                        p.alternateNames = $altNames,
                        p.wikidataAlternateNames = $altNames

                    MERGE (c:Country {code: 'CA'})
                    MERGE (p)-[:LOCATED_IN_COUNTRY]->(c)
                """,
                    qid=wd_place['qid'],
                    name=wd_place['name'],
                    lat=wd_place['latitude'],
                    lon=wd_place['longitude'],
                    wikipediaUrl=wd_place.get('wikipediaUrl'),
                    description=wd_place.get('description'),
                    population=wd_place.get('population'),
                    inceptionDate=wd_place.get('inceptionDate'),
                    dissolvedDate=wd_place.get('dissolvedDate'),
                    altNames=all_alt_names
                )

                created += 1

        return created

    def enrich_all_canadian_places(self):
        """Main enrichment process for all Canadian places."""

        print("\n" + "="*60)
        print("Comprehensive Canadian Wikidata Enrichment")
        print("="*60)

        # Fetch all Canadian places from Wikidata
        wikidata_places = self.fetch_all_canadian_places_from_wikidata()

        if not wikidata_places:
            print("✗ No Wikidata results retrieved")
            return

        print(f"\nProcessing {len(wikidata_places):,} Wikidata entries...")

        # Match and update existing GeoNames places
        matched = self.match_and_update_by_geonames_id(wikidata_places)
        print(f"✓ Matched and updated {matched:,} existing places")

        # Create new places for Wikidata-only entries
        created = self.create_wikidata_only_places(wikidata_places)
        print(f"✓ Created {created:,} new places from Wikidata")

        print("\n✓ Canadian Wikidata enrichment complete!")

    def print_enrichment_statistics(self):
        """Print comprehensive enrichment statistics."""

        print("\n" + "="*60)
        print("CANADIAN WIKIDATA ENRICHMENT STATISTICS")
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

            # Historical places (dissolved)
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

            print("\n" + "="*60)


def main():
    """Main execution function."""

    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

    print("="*60)
    print("Comprehensive Canadian Wikidata Integration")
    print("="*60)

    enricher = CanadaWikidataEnricher(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # Enrich all Canadian places
        enricher.enrich_all_canadian_places()

        # Print statistics
        enricher.print_enrichment_statistics()

    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise

    finally:
        enricher.close()


if __name__ == '__main__':
    main()
