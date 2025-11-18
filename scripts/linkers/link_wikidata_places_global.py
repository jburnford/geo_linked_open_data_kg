#!/usr/bin/env python3
"""
Link WikidataPlace to Place (GeoNames) using direct ID matches and geographic proximity.

Adapted from link_by_geography.py for global scale (24.5M nodes vs 556K).

Key differences:
- Source: WikidataPlace nodes (11.5M) instead of Place nodes with wikidataId
- Target: Place nodes (6.2M GeoNames places)
- Scale: Country-by-country processing for memory efficiency
- Phase 1: Direct geonamesId links (fast, ~2-3M expected)
- Phase 2: Geographic proximity links (4-6 hours, ~7-10M expected)

Relationship types (from proven spatial linking):
- SAME_AS: High confidence identity match (confidence ≥0.85, distance <1km)
- NEAR: Spatial proximity (confidence ≥0.5, distance ≤10km)
- LOCATED_IN: POI containment (low-priority entity within settlement)
"""

import os
from typing import List, Dict, Optional
from neo4j import GraphDatabase
from tqdm import tqdm


class WikidataPlaceLinker:
    """Link WikidataPlace to Place using direct IDs and geographic proximity."""

    def __init__(self, uri: str = "bolt://localhost:7687",
                 user: str = "neo4j",
                 password: str = "historicalkg2025"):
        print(f"Connecting to {uri}...")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    # ========================================================================
    # PHASE 1: DIRECT GEONAMES ID LINKS
    # ========================================================================

    def link_by_geonames_id(self, batch_size: int = 50000):
        """
        Fast direct linking via geonamesId property match.

        Expected: 2-3M WikidataPlace nodes have geonamesId.
        Time: ~30 minutes
        """
        print("\n" + "="*60)
        print("PHASE 1.1: Direct geonamesId Links")
        print("="*60)

        # Count linkable entities
        with self.driver.session() as session:
            result = session.run("""
                MATCH (wp:WikidataPlace)
                WHERE wp.geonamesId IS NOT NULL
                  AND NOT EXISTS((wp)-[:SAME_AS]->())
                RETURN count(wp) as total
            """)
            total = result.single()['total']

        print(f"Found {total:,} WikidataPlace nodes with geonamesId property")
        print(f"Creating SAME_AS links to Place nodes...")

        # Create links in batches
        with self.driver.session() as session:
            result = session.run(f"""
                CALL {{
                    MATCH (wp:WikidataPlace)
                    WHERE wp.geonamesId IS NOT NULL
                      AND NOT EXISTS((wp)-[:SAME_AS]->())
                    WITH wp LIMIT {batch_size}
                    MATCH (p:Place {{geonameId: wp.geonamesId}})
                    MERGE (wp)-[r:SAME_AS]->(p)
                    SET r.evidence = 'geonames_id_match',
                        r.confidence = 1.0,
                        r.distance_km = 0.0,
                        r.linkedDate = datetime()
                    RETURN count(r) as batch_count
                }} IN TRANSACTIONS OF {batch_size} ROWS
                RETURN sum(batch_count) as total_count
            """)

            count = result.single()['total_count']
            print(f"✓ Created {count:,} SAME_AS relationships via geonamesId match")

        return count

    # ========================================================================
    # PHASE 2: GEOGRAPHIC PROXIMITY LINKS
    # ========================================================================

    def get_countries_with_unlinked_places(self) -> List[tuple]:
        """
        Get countries that have unlinked WikidataPlace nodes.

        Returns list of (countryQid, count) tuples ordered by count DESC.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (wp:WikidataPlace)
                WHERE wp.countryQid IS NOT NULL
                  AND wp.latitude IS NOT NULL
                  AND wp.longitude IS NOT NULL
                  AND NOT EXISTS((wp)-[:SAME_AS|NEAR|LOCATED_IN]->())
                RETURN DISTINCT wp.countryQid AS country, count(*) AS count
                ORDER BY count DESC
            """)
            return [(r['country'], r['count']) for r in result]

    def get_unlinked_wikidata_places_for_country(self, country_qid: str) -> List[Dict]:
        """
        Get WikidataPlace nodes for a country that lack geographic links.

        Args:
            country_qid: Wikidata QID for country (e.g., "Q16" for Canada)

        Returns:
            List of place dictionaries with coordinates
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (wp:WikidataPlace)
                WHERE wp.countryQid = $countryQid
                  AND wp.latitude IS NOT NULL
                  AND wp.longitude IS NOT NULL
                  AND NOT EXISTS((wp)-[:SAME_AS|NEAR|LOCATED_IN]->())
                RETURN wp.qid AS qid,
                       wp.name AS name,
                       wp.latitude AS lat,
                       wp.longitude AS lon,
                       wp.instanceOfQid AS instanceType
                LIMIT 50000
            """, countryQid=country_qid)

            return [dict(record) for record in result]

    def find_nearby_geonames_places(self, lat: float, lon: float,
                                    country_code: Optional[str] = None,
                                    max_distance_km: float = 10.0) -> List[Dict]:
        """
        Find GeoNames Place nodes within distance threshold.

        Args:
            lat, lon: Coordinates to search around
            country_code: Optional 2-letter country code filter (e.g., "CA")
            max_distance_km: Maximum distance in kilometers

        Returns:
            List of nearby places with distances
        """
        # Build query with optional country filter
        country_filter = "AND p.countryCode = $countryCode" if country_code else ""

        with self.driver.session() as session:
            result = session.run(f"""
                MATCH (p:Place)
                WHERE p.geonameId IS NOT NULL
                  AND p.location IS NOT NULL
                  {country_filter}
                WITH p,
                     point.distance(p.location, point({{latitude: $lat, longitude: $lon}})) / 1000.0 AS distance_km
                WHERE distance_km <= $maxDistance
                RETURN p.geonameId AS geonameId,
                       p.name AS name,
                       p.latitude AS lat,
                       p.longitude AS lon,
                       p.featureClass AS featureClass,
                       p.featureCode AS featureCode,
                       p.population AS population,
                       distance_km
                ORDER BY distance_km ASC
                LIMIT 10
            """,
                lat=lat,
                lon=lon,
                countryCode=country_code,
                maxDistance=max_distance_km
            )

            return [dict(record) for record in result]

    def get_entity_priority(self, place: Dict, is_wikidata: bool = False) -> int:
        """
        Get entity type priority score.

        Higher priority = more likely target for settlement linking.
        Avoids linking to POIs/buildings when we want administrative areas.

        Args:
            place: Place dictionary with type information
            is_wikidata: True for WikidataPlace, False for GeoNames Place

        Returns:
            Priority score 0-100 (higher = more important)
        """
        if is_wikidata:
            # WikidataPlace has instanceOfQid (need to map QIDs to types)
            # For now, use simple heuristics - could enhance with QID lookup
            instance_qid = place.get('instanceType', '')

            # Administrative divisions (Q administrative territorial entity subtypes)
            # These are high priority targets
            return 70  # Default for WikidataPlace

        else:
            # GeoNames feature codes
            feature_code = (place.get('featureCode') or '').upper()

            if feature_code.startswith('ADM'):  # Administrative division
                return 85
            elif feature_code.startswith('PPLA'):  # Admin seat (capital, etc.)
                return 80
            elif feature_code == 'PPL':  # Populated place
                return 70
            elif feature_code == 'AREA':  # Area
                return 75
            elif feature_code == 'PPLX':  # Section of populated place
                return 40

            return 50  # Default

    def calculate_confidence(self, wikidata_place: Dict, geonames_place: Dict,
                            distance_km: float) -> float:
        """
        Calculate confidence score for a geographic match.

        Uses proven formula from Canadian LOD project:
        - Distance: 30% weight (closer = higher confidence)
        - Name similarity: 50% weight (CRITICAL for precision)
        - Entity type: 20% weight (settlement vs POI priority)

        Returns:
            Confidence score 0.0-1.0
        """
        # Distance component (exponential decay)
        if distance_km <= 0.1:
            distance_score = 1.0
        elif distance_km <= 1.0:
            distance_score = 0.9
        elif distance_km <= 5.0:
            distance_score = 0.7
        elif distance_km <= 10.0:
            distance_score = 0.5
        else:
            distance_score = 0.3

        # Name similarity component
        wd_name = (wikidata_place.get('name') or '').lower()
        gn_name = (geonames_place.get('name') or '').lower()

        if wd_name == gn_name:
            name_score = 1.0
        elif wd_name in gn_name or gn_name in wd_name:
            name_score = 0.8
        else:
            # Check word overlap
            wd_words = set(wd_name.split())
            gn_words = set(gn_name.split())
            overlap = len(wd_words & gn_words)
            if overlap > 0:
                name_score = 0.5 * (overlap / max(len(wd_words), len(gn_words)))
            else:
                name_score = 0.0

        # Entity type compatibility (normalized to 0-1)
        wd_priority = self.get_entity_priority(wikidata_place, is_wikidata=True)
        gn_priority = self.get_entity_priority(geonames_place, is_wikidata=False)

        # Average of both priorities, normalized
        type_score = ((wd_priority + gn_priority) / 2) / 100.0

        # Bonus if both are high-priority (settlements/admin divisions)
        if wd_priority >= 70 and gn_priority >= 70:
            type_score = min(type_score * 1.2, 1.0)

        # Weighted combination - NAME is 50% to prevent false SAME_AS links
        confidence = (distance_score * 0.30) + (name_score * 0.50) + (type_score * 0.20)

        return min(confidence, 1.0)

    def link_by_geography_for_country(self, country_qid: str,
                                     distance_threshold: float = 10.0,
                                     min_confidence: float = 0.5,
                                     batch_size: int = 100):
        """
        Link WikidataPlace to Place for one country using geographic proximity.

        Args:
            country_qid: Wikidata QID for country
            distance_threshold: Maximum distance to consider (km)
            min_confidence: Minimum confidence score to create link
            batch_size: Batch size for database writes
        """
        wikidata_places = self.get_unlinked_wikidata_places_for_country(country_qid)

        if not wikidata_places:
            return 0

        links_created = 0
        links_batch = []

        # Get country code for GeoNames filtering (if possible)
        # For now, we'll do spatial search without country filter
        # Could enhance with QID→country_code mapping

        for wd_place in tqdm(wikidata_places, desc=f"Linking {country_qid}"):
            # Find nearby GeoNames places
            nearby = self.find_nearby_geonames_places(
                wd_place['lat'],
                wd_place['lon'],
                max_distance_km=distance_threshold
            )

            if not nearby:
                continue

            # Find best match(es)
            for gn_place in nearby:
                confidence = self.calculate_confidence(
                    wd_place,
                    gn_place,
                    gn_place['distance_km']
                )

                if confidence >= min_confidence:
                    # Determine relationship type
                    wd_priority = self.get_entity_priority(wd_place, is_wikidata=True)
                    gn_priority = self.get_entity_priority(gn_place, is_wikidata=False)

                    # LOCATED_IN: POI/building contained in settlement
                    if (wd_priority < 60 and gn_priority >= 60 and
                        gn_place['distance_km'] <= 5.0):
                        rel_type = 'LOCATED_IN'
                    # SAME_AS: High confidence + close distance + name similarity
                    elif (confidence >= 0.85 and gn_place['distance_km'] <= 1.0):
                        rel_type = 'SAME_AS'
                    else:
                        rel_type = 'NEAR'  # Default spatial proximity

                    links_batch.append({
                        'wikidataQid': wd_place['qid'],
                        'geonameId': gn_place['geonameId'],
                        'distance_km': round(gn_place['distance_km'], 3),
                        'confidence': round(confidence, 3),
                        'matchMethod': 'geographic_proximity',
                        'relType': rel_type
                    })

            # Commit batch
            if len(links_batch) >= batch_size:
                self._create_links_batch(links_batch)
                links_created += len(links_batch)
                links_batch = []

        # Create remaining links
        if links_batch:
            self._create_links_batch(links_batch)
            links_created += len(links_batch)

        return links_created

    def _create_links_batch(self, links: List[Dict]):
        """Create a batch of geographic relationships."""
        with self.driver.session() as session:
            # Separate links by type
            same_as_links = [l for l in links if l['relType'] == 'SAME_AS']
            near_links = [l for l in links if l['relType'] == 'NEAR']
            located_in_links = [l for l in links if l['relType'] == 'LOCATED_IN']

            # Create SAME_AS relationships
            if same_as_links:
                session.run("""
                    UNWIND $links AS link
                    MATCH (wp:WikidataPlace {qid: link.wikidataQid})
                    MATCH (p:Place {geonameId: link.geonameId})
                    MERGE (wp)-[r:SAME_AS]->(p)
                    SET r.distance_km = link.distance_km,
                        r.confidence = link.confidence,
                        r.evidence = link.matchMethod,
                        r.linkedDate = datetime()
                """, links=same_as_links)

            # Create NEAR relationships
            if near_links:
                session.run("""
                    UNWIND $links AS link
                    MATCH (wp:WikidataPlace {qid: link.wikidataQid})
                    MATCH (p:Place {geonameId: link.geonameId})
                    MERGE (wp)-[r:NEAR]->(p)
                    SET r.distance_km = link.distance_km,
                        r.confidence = link.confidence,
                        r.matchMethod = link.matchMethod,
                        r.linkedDate = datetime()
                """, links=near_links)

            # Create LOCATED_IN relationships
            if located_in_links:
                session.run("""
                    UNWIND $links AS link
                    MATCH (wp:WikidataPlace {qid: link.wikidataQid})
                    MATCH (p:Place {geonameId: link.geonameId})
                    MERGE (wp)-[r:LOCATED_IN]->(p)
                    SET r.distance_km = link.distance_km,
                        r.confidence = link.confidence,
                        r.matchMethod = link.matchMethod,
                        r.linkedDate = datetime()
                """, links=located_in_links)

    # ========================================================================
    # ORCHESTRATION
    # ========================================================================

    def link_all_by_geography(self, distance_threshold: float = 10.0,
                             min_confidence: float = 0.5):
        """
        Link all unlinked WikidataPlace nodes country-by-country.

        This processes one country at a time to avoid memory issues with
        11.5M WikidataPlace nodes.
        """
        print("\n" + "="*60)
        print("PHASE 1.2: Geographic Proximity Links")
        print("="*60)
        print(f"Distance threshold: {distance_threshold} km")
        print(f"Minimum confidence: {min_confidence}")

        countries = self.get_countries_with_unlinked_places()
        print(f"\nFound {len(countries)} countries with unlinked places")

        total_links = 0

        for country_qid, count in countries:
            print(f"\n{country_qid}: {count:,} unlinked places")
            links = self.link_by_geography_for_country(
                country_qid,
                distance_threshold,
                min_confidence
            )
            total_links += links
            print(f"  ✓ Created {links:,} links")

        print(f"\n✓ Total geographic links created: {total_links:,}")

    # ========================================================================
    # STATISTICS
    # ========================================================================

    def print_statistics(self):
        """Print linking statistics."""
        print("\n" + "="*60)
        print("WIKIDATA PLACE LINKING STATISTICS")
        print("="*60)

        with self.driver.session() as session:
            # Total WikidataPlace nodes
            result = session.run("MATCH (wp:WikidataPlace) RETURN count(wp) as total")
            total_wp = result.single()['total']

            # Linked via SAME_AS
            result = session.run("""
                MATCH (wp:WikidataPlace)-[:SAME_AS]->()
                RETURN count(DISTINCT wp) as count
            """)
            same_as_count = result.single()['count']

            # Linked via NEAR
            result = session.run("""
                MATCH (wp:WikidataPlace)-[:NEAR]->()
                RETURN count(DISTINCT wp) as count
            """)
            near_count = result.single()['count']

            # Linked via LOCATED_IN
            result = session.run("""
                MATCH (wp:WikidataPlace)-[:LOCATED_IN]->()
                RETURN count(DISTINCT wp) as count
            """)
            located_in_count = result.single()['count']

            # Any link
            result = session.run("""
                MATCH (wp:WikidataPlace)
                WHERE EXISTS((wp)-[:SAME_AS|NEAR|LOCATED_IN]->())
                RETURN count(DISTINCT wp) as count
            """)
            linked = result.single()['count']

            # Relationship counts
            result = session.run("MATCH ()-[r:SAME_AS]->() RETURN count(r) as count")
            same_as_rels = result.single()['count']

            result = session.run("MATCH ()-[r:NEAR]->() RETURN count(r) as count")
            near_rels = result.single()['count']

            result = session.run("MATCH ()-[r:LOCATED_IN]->() RETURN count(r) as count")
            located_in_rels = result.single()['count']

            print(f"\nWikidataPlace nodes: {total_wp:,}")
            print(f"  With SAME_AS links: {same_as_count:,} ({(same_as_count/total_wp)*100:.1f}%)")
            print(f"  With NEAR links: {near_count:,} ({(near_count/total_wp)*100:.1f}%)")
            print(f"  With LOCATED_IN links: {located_in_count:,} ({(located_in_count/total_wp)*100:.1f}%)")
            print(f"  Total linked: {linked:,} ({(linked/total_wp)*100:.1f}%)")
            print(f"  Unlinked: {total_wp - linked:,}")

            print(f"\nRelationships:")
            print(f"  SAME_AS (identity): {same_as_rels:,}")
            print(f"  NEAR (proximity): {near_rels:,}")
            print(f"  LOCATED_IN (containment): {located_in_rels:,}")
            print(f"  Total: {same_as_rels + near_rels + located_in_rels:,}")

            # Sample high-confidence links
            result = session.run("""
                MATCH (wp:WikidataPlace)-[r:SAME_AS]->(p:Place)
                WHERE r.confidence > 0.9
                RETURN wp.name AS wikidata_name,
                       p.name AS geonames_name,
                       r.distance_km AS distance,
                       r.confidence AS confidence
                ORDER BY r.confidence DESC
                LIMIT 10
            """)

            print(f"\nTop 10 SAME_AS Links (confidence > 0.9):")
            for record in result:
                print(f"  {record['wikidata_name']} → {record['geonames_name']}")
                print(f"    Distance: {record['distance']:.2f} km, Confidence: {record['confidence']:.3f}")

        print("="*60)


def main():
    """Main execution."""
    print("="*60)
    print("WikidataPlace → Place Linker (Global Scale)")
    print("="*60)

    linker = WikidataPlaceLinker()

    try:
        # Phase 1.1: Direct geonamesId links (fast)
        linker.link_by_geonames_id()

        # Phase 1.2: Geographic proximity links (country-by-country)
        linker.link_all_by_geography(
            distance_threshold=10.0,
            min_confidence=0.5
        )

        # Print statistics
        linker.print_statistics()

        print("\n✓ WikidataPlace linking complete!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        linker.close()


if __name__ == '__main__':
    main()
