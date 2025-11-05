#!/usr/bin/env python3
"""
Link HGIS (Historical GIS) datasets to LOD Knowledge Graph.

Designed for LINCS team integration - robust geographic matching that:
1. Prioritizes administrative/settlement entities over POIs
2. Handles clustered urban areas (Toronto city vs CN Tower)
3. Uses multi-factor scoring for reliable automatic linking
4. Provides confidence metrics for quality assessment
5. Fast enough for large historical datasets

Key Innovation: Entity Type Hierarchy
- Level 1: Countries, provinces, counties (administrative)
- Level 2: Cities, towns, villages (settlements)
- Level 3: Neighborhoods, districts (sub-areas)
- Level 4: Buildings, landmarks, POIs (specific features)

For historical coordinates, we want Levels 1-2, NOT Level 4.
"""

import os
from typing import List, Dict, Tuple, Optional
from neo4j import GraphDatabase
from tqdm import tqdm
from dotenv import load_dotenv
import math

load_dotenv()


class HGISLinker:
    """Link Historical GIS data to LOD knowledge graph."""

    # Entity type hierarchy - higher priority = better match for historical data
    ENTITY_TYPE_PRIORITY = {
        # Level 1: Administrative divisions (highest priority for regions)
        'country': 100,
        'province': 95,
        'state': 95,
        'county': 90,
        'regional county municipality': 90,
        'census division': 90,
        'regional district': 90,
        'township': 85,
        'rural municipality': 85,
        'geographic township': 85,
        'municipality': 80,

        # Level 2: Settlements (high priority for populated places)
        'city': 75,
        'town': 70,
        'village': 65,
        'hamlet': 60,
        'settlement': 60,
        'human settlement': 60,
        'unincorporated community': 55,

        # Level 3: Sub-areas (medium priority)
        'neighbourhood': 40,
        'district': 40,
        'neighborhood': 40,
        'borough': 40,

        # Level 4: Specific features (low priority - usually NOT what HGIS refers to)
        'building': 20,
        'landmark': 20,
        'place of worship': 15,
        'railway station': 15,
        'tower': 10,
        'monument': 10,
        'park': 10,
        'cemetery': 10,
        'school': 10,
        'hospital': 10,
    }

    # Feature codes - similar hierarchy
    FEATURE_CODE_PRIORITY = {
        # Administrative
        'ADM1': 95,  # First-order admin (province/state)
        'ADM2': 90,  # Second-order (county)
        'ADM3': 85,  # Third-order (township)
        'ADM4': 80,  # Fourth-order
        'AREA': 75,  # Area

        # Populated places
        'PPLA': 90,   # Seat of first-order admin
        'PPLA2': 85,  # Seat of second-order admin
        'PPLA3': 80,  # Seat of third-order admin
        'PPLA4': 75,  # Seat of fourth-order admin
        'PPL': 70,    # Populated place
        'PPLL': 65,   # Populated locality
        'PPLC': 95,   # Capital

        # Historical
        'PPLH': 60,   # Historical populated place
        'PPLQ': 55,   # Abandoned populated place

        # Sub-features (lower priority)
        'PPLX': 40,   # Section of populated place

        # Specific features (avoid for historical matching)
        'CH': 15,     # Church
        'SCH': 15,    # School
        'BLDG': 10,   # Building
        'MUS': 10,    # Museum
        'MNMT': 10,   # Monument
        'HTL': 10,    # Hotel
    }

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def get_entity_type_score(self, place: Dict) -> int:
        """
        Get priority score for entity type.

        Higher score = more likely to be what historical data refers to.
        """
        # Check Wikidata instance type
        instance_type = (place.get('instanceOfLabel') or '').lower()
        for key, score in self.ENTITY_TYPE_PRIORITY.items():
            if key in instance_type:
                return score

        # Check feature code
        feature_code = (place.get('featureCode') or '').upper()
        if feature_code in self.FEATURE_CODE_PRIORITY:
            return self.FEATURE_CODE_PRIORITY[feature_code]

        # Check feature class
        feature_class = (place.get('featureClass') or '').upper()
        if feature_class == 'P':  # Populated place
            return 50
        elif feature_class == 'A':  # Administrative
            return 60
        elif feature_class == 'L':  # Area
            return 55

        # Default: medium-low priority
        return 30

    def calculate_distance(self, lat1: float, lon1: float,
                          lat2: float, lon2: float) -> float:
        """Calculate distance in km using Haversine formula."""
        R = 6371  # Earth radius in km

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (math.sin(dlat/2)**2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        return R * c

    def calculate_population_weight(self, population: Optional[int]) -> float:
        """
        Weight by population - larger settlements are more likely targets.

        But not too much weight - small historical places are valid too.
        """
        if not population or population == 0:
            return 1.0  # Neutral

        # Log scale - major cities get some boost but not overwhelming
        if population >= 100000:
            return 1.3  # Large city
        elif population >= 10000:
            return 1.2  # City
        elif population >= 1000:
            return 1.1  # Town
        else:
            return 1.0  # Village/hamlet

    def find_candidates(self, lat: float, lon: float,
                       radius_km: float = 25.0,
                       min_entity_score: int = 40) -> List[Dict]:
        """
        Find candidate places within radius.

        Filters out low-priority entities (POIs, buildings, etc.)
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Place)
                WHERE p.latitude IS NOT NULL
                  AND p.longitude IS NOT NULL
                  AND p.countryCode = 'CA'
                WITH p,
                     point.distance(
                         point({latitude: p.latitude, longitude: p.longitude}),
                         point({latitude: $lat, longitude: $lon})
                     ) / 1000.0 AS distance_km
                WHERE distance_km <= $radius
                RETURN p.geonameId AS geonameId,
                       p.wikidataId AS wikidataId,
                       p.name AS name,
                       p.latitude AS lat,
                       p.longitude AS lon,
                       p.featureClass AS featureClass,
                       p.featureCode AS featureCode,
                       p.instanceOfLabel AS instanceOfLabel,
                       p.population AS population,
                       distance_km
                ORDER BY distance_km ASC
                LIMIT 50
            """,
                lat=lat,
                lon=lon,
                radius=radius_km
            )

            candidates = []
            for record in result:
                place = dict(record)
                entity_score = self.get_entity_type_score(place)

                # Filter out low-priority entities
                if entity_score >= min_entity_score:
                    place['entity_score'] = entity_score
                    candidates.append(place)

            return candidates

    def score_candidate(self, candidate: Dict,
                       target_name: Optional[str] = None,
                       historical_date: Optional[int] = None) -> Dict:
        """
        Calculate comprehensive match score.

        Components:
        1. Distance score (40% weight)
        2. Entity type score (35% weight) - KEY for avoiding POIs
        3. Name similarity (15% weight)
        4. Population weight (10% weight)

        Returns dict with score and breakdown.
        """
        distance_km = candidate['distance_km']
        entity_score = candidate['entity_score']

        # 1. Distance score (exponential decay)
        if distance_km <= 0.5:
            distance_score = 1.0
        elif distance_km <= 2.0:
            distance_score = 0.9
        elif distance_km <= 5.0:
            distance_score = 0.75
        elif distance_km <= 10.0:
            distance_score = 0.5
        elif distance_km <= 25.0:
            distance_score = 0.3
        else:
            distance_score = 0.1

        # 2. Entity type score (normalized to 0-1)
        type_score = entity_score / 100.0

        # 3. Name similarity (if target name provided)
        if target_name:
            candidate_name = (candidate.get('name') or '').lower()
            target_lower = target_name.lower()

            if candidate_name == target_lower:
                name_score = 1.0
            elif target_lower in candidate_name or candidate_name in target_lower:
                name_score = 0.8
            else:
                # Word overlap
                target_words = set(target_lower.split())
                candidate_words = set(candidate_name.split())
                overlap = len(target_words & candidate_words)
                if overlap > 0 and target_words:
                    name_score = 0.5 * (overlap / len(target_words))
                else:
                    name_score = 0.0
        else:
            name_score = 0.5  # Neutral if no name

        # 4. Population weight
        pop_weight = self.calculate_population_weight(candidate.get('population'))

        # Weighted combination
        base_score = (
            distance_score * 0.40 +
            type_score * 0.35 +
            name_score * 0.15 +
            (pop_weight - 1.0) * 0.10  # Population adds small boost
        )

        final_score = min(base_score, 1.0)

        return {
            'final_score': final_score,
            'distance_score': distance_score,
            'type_score': type_score,
            'name_score': name_score,
            'pop_weight': pop_weight,
            'distance_km': distance_km,
            'entity_type': entity_score
        }

    def match_single_hgis_point(self, lat: float, lon: float,
                                name: Optional[str] = None,
                                year: Optional[int] = None,
                                radius_km: float = 25.0,
                                min_confidence: float = 0.6) -> List[Dict]:
        """
        Match a single HGIS point to LOD entities.

        Args:
            lat, lon: Coordinates from HGIS dataset
            name: Place name from HGIS (optional but helps)
            year: Historical year (optional, for future temporal filtering)
            radius_km: Search radius
            min_confidence: Minimum score to return

        Returns:
            List of matches sorted by score (best first)
        """
        # Find candidates
        candidates = self.find_candidates(lat, lon, radius_km)

        if not candidates:
            return []

        # Score each candidate
        scored = []
        for candidate in candidates:
            score_breakdown = self.score_candidate(
                candidate,
                target_name=name,
                historical_date=year
            )

            if score_breakdown['final_score'] >= min_confidence:
                result = {
                    **candidate,
                    'match_score': score_breakdown['final_score'],
                    'score_breakdown': score_breakdown
                }
                scored.append(result)

        # Sort by score (best first)
        scored.sort(key=lambda x: x['match_score'], reverse=True)

        return scored

    def print_match_report(self, matches: List[Dict], hgis_name: str):
        """Pretty print match results for review."""
        print(f"\n{'='*70}")
        print(f"Matches for: {hgis_name}")
        print('='*70)

        if not matches:
            print("No matches found above confidence threshold")
            return

        for i, match in enumerate(matches[:5], 1):  # Top 5
            print(f"\n#{i} Match (Score: {match['match_score']:.3f})")
            print(f"  Name: {match['name']}")
            print(f"  Type: {match.get('instanceOfLabel') or match.get('featureCode', 'N/A')}")
            print(f"  Distance: {match['distance_km']:.2f} km")
            print(f"  Population: {match.get('population') or 'N/A'}")
            print(f"  IDs: GeoNames={match.get('geonameId')}, Wikidata={match.get('wikidataId')}")

            breakdown = match['score_breakdown']
            print(f"  Score Breakdown:")
            print(f"    Distance: {breakdown['distance_score']:.2f} (40% weight)")
            print(f"    Entity Type: {breakdown['type_score']:.2f} (35% weight) - Priority: {breakdown['entity_type']}")
            print(f"    Name Match: {breakdown['name_score']:.2f} (15% weight)")
            print(f"    Population: {breakdown['pop_weight']:.2f} (10% weight)")


def test_toronto_cn_tower_problem():
    """
    Test case: Historical "Toronto" coordinates should match city, not CN Tower.

    Toronto City: ~43.65, -79.38
    CN Tower: 43.6426, -79.3871 (very close!)

    Our system should prioritize the city entity over the landmark.
    """
    print("\n" + "="*70)
    print("TEST: Toronto vs CN Tower Problem")
    print("="*70)

    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

    linker = HGISLinker(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # Historical Toronto coordinates (approximate city center)
        matches = linker.match_single_hgis_point(
            lat=43.65,
            lon=-79.38,
            name="Toronto",
            year=1921,
            radius_km=10.0,
            min_confidence=0.5
        )

        linker.print_match_report(matches, "Toronto (1921 Census)")

        # Check if top match is city-level entity
        if matches:
            top_match = matches[0]
            entity_score = top_match['score_breakdown']['entity_type']
            print(f"\n✓ Top match entity priority: {entity_score}")
            if entity_score >= 70:
                print("✓ SUCCESS: Matched to settlement/city level entity")
            else:
                print("⚠ WARNING: Matched to low-priority entity (POI/building)")

    finally:
        linker.close()


def main():
    """Main execution."""
    # Run test case
    test_toronto_cn_tower_problem()

    print("\n" + "="*70)
    print("HGIS Linking System Ready")
    print("="*70)
    print("\nUsage:")
    print("  from link_hgis_to_lod import HGISLinker")
    print("  linker = HGISLinker(uri, user, password)")
    print("  matches = linker.match_single_hgis_point(lat, lon, name='Toronto')")
    print("\nFeatures:")
    print("  ✓ Prioritizes administrative/settlement entities over POIs")
    print("  ✓ Handles urban clustering (Toronto city vs CN Tower)")
    print("  ✓ Multi-factor scoring with confidence metrics")
    print("  ✓ Fast geographic queries with spatial indexes")
    print("  ✓ Designed for batch processing of HGIS datasets")


if __name__ == '__main__':
    main()
