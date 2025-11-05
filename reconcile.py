#!/usr/bin/env python3
"""
NER Reconciliation Functions for GeoNames + Wikidata Knowledge Graph

Provides various matching strategies for reconciling Named Entity Recognition
results against the LOD knowledge graph.
"""

import os
from typing import Dict, List, Optional, Tuple
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()


class NERReconciler:
    """Reconcile NER entities against the knowledge graph."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def exact_match(self, name: str, country_code: Optional[str] = None) -> List[Dict]:
        """
        Exact name match reconciliation.

        Args:
            name: Place name to match
            country_code: Optional ISO country code filter (e.g., 'CA')

        Returns:
            List of matching places with metadata
        """
        with self.driver.session() as session:
            query = """
            MATCH (p:Place)
            WHERE p.name = $name
              OR $name IN p.alternateNames
              OR $name IN p.wikidataAlternateNames
            """

            if country_code:
                query += " AND p.countryCode = $countryCode"

            query += """
            RETURN p.geonameId AS geonameId,
                   p.wikidataId AS wikidataId,
                   p.name AS name,
                   p.countryCode AS country,
                   p.featureClass AS featureClass,
                   p.featureCode AS featureCode,
                   p.population AS population,
                   p.latitude AS latitude,
                   p.longitude AS longitude,
                   p.wikipediaUrl AS wikipedia,
                   p.alternateNames AS alternateNames,
                   1.0 AS confidence
            ORDER BY p.population DESC NULLS LAST
            LIMIT 20
            """

            result = session.run(query, name=name, countryCode=country_code)
            return [dict(record) for record in result]

    def fuzzy_match(self, name: str, country_code: Optional[str] = None,
                    max_distance: int = 2) -> List[Dict]:
        """
        Fuzzy name match using Levenshtein distance (requires APOC).

        Args:
            name: Place name to match
            country_code: Optional ISO country code filter
            max_distance: Maximum edit distance (default 2)

        Returns:
            List of matching places with confidence scores
        """
        with self.driver.session() as session:
            query = """
            MATCH (p:Place)
            WHERE apoc.text.levenshteinDistance(toLower(p.name), toLower($name)) <= $maxDistance
            """

            if country_code:
                query += " AND p.countryCode = $countryCode"

            query += """
            WITH p,
                 apoc.text.levenshteinDistance(toLower(p.name), toLower($name)) AS distance
            RETURN p.geonameId AS geonameId,
                   p.wikidataId AS wikidataId,
                   p.name AS name,
                   p.countryCode AS country,
                   p.featureClass AS featureClass,
                   p.featureCode AS featureCode,
                   p.population AS population,
                   p.latitude AS latitude,
                   p.longitude AS longitude,
                   p.wikipediaUrl AS wikipedia,
                   distance,
                   (1.0 - (toFloat(distance) / size($name))) AS confidence
            ORDER BY distance ASC, p.population DESC NULLS LAST
            LIMIT 20
            """

            result = session.run(query, name=name, countryCode=country_code,
                               maxDistance=max_distance)
            return [dict(record) for record in result]

    def geographic_context_match(self, name: str, lat: float, lon: float,
                                 radius_km: float = 50.0) -> List[Dict]:
        """
        Match places by name within geographic radius.

        Useful when you have approximate coordinates from geocoding or context.

        Args:
            name: Place name to match
            lat: Latitude
            lon: Longitude
            radius_km: Search radius in kilometers

        Returns:
            List of matching places sorted by distance
        """
        with self.driver.session() as session:
            query = """
            MATCH (p:Place)
            WHERE p.latitude IS NOT NULL AND p.longitude IS NOT NULL
              AND (p.name = $name OR $name IN p.alternateNames)
            WITH p,
                 point.distance(
                   point({latitude: p.latitude, longitude: p.longitude}),
                   point({latitude: $lat, longitude: $lon})
                 ) / 1000.0 AS distance_km
            WHERE distance_km <= $radius_km
            RETURN p.geonameId AS geonameId,
                   p.wikidataId AS wikidataId,
                   p.name AS name,
                   p.countryCode AS country,
                   p.latitude AS latitude,
                   p.longitude AS longitude,
                   p.population AS population,
                   p.wikipediaUrl AS wikipedia,
                   distance_km,
                   (1.0 - (distance_km / $radius_km)) AS confidence
            ORDER BY distance_km ASC
            LIMIT 20
            """

            result = session.run(query, name=name, lat=lat, lon=lon,
                               radius_km=radius_km)
            return [dict(record) for record in result]

    def administrative_context_match(self, city_name: str, admin_name: str,
                                     country_code: str = 'CA') -> List[Dict]:
        """
        Match place with administrative context (e.g., "Regina, Saskatchewan").

        Args:
            city_name: Name of the city/town
            admin_name: Name of the province/state/county
            country_code: Country code (default 'CA')

        Returns:
            List of matching places
        """
        with self.driver.session() as session:
            # Try matching admin name against admin division names
            # Note: This requires admin division names to be populated
            query = """
            MATCH (p:Place)-[:LOCATED_IN_ADMIN1]->(a:AdminDivision)
            WHERE (p.name = $cityName OR $cityName IN p.alternateNames)
              AND p.countryCode = $countryCode
              AND (a.name = $adminName OR a.code CONTAINS $adminName)
            RETURN p.geonameId AS geonameId,
                   p.wikidataId AS wikidataId,
                   p.name AS name,
                   p.countryCode AS country,
                   a.name AS adminDivision,
                   p.latitude AS latitude,
                   p.longitude AS longitude,
                   p.population AS population,
                   p.wikipediaUrl AS wikipedia,
                   1.0 AS confidence
            ORDER BY p.population DESC NULLS LAST
            LIMIT 20
            """

            result = session.run(query, cityName=city_name, adminName=admin_name,
                               countryCode=country_code)
            return [dict(record) for record in result]

    def historical_name_match(self, name: str, country_code: str = 'CA') -> List[Dict]:
        """
        Match historical/former place names.

        Prioritizes places with dissolution dates or marked as historical.

        Args:
            name: Historical place name
            country_code: Country code (default 'CA')

        Returns:
            List of historical places
        """
        with self.driver.session() as session:
            query = """
            MATCH (p:Place)
            WHERE p.countryCode = $countryCode
              AND (p.name = $name OR $name IN p.alternateNames
                   OR $name IN p.wikidataAlternateNames)
              AND (p.featureCode IN ['PPLH', 'PPLQ', 'PPLW']
                   OR p.dissolvedDate IS NOT NULL)
            RETURN p.geonameId AS geonameId,
                   p.wikidataId AS wikidataId,
                   p.name AS name,
                   p.countryCode AS country,
                   p.featureCode AS featureCode,
                   p.dissolvedDate AS dissolvedDate,
                   p.inceptionDate AS inceptionDate,
                   p.latitude AS latitude,
                   p.longitude AS longitude,
                   p.wikipediaUrl AS wikipedia,
                   p.wikidataDescription AS description,
                   1.0 AS confidence
            ORDER BY p.dissolvedDate DESC NULLS LAST
            LIMIT 20
            """

            result = session.run(query, name=name, countryCode=country_code)
            return [dict(record) for record in result]

    def reconcile_smart(self, name: str,
                       context: Optional[Dict] = None,
                       threshold: float = 0.7) -> List[Dict]:
        """
        Smart reconciliation combining multiple strategies.

        Tries multiple matching approaches and ranks results by confidence.

        Args:
            name: Place name to reconcile
            context: Optional dict with keys:
                - country: ISO country code
                - admin1: Province/state name
                - lat, lon: Coordinates
                - radius_km: Search radius
                - historical: Boolean flag
            threshold: Minimum confidence score (0.0-1.0)

        Returns:
            Ranked list of matches with confidence scores
        """
        context = context or {}
        all_matches = []
        seen_ids = set()

        # Strategy 1: Exact match
        exact_results = self.exact_match(
            name,
            country_code=context.get('country')
        )
        for result in exact_results:
            result_id = (result.get('geonameId'), result.get('wikidataId'))
            if result_id not in seen_ids:
                result['match_strategy'] = 'exact'
                all_matches.append(result)
                seen_ids.add(result_id)

        # Strategy 2: Admin context if provided
        if context.get('admin1'):
            admin_results = self.administrative_context_match(
                name,
                context['admin1'],
                country_code=context.get('country', 'CA')
            )
            for result in admin_results:
                result_id = (result.get('geonameId'), result.get('wikidataId'))
                if result_id not in seen_ids:
                    result['match_strategy'] = 'administrative'
                    result['confidence'] = 0.95
                    all_matches.append(result)
                    seen_ids.add(result_id)

        # Strategy 3: Geographic context if coordinates provided
        if context.get('lat') and context.get('lon'):
            geo_results = self.geographic_context_match(
                name,
                context['lat'],
                context['lon'],
                radius_km=context.get('radius_km', 50.0)
            )
            for result in geo_results:
                result_id = (result.get('geonameId'), result.get('wikidataId'))
                if result_id not in seen_ids:
                    result['match_strategy'] = 'geographic'
                    all_matches.append(result)
                    seen_ids.add(result_id)

        # Strategy 4: Historical if flagged
        if context.get('historical'):
            hist_results = self.historical_name_match(
                name,
                country_code=context.get('country', 'CA')
            )
            for result in hist_results:
                result_id = (result.get('geonameId'), result.get('wikidataId'))
                if result_id not in seen_ids:
                    result['match_strategy'] = 'historical'
                    result['confidence'] = 0.9
                    all_matches.append(result)
                    seen_ids.add(result_id)

        # Strategy 5: Fuzzy match as fallback
        if len(all_matches) < 5:
            try:
                fuzzy_results = self.fuzzy_match(
                    name,
                    country_code=context.get('country')
                )
                for result in fuzzy_results:
                    result_id = (result.get('geonameId'), result.get('wikidataId'))
                    if result_id not in seen_ids:
                        result['match_strategy'] = 'fuzzy'
                        all_matches.append(result)
                        seen_ids.add(result_id)
            except:
                # APOC might not be available
                pass

        # Filter by threshold and sort by confidence
        filtered = [m for m in all_matches if m.get('confidence', 0) >= threshold]
        filtered.sort(key=lambda x: x.get('confidence', 0), reverse=True)

        return filtered[:10]  # Top 10 results


def main():
    """Example usage."""

    NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password')

    reconciler = NERReconciler(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # Example 1: Simple exact match
        print("="*60)
        print("Example 1: Exact Match - 'Regina'")
        print("="*60)
        results = reconciler.exact_match('Regina', country_code='CA')
        for r in results[:3]:
            print(f"  {r['name']} ({r['country']}) - Pop: {r.get('population', 'N/A')}")
            print(f"    GeoNames: {r['geonameId']}, Wikidata: {r.get('wikidataId')}")

        # Example 2: Administrative context
        print("\n" + "="*60)
        print("Example 2: Admin Context - 'Regina, Saskatchewan'")
        print("="*60)
        results = reconciler.administrative_context_match('Regina', 'Saskatchewan')
        for r in results[:3]:
            print(f"  {r['name']} in {r.get('adminDivision', 'N/A')}")
            print(f"    Confidence: {r['confidence']:.2f}")

        # Example 3: Historical place
        print("\n" + "="*60)
        print("Example 3: Historical Place - 'Maitland'")
        print("="*60)
        results = reconciler.exact_match('Maitland', country_code='CA')
        for r in results:
            print(f"  {r['name']} ({r['country']}) - {r['featureCode']}")
            if r.get('wikipediaUrl'):
                print(f"    Wikipedia: {r['wikipediaUrl']}")

        # Example 4: Smart reconciliation
        print("\n" + "="*60)
        print("Example 4: Smart Reconcile - 'Maitland' with context")
        print("="*60)
        results = reconciler.reconcile_smart(
            'Maitland',
            context={'country': 'CA', 'admin1': 'Nova Scotia'}
        )
        for r in results[:3]:
            print(f"  {r['name']} - {r['match_strategy']} (confidence: {r['confidence']:.2f})")

    finally:
        reconciler.close()


if __name__ == '__main__':
    main()
