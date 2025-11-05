#!/usr/bin/env python3
"""
Link Wikidata-only places to GeoNames places using geographic proximity.

Strategy:
- Find Wikidata places that lack GeoNames ID linkage
- Search for nearby GeoNames places within threshold distance
- Create NEAR relationships with distance and confidence scores
- Use multiple distance thresholds for different confidence levels

This helps resolve cases like:
- Maitland, NS (wrong coords in GeoNames, correct in Wikidata)
- Administrative divisions that overlap with settlements
- Name variants that don't match exactly
"""

import os
from typing import List, Dict, Tuple
from neo4j import GraphDatabase
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()


class GeographicLinker:
    """Link places using geographic proximity."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def get_wikidata_only_places(self) -> List[Dict]:
        """
        Get Wikidata places that aren't linked to GeoNames.

        These are the 17K+ places we need to link geographically.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Place)
                WHERE p.wikidataId IS NOT NULL
                  AND p.geonameId IS NULL
                  AND p.latitude IS NOT NULL
                  AND p.longitude IS NOT NULL
                  AND p.countryCode = 'CA'
                RETURN p.wikidataId AS wikidataId,
                       p.name AS name,
                       p.latitude AS lat,
                       p.longitude AS lon,
                       p.instanceOfLabel AS type
            """)

            places = [dict(record) for record in result]

        print(f"Found {len(places):,} Wikidata-only places with coordinates")
        return places

    def find_nearby_geonames_places(self, lat: float, lon: float,
                                    max_distance_km: float = 10.0) -> List[Dict]:
        """
        Find GeoNames places within distance threshold.

        Args:
            lat, lon: Coordinates to search around
            max_distance_km: Maximum distance in kilometers

        Returns:
            List of nearby places with distances
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Place)
                WHERE p.geonameId IS NOT NULL
                  AND p.latitude IS NOT NULL
                  AND p.longitude IS NOT NULL
                  AND p.countryCode = 'CA'
                WITH p,
                     point.distance(
                         point({latitude: p.latitude, longitude: p.longitude}),
                         point({latitude: $lat, longitude: $lon})
                     ) / 1000.0 AS distance_km
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
                maxDistance=max_distance_km
            )

            return [dict(record) for record in result]

    def get_entity_priority(self, place: Dict, is_wikidata: bool = False) -> int:
        """
        Get entity type priority score.

        Practice for HGIS linking: higher priority = more likely target for historical data.
        Avoids linking to POIs/buildings when we want settlements.
        """
        if is_wikidata:
            instance_type = (place.get('type') or '').lower()
            # Administrative divisions
            if any(x in instance_type for x in ['county', 'township', 'municipality', 'division']):
                return 85
            # Settlements
            if any(x in instance_type for x in ['city', 'town', 'village', 'settlement']):
                return 70
            # Sub-areas
            if 'neighbourhood' in instance_type or 'district' in instance_type:
                return 40
            return 50  # Default
        else:
            # GeoNames feature codes
            feature_code = (place.get('featureCode') or '').upper()
            if feature_code.startswith('ADM'):  # Administrative
                return 85
            elif feature_code.startswith('PPLA'):  # Admin seat
                return 80
            elif feature_code == 'PPL':  # Populated place
                return 70
            elif feature_code == 'AREA':  # Area
                return 75
            elif feature_code == 'PPLX':  # Section (lower priority)
                return 40
            return 50

    def calculate_confidence(self, wikidata_place: Dict, geonames_place: Dict,
                            distance_km: float) -> float:
        """
        Calculate confidence score for a geographic match.

        Factors (tuned for HGIS linking experience):
        - Distance (40% weight) - closer = higher confidence
        - Name similarity (35% weight) - same/similar name = higher
        - Entity type compatibility (25% weight) - settlement vs POI priority

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
        wd_name = wikidata_place['name'].lower() if wikidata_place.get('name') else ''
        gn_name = geonames_place['name'].lower() if geonames_place.get('name') else ''

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

        # Weighted combination
        # Practice for HGIS: balanced weights for learning
        confidence = (distance_score * 0.40) + (name_score * 0.35) + (type_score * 0.25)

        return min(confidence, 1.0)

    def create_geographic_links(self, distance_threshold: float = 10.0,
                               min_confidence: float = 0.5,
                               batch_size: int = 100):
        """
        Create NEAR relationships between Wikidata and GeoNames places.

        Args:
            distance_threshold: Maximum distance to consider (km)
            min_confidence: Minimum confidence score to create link
            batch_size: Number of places to process before committing
        """
        print(f"\nCreating geographic links...")
        print(f"  Distance threshold: {distance_threshold} km")
        print(f"  Minimum confidence: {min_confidence}")

        wikidata_places = self.get_wikidata_only_places()

        links_created = 0
        links_batch = []

        for wd_place in tqdm(wikidata_places, desc="Linking by geography"):
            # Find nearby GeoNames places
            nearby = self.find_nearby_geonames_places(
                wd_place['lat'],
                wd_place['lon'],
                distance_threshold
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
                    links_batch.append({
                        'wikidataId': wd_place['wikidataId'],
                        'geonameId': gn_place['geonameId'],
                        'distance_km': round(gn_place['distance_km'], 3),
                        'confidence': round(confidence, 3),
                        'matchMethod': 'geographic_proximity'
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

        print(f"\n✓ Created {links_created:,} geographic links")
        print(f"  Average: {links_created / len(wikidata_places):.2f} links per Wikidata place")

    def _create_links_batch(self, links: List[Dict]):
        """Create a batch of NEAR relationships."""
        with self.driver.session() as session:
            session.run("""
                UNWIND $links AS link
                MATCH (wd:Place {wikidataId: link.wikidataId})
                MATCH (gn:Place {geonameId: link.geonameId})
                MERGE (wd)-[r:NEAR]->(gn)
                SET r.distance_km = link.distance_km,
                    r.confidence = link.confidence,
                    r.matchMethod = link.matchMethod,
                    r.linkedDate = datetime()
            """, links=links)

    def create_high_confidence_same_as_links(self, confidence_threshold: float = 0.85):
        """
        Create SAME_AS relationships for very high confidence geographic matches.

        These are places that are almost certainly the same entity:
        - Very close distance (< 1km)
        - Same or very similar name
        - Compatible types
        - High confidence score (> 0.85)
        """
        print(f"\nCreating SAME_AS links for high confidence matches (>{confidence_threshold})...")

        with self.driver.session() as session:
            result = session.run("""
                MATCH (wd:Place)-[r:NEAR]->(gn:Place)
                WHERE r.confidence >= $threshold
                  AND r.distance_km <= 1.0
                MERGE (wd)-[s:SAME_AS]->(gn)
                SET s.confidence = r.confidence,
                    s.distance_km = r.distance_km,
                    s.evidence = 'geographic_proximity_high_confidence'
                RETURN count(s) AS count
            """, threshold=confidence_threshold)

            count = result.single()['count']
            print(f"✓ Created {count:,} SAME_AS relationships")

    def print_statistics(self):
        """Print linking statistics."""
        print("\n" + "="*60)
        print("GEOGRAPHIC LINKING STATISTICS")
        print("="*60)

        with self.driver.session() as session:
            # Total Wikidata places
            result = session.run("""
                MATCH (p:Place)
                WHERE p.wikidataId IS NOT NULL AND p.geonameId IS NULL
                RETURN count(p) AS count
            """)
            wikidata_only = result.single()['count']

            # Places with NEAR links
            result = session.run("""
                MATCH (wd:Place {geonameId: NULL})-[:NEAR]->(gn:Place)
                WHERE wd.wikidataId IS NOT NULL
                RETURN count(DISTINCT wd) AS count
            """)
            linked = result.single()['count']

            # Total NEAR relationships
            result = session.run("""
                MATCH ()-[r:NEAR]->()
                RETURN count(r) AS count
            """)
            total_links = result.single()['count']

            # SAME_AS relationships
            result = session.run("""
                MATCH ()-[r:SAME_AS]->()
                RETURN count(r) AS count
            """)
            same_as = result.single()['count']

            # Average confidence
            result = session.run("""
                MATCH ()-[r:NEAR]->()
                RETURN avg(r.confidence) AS avg_confidence,
                       avg(r.distance_km) AS avg_distance
            """)
            stats = result.single()
            avg_conf = stats['avg_confidence']
            avg_dist = stats['avg_distance']

            print(f"\nWikidata-only places: {wikidata_only:,}")
            print(f"  Linked geographically: {linked:,} ({(linked/wikidata_only)*100:.1f}%)")
            print(f"  Unlinked: {wikidata_only - linked:,}")

            print(f"\nRelationships:")
            print(f"  NEAR links: {total_links:,}")
            print(f"  SAME_AS links: {same_as:,}")

            if avg_conf:
                print(f"\nAverage NEAR link:")
                print(f"  Confidence: {avg_conf:.3f}")
                print(f"  Distance: {avg_dist:.2f} km")

            # Top linked places
            result = session.run("""
                MATCH (wd:Place)-[r:NEAR]->(gn:Place)
                WHERE r.confidence > 0.8
                RETURN wd.name AS wikidata_name,
                       gn.name AS geonames_name,
                       r.distance_km AS distance,
                       r.confidence AS confidence
                ORDER BY r.confidence DESC
                LIMIT 10
            """)

            print(f"\nTop 10 High-Confidence Matches:")
            for record in result:
                print(f"  {record['wikidata_name']} → {record['geonames_name']}")
                print(f"    Distance: {record['distance']:.2f} km, Confidence: {record['confidence']:.3f}")

        print("="*60)


def main():
    """Main execution."""
    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

    print("="*60)
    print("Geographic Place Linker")
    print("="*60)

    linker = GeographicLinker(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # Create geographic links
        # Try multiple thresholds:
        # - 1km for very close matches (likely same place or within same area)
        # - 5km for nearby places (settlements in townships, etc.)
        # - 10km for regional context

        linker.create_geographic_links(
            distance_threshold=10.0,
            min_confidence=0.5,
            batch_size=100
        )

        # Create SAME_AS for high confidence matches
        linker.create_high_confidence_same_as_links(confidence_threshold=0.85)

        # Print statistics
        linker.print_statistics()

        print("\n✓ Geographic linking complete!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise

    finally:
        linker.close()


if __name__ == '__main__':
    main()
