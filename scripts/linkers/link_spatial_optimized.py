#!/usr/bin/env python3
"""
Optimized spatial linking for WikidataPlace → Place at global scale.

Key optimizations:
1. Bounding box pre-filter (lat/lon ranges) before expensive point.distance()
2. Limit to top 5 nearest candidates per WikidataPlace
3. Smaller batch sizes (1000) for better progress tracking
4. Skip WikidataPlace nodes already linked via SAME_AS
5. Country-specific processing with adaptive strategies
6. Focus on high-value matches (confidence ≥0.7)

Target: <0.1 sec per place → ~320 hours for 11.5M places
"""

from neo4j import GraphDatabase
from tqdm import tqdm
import time
import math
import os


class OptimizedSpatialLinker:
    def __init__(self, uri=None, user=None, password=None):
        # Use environment variables if not provided
        uri = uri or os.getenv('NEO4J_URI', 'bolt://localhost:7687')
        user = user or os.getenv('NEO4J_USER', 'neo4j')
        password = password or os.getenv('NEO4J_PASSWORD')
        print(f"Connecting to {uri}...")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def haversine_box(self, lat: float, lon: float, distance_km: float = 10.0):
        """
        Calculate bounding box for haversine distance.

        Returns: (min_lat, max_lat, min_lon, max_lon)
        """
        # Earth radius in km
        R = 6371.0

        # Latitude range (simpler, same at all longitudes)
        lat_delta = (distance_km / R) * (180 / math.pi)

        # Longitude range (varies by latitude)
        lon_delta = (distance_km / (R * math.cos(math.radians(lat)))) * (180 / math.pi)

        return (
            max(-90, lat - lat_delta),
            min(90, lat + lat_delta),
            lon - lon_delta,
            lon + lon_delta
        )

    def get_unlinked_places_by_country(self, country_qid: str, limit: int = 10000):
        """
        Get batch of unlinked WikidataPlace nodes for a country.

        Only returns places NOT already linked via SAME_AS.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (wp:WikidataPlace)
                WHERE wp.countryQid = $countryQid
                  AND wp.latitude IS NOT NULL
                  AND wp.longitude IS NOT NULL
                  AND NOT EXISTS((wp)-[:SAME_AS]->())
                RETURN wp.qid AS qid,
                       wp.name AS name,
                       wp.latitude AS lat,
                       wp.longitude AS lon,
                       wp.instanceOfQid AS instanceType
                LIMIT $limit
            """, countryQid=country_qid, limit=limit)

            return [dict(record) for record in result]

    def find_nearby_with_bbox(self, lat: float, lon: float,
                              distance_km: float = 10.0,
                              limit: int = 5):
        """
        Find nearby Place nodes using bounding box pre-filter.

        Returns up to 'limit' nearest matches within distance_km.
        """
        # Calculate bounding box
        min_lat, max_lat, min_lon, max_lon = self.haversine_box(lat, lon, distance_km)

        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Place)
                WHERE p.geonameId IS NOT NULL
                  AND p.latitude >= $min_lat AND p.latitude <= $max_lat
                  AND p.longitude >= $min_lon AND p.longitude <= $max_lon
                WITH p,
                     point.distance(p.location, point({latitude: $lat, longitude: $lon})) / 1000.0 AS distance_km
                WHERE distance_km <= $max_distance
                RETURN p.geonameId AS geonameId,
                       p.name AS name,
                       p.latitude AS lat,
                       p.longitude AS lon,
                       p.featureClass AS featureClass,
                       p.featureCode AS featureCode,
                       p.population AS population,
                       distance_km
                ORDER BY distance_km ASC
                LIMIT $limit
            """,
                lat=lat,
                lon=lon,
                min_lat=min_lat,
                max_lat=max_lat,
                min_lon=min_lon,
                max_lon=max_lon,
                max_distance=distance_km,
                limit=limit
            )

            return [dict(record) for record in result]

    def calculate_confidence(self, wikidata_place: dict, geonames_place: dict,
                            distance_km: float) -> float:
        """
        Calculate confidence score (proven formula from Canadian LOD).

        Returns: 0.0-1.0
        """
        # Distance component
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
            # Word overlap
            wd_words = set(wd_name.split())
            gn_words = set(gn_name.split())
            overlap = len(wd_words & gn_words)
            if overlap > 0:
                name_score = 0.5 * (overlap / max(len(wd_words), len(gn_words)))
            else:
                name_score = 0.0

        # Entity type (simplified - 70 for both since we're focusing on matches)
        type_score = 0.7

        # Weighted combination: 50% name, 30% distance, 20% type
        confidence = (distance_score * 0.30) + (name_score * 0.50) + (type_score * 0.20)

        return min(confidence, 1.0)

    def create_links_batch(self, links: list):
        """Create batch of spatial relationships."""
        if not links:
            return

        with self.driver.session() as session:
            # Separate by type
            same_as = [l for l in links if l['relType'] == 'SAME_AS']
            near = [l for l in links if l['relType'] == 'NEAR']
            located_in = [l for l in links if l['relType'] == 'LOCATED_IN']

            # Create SAME_AS
            if same_as:
                session.run("""
                    UNWIND $links AS link
                    MATCH (wp:WikidataPlace {qid: link.wikidataQid})
                    MATCH (p:Place {geonameId: link.geonameId})
                    MERGE (wp)-[r:SAME_AS]->(p)
                    SET r.distance_km = link.distance_km,
                        r.confidence = link.confidence,
                        r.evidence = 'spatial_proximity',
                        r.linkedDate = datetime()
                """, links=same_as)

            # Create NEAR
            if near:
                session.run("""
                    UNWIND $links AS link
                    MATCH (wp:WikidataPlace {qid: link.wikidataQid})
                    MATCH (p:Place {geonameId: link.geonameId})
                    MERGE (wp)-[r:NEAR]->(p)
                    SET r.distance_km = link.distance_km,
                        r.confidence = link.confidence,
                        r.matchMethod = 'spatial_proximity',
                        r.linkedDate = datetime()
                """, links=near)

            # Create LOCATED_IN
            if located_in:
                session.run("""
                    UNWIND $links AS link
                    MATCH (wp:WikidataPlace {qid: link.wikidataQid})
                    MATCH (p:Place {geonameId: link.geonameId})
                    MERGE (wp)-[r:LOCATED_IN]->(p)
                    SET r.distance_km = link.distance_km,
                        r.confidence = link.confidence,
                        r.matchMethod = 'spatial_proximity',
                        r.linkedDate = datetime()
                """, links=located_in)

    def link_country_batch(self, country_qid: str, batch_size: int = 1000,
                          min_confidence: float = 0.7):
        """
        Link one batch of WikidataPlace nodes for a country.

        Returns: (links_created, places_processed)
        """
        places = self.get_unlinked_places_by_country(country_qid, limit=batch_size)

        if not places:
            return 0, 0

        links_batch = []

        for wp in places:
            # Find up to 5 nearest places
            nearby = self.find_nearby_with_bbox(
                wp['lat'],
                wp['lon'],
                distance_km=10.0,
                limit=5
            )

            if not nearby:
                continue

            # Calculate confidence for best match only
            best_match = nearby[0]
            confidence = self.calculate_confidence(wp, best_match, best_match['distance_km'])

            if confidence >= min_confidence:
                # Determine relationship type
                if confidence >= 0.85 and best_match['distance_km'] <= 1.0:
                    rel_type = 'SAME_AS'
                elif best_match['distance_km'] <= 5.0:
                    rel_type = 'NEAR'
                else:
                    rel_type = 'LOCATED_IN'

                links_batch.append({
                    'wikidataQid': wp['qid'],
                    'geonameId': best_match['geonameId'],
                    'distance_km': round(best_match['distance_km'], 3),
                    'confidence': round(confidence, 3),
                    'relType': rel_type
                })

        # Create links
        self.create_links_batch(links_batch)

        return len(links_batch), len(places)

    def get_countries_with_unlinked_counts(self):
        """Get countries ordered by unlinked place count (smallest first for faster initial results)."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (wp:WikidataPlace)
                WHERE wp.countryQid IS NOT NULL
                  AND wp.latitude IS NOT NULL
                  AND wp.longitude IS NOT NULL
                  AND NOT EXISTS((wp)-[:SAME_AS]->())
                WITH wp.countryQid AS country, count(*) AS count
                RETURN country, count
                ORDER BY count ASC
            """)
            return [(r['country'], r['count']) for r in result]

    def link_all_optimized(self, batch_size: int = 1000,
                          min_confidence: float = 0.7):
        """
        Link all unlinked WikidataPlace nodes with optimized spatial queries.
        """
        print("\n" + "="*60)
        print("OPTIMIZED SPATIAL LINKING")
        print("="*60)
        print(f"Batch size: {batch_size:,}")
        print(f"Minimum confidence: {min_confidence}")
        print(f"Max distance: 10km")
        print(f"Candidates per place: 5\n")

        countries = self.get_countries_with_unlinked_counts()
        print(f"Found {len(countries)} countries with unlinked places")

        total_links = 0
        total_processed = 0
        start_time = time.time()

        for country_qid, count in tqdm(countries, desc="Countries"):
            print(f"\n{country_qid}: {count:,} unlinked places")

            # Process country in batches
            country_links = 0
            country_processed = 0

            while True:
                links, processed = self.link_country_batch(
                    country_qid,
                    batch_size=batch_size,
                    min_confidence=min_confidence
                )

                country_links += links
                country_processed += processed
                total_links += links
                total_processed += processed

                if processed < batch_size:
                    # Finished this country
                    break

            elapsed = time.time() - start_time
            rate = total_processed / elapsed if elapsed > 0 else 0

            print(f"  ✓ Created {country_links:,} links from {country_processed:,} places")
            print(f"  Overall: {total_links:,} links, {total_processed:,} places, {rate:.1f} places/sec")

        elapsed = time.time() - start_time
        print(f"\n✓ Total: {total_links:,} links created")
        print(f"  Processed: {total_processed:,} places")
        print(f"  Time: {elapsed/3600:.1f} hours")
        print(f"  Rate: {total_processed/elapsed:.1f} places/sec")


def main():
    """Main execution."""
    print("="*60)
    print("Optimized Spatial Linker (WikidataPlace → Place)")
    print("="*60)

    linker = OptimizedSpatialLinker()

    try:
        linker.link_all_optimized(
            batch_size=1000,
            min_confidence=0.7
        )

        print("\n✓ Optimized spatial linking complete!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        linker.close()


if __name__ == '__main__':
    main()
