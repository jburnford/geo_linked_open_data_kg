#!/usr/bin/env python3
"""
Parse LINCS Historical Canadians RDF (Turtle format) and convert to Neo4j-friendly JSON.

Dataset: 186MB, 25,596 persons, 6,016 places
RDF Structure (CIDOC-CRM):
- crm:E21_Person: Individual persons (identified by VIAF, Wikidata, or LINCS IDs)
- crm:E67_Birth: Birth events (with places via GeoNames, dates, parents)
- crm:E69_Death: Death events (with places via GeoNames, dates)
- crm:E52_Time-Span: Date ranges
- crm:E53_Place: Places (with GeoNames links)
- crm:E85_Joining: Marriage events
- owl:sameAs: Links to Wikidata Person nodes
"""

import json
import re
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL
from typing import Dict, List, Set, Optional
from tqdm import tqdm
from collections import defaultdict

# Define namespaces
CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
LINCS = Namespace("http://id.lincsproject.ca/")
VIAF = Namespace("http://viaf.org/viaf/")
WIKIDATA = Namespace("http://www.wikidata.org/entity/")
GEONAMES = Namespace("https://sws.geonames.org/")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")

# CIDOC-CRM uses hyphens in property/class names - define URIRefs directly
CRM_E21_Person = URIRef("http://www.cidoc-crm.org/cidoc-crm/E21_Person")
CRM_E67_Birth = URIRef("http://www.cidoc-crm.org/cidoc-crm/E67_Birth")
CRM_E69_Death = URIRef("http://www.cidoc-crm.org/cidoc-crm/E69_Death")
CRM_E52_TimeSpan = URIRef("http://www.cidoc-crm.org/cidoc-crm/E52_Time-Span")
CRM_E53_Place = URIRef("http://www.cidoc-crm.org/cidoc-crm/E53_Place")
CRM_E85_Joining = URIRef("http://www.cidoc-crm.org/cidoc-crm/E85_Joining")

CRM_P4_has_timespan = URIRef("http://www.cidoc-crm.org/cidoc-crm/P4_has_time-span")
CRM_P7_took_place_at = URIRef("http://www.cidoc-crm.org/cidoc-crm/P7_took_place_at")
CRM_P82_at_some_time_within = URIRef("http://www.cidoc-crm.org/cidoc-crm/P82_at_some_time_within")
CRM_P82a_begin = URIRef("http://www.cidoc-crm.org/cidoc-crm/P82a_begin_of_the_begin")
CRM_P82b_end = URIRef("http://www.cidoc-crm.org/cidoc-crm/P82b_end_of_the_end")
CRM_P89_falls_within = URIRef("http://www.cidoc-crm.org/cidoc-crm/P89_falls_within")
CRM_P96_by_mother = URIRef("http://www.cidoc-crm.org/cidoc-crm/P96_by_mother")
CRM_P97_from_father = URIRef("http://www.cidoc-crm.org/cidoc-crm/P97_from_father")
CRM_P98_brought_into_life = URIRef("http://www.cidoc-crm.org/cidoc-crm/P98_brought_into_life")
CRM_P100_was_death_of = URIRef("http://www.cidoc-crm.org/cidoc-crm/P100_was_death_of")
CRM_P143_joined = URIRef("http://www.cidoc-crm.org/cidoc-crm/P143_joined")
CRM_P168_place_is_defined_by = URIRef("http://www.cidoc-crm.org/cidoc-crm/P168_place_is_defined_by")


def extract_id_from_uri(uri: str, namespace: str) -> Optional[str]:
    """Extract ID from a URI."""
    if namespace in uri:
        # Remove trailing slash and get last part
        return uri.rstrip("/").split("/")[-1]
    return None


def extract_geonames_id(uri: str) -> Optional[int]:
    """Extract numeric GeoNames ID from URL."""
    if "geonames.org" in uri:
        try:
            id_str = uri.rstrip("/").split("/")[-1]
            # Remove non-numeric characters
            id_str = ''.join(c for c in id_str if c.isdigit())
            if id_str:
                return int(id_str)
        except (ValueError, IndexError):
            pass
    return None


def parse_date(date_str: str) -> Optional[str]:
    """Parse various date formats to ISO date string."""
    if not date_str:
        return None

    # Already ISO format
    if re.match(r'^\d{4}-\d{2}-\d{2}', date_str):
        return date_str[:10]  # Return just YYYY-MM-DD

    # Extract year from various formats
    year_match = re.search(r'\b(\d{4})\b', date_str)
    if year_match:
        return year_match.group(1)  # Return just the year

    return date_str  # Return as-is if can't parse


class HistoricalCanadiansParser:
    """Parse LINCS Historical Canadians RDF data."""

    def __init__(self, ttl_file: str):
        self.ttl_file = ttl_file
        self.graph = None
        self.persons = {}
        self.time_spans = {}  # Cache time-span data
        self.places = {}  # Cache place data

    def load_graph(self):
        """Load RDF graph from Turtle file."""
        print(f"Loading RDF from {self.ttl_file}...")
        print("This may take a few minutes for 186MB file...")

        self.graph = Graph()
        self.graph.parse(self.ttl_file, format="turtle")

        print(f"Loaded {len(self.graph):,} triples")

    def cache_time_spans(self):
        """Pre-cache all time-span data for faster lookup."""
        print("\nCaching time-span data...")

        time_span_uris = set(self.graph.subjects(RDF.type, CRM_E52_TimeSpan))

        for ts_uri in tqdm(time_span_uris, desc="Time-spans"):
            time_span = {}

            # Get human-readable date
            for date_val in self.graph.objects(ts_uri, CRM_P82_at_some_time_within):
                time_span['display'] = str(date_val)

            # Get ISO begin date
            for begin_val in self.graph.objects(ts_uri, CRM_P82a_begin):
                time_span['begin'] = str(begin_val)

            # Get ISO end date
            for end_val in self.graph.objects(ts_uri, CRM_P82b_end):
                time_span['end'] = str(end_val)

            self.time_spans[str(ts_uri)] = time_span

        print(f"Cached {len(self.time_spans):,} time-spans")

    def cache_places(self):
        """Pre-cache place data for faster lookup."""
        print("\nCaching place data...")

        place_uris = set(self.graph.subjects(RDF.type, CRM_E53_Place))

        for place_uri in tqdm(place_uris, desc="Places"):
            place = {}

            # Get labels
            labels = list(self.graph.objects(place_uri, RDFS.label))
            if labels:
                place['name'] = str(labels[0])

            # Get GeoNames link (P89_falls_within)
            for geonames_uri in self.graph.objects(place_uri, CRM_P89_falls_within):
                geonames_id = extract_geonames_id(str(geonames_uri))
                if geonames_id:
                    place['geonamesId'] = geonames_id

            # Get coordinates (P168_place_is_defined_by)
            for coords in self.graph.objects(place_uri, CRM_P168_place_is_defined_by):
                coords_str = str(coords)
                # Extract lat/lon from POINT(lon lat) format
                match = re.search(r'POINT\(([-\d.]+)\s+([-\d.]+)\)', coords_str)
                if match:
                    place['longitude'] = float(match.group(1))
                    place['latitude'] = float(match.group(2))

            # Check if this is a Wikidata place
            place_str = str(place_uri)
            if "wikidata.org" in place_str:
                place['wikidataQid'] = extract_id_from_uri(place_str, "wikidata.org")

            self.places[str(place_uri)] = place

        print(f"Cached {len(self.places):,} places")

    def extract_persons(self):
        """Extract all person entities."""
        print("\nExtracting persons...")

        person_uris = set(self.graph.subjects(RDF.type, CRM_E21_Person))
        print(f"Found {len(person_uris):,} persons")

        for person_uri in tqdm(person_uris, desc="Processing persons"):
            person_str = str(person_uri)

            # Determine person ID type
            person_id = None
            id_type = None

            if "viaf.org" in person_str:
                person_id = f"viaf:{extract_id_from_uri(person_str, 'viaf.org')}"
                id_type = "VIAF"
            elif "wikidata.org" in person_str:
                person_id = f"wd:{extract_id_from_uri(person_str, 'wikidata.org')}"
                id_type = "Wikidata"
            elif "lincsproject.ca" in person_str or "id.lincsproject.ca" in person_str:
                lincs_id = person_str.split("/")[-1]
                person_id = f"lincs:{lincs_id}"
                id_type = "LINCS"
            else:
                # Unknown ID type, use full URI
                person_id = person_str
                id_type = "Other"

            # Get labels (names)
            names = []
            for label in self.graph.objects(person_uri, RDFS.label):
                names.append(str(label))

            # Primary name (first label)
            name = names[0] if names else "Unknown"

            # Get Wikidata link via owl:sameAs
            wikidata_qid = None
            for same_as in self.graph.objects(person_uri, OWL.sameAs):
                same_as_str = str(same_as)
                if "wikidata.org" in same_as_str:
                    wikidata_qid = extract_id_from_uri(same_as_str, "wikidata.org")

            # Get VIAF ID if person has owl:sameAs to VIAF
            viaf_id = None
            for same_as in self.graph.objects(person_uri, OWL.sameAs):
                same_as_str = str(same_as)
                if "viaf.org" in same_as_str:
                    viaf_id = extract_id_from_uri(same_as_str, "viaf.org")

            # Initialize person data
            person_data = {
                'personId': person_id,
                'idType': id_type,
                'name': name,
                'alternateNames': names[1:] if len(names) > 1 else [],
                'wikidataQid': wikidata_qid,
                'viafId': viaf_id if id_type != "VIAF" else extract_id_from_uri(person_str, 'viaf.org'),
                'birthEvent': None,
                'deathEvent': None,
                'occupations': [],
                'relationships': []
            }

            self.persons[str(person_uri)] = person_data

        print(f"Extracted {len(self.persons):,} persons")

    def extract_birth_events(self):
        """Extract birth events and link to persons."""
        print("\nExtracting birth events...")

        birth_uris = set(self.graph.subjects(RDF.type, CRM_E67_Birth))
        print(f"Found {len(birth_uris):,} birth events")

        birth_count = 0
        for birth_uri in tqdm(birth_uris, desc="Processing births"):
            # Get person born (P98_brought_into_life)
            person_uri = None
            for p in self.graph.objects(birth_uri, CRM_P98_brought_into_life):
                person_uri = str(p)
                break

            if not person_uri or person_uri not in self.persons:
                continue

            birth_event = {}

            # Get birth place(s) (P7_took_place_at)
            birth_places = []
            for place_uri in self.graph.objects(birth_uri, CRM_P7_took_place_at):
                place_str = str(place_uri)

                # Check if it's a GeoNames URL
                geonames_id = extract_geonames_id(place_str)
                if geonames_id:
                    birth_places.append({
                        'type': 'geonames',
                        'id': geonames_id
                    })
                elif place_str in self.places:
                    # Use cached place data
                    place_data = self.places[place_str].copy()
                    place_data['type'] = 'lincs_place'
                    birth_places.append(place_data)

            if birth_places:
                birth_event['places'] = birth_places

            # Get birth date (P4_has_time-span)
            for ts_uri in self.graph.objects(birth_uri, CRM_P4_has_timespan):
                ts_str = str(ts_uri)
                if ts_str in self.time_spans:
                    ts_data = self.time_spans[ts_str]
                    birth_event['date'] = ts_data.get('display')
                    birth_event['dateBegin'] = ts_data.get('begin')
                    birth_event['dateEnd'] = ts_data.get('end')

            # Get parents
            for mother_uri in self.graph.objects(birth_uri, CRM_P96_by_mother):
                mother_str = str(mother_uri)
                if mother_str in self.persons:
                    birth_event['motherId'] = self.persons[mother_str]['personId']

            for father_uri in self.graph.objects(birth_uri, CRM_P97_from_father):
                father_str = str(father_uri)
                if father_str in self.persons:
                    birth_event['fatherId'] = self.persons[father_str]['personId']

            # Add birth event to person
            if birth_event:
                self.persons[person_uri]['birthEvent'] = birth_event
                birth_count += 1

        print(f"Linked {birth_count:,} birth events to persons")

    def extract_death_events(self):
        """Extract death events and link to persons."""
        print("\nExtracting death events...")

        death_uris = set(self.graph.subjects(RDF.type, CRM_E69_Death))
        print(f"Found {len(death_uris):,} death events")

        death_count = 0
        for death_uri in tqdm(death_uris, desc="Processing deaths"):
            # Get person who died (P100_was_death_of)
            person_uri = None
            for p in self.graph.objects(death_uri, CRM_P100_was_death_of):
                person_uri = str(p)
                break

            if not person_uri or person_uri not in self.persons:
                continue

            death_event = {}

            # Get death place(s) (P7_took_place_at)
            death_places = []
            for place_uri in self.graph.objects(death_uri, CRM_P7_took_place_at):
                place_str = str(place_uri)

                # Check if it's a GeoNames URL
                geonames_id = extract_geonames_id(place_str)
                if geonames_id:
                    death_places.append({
                        'type': 'geonames',
                        'id': geonames_id
                    })
                elif place_str in self.places:
                    # Use cached place data
                    place_data = self.places[place_str].copy()
                    place_data['type'] = 'lincs_place'
                    death_places.append(place_data)

            if death_places:
                death_event['places'] = death_places

            # Get death date (P4_has_time-span)
            for ts_uri in self.graph.objects(death_uri, CRM_P4_has_timespan):
                ts_str = str(ts_uri)
                if ts_str in self.time_spans:
                    ts_data = self.time_spans[ts_str]
                    death_event['date'] = ts_data.get('display')
                    death_event['dateBegin'] = ts_data.get('begin')
                    death_event['dateEnd'] = ts_data.get('end')

            # Add death event to person
            if death_event:
                self.persons[person_uri]['deathEvent'] = death_event
                death_count += 1

        print(f"Linked {death_count:,} death events to persons")

    def extract_marriages(self):
        """Extract marriage events."""
        print("\nExtracting marriage events...")

        marriage_uris = set(self.graph.subjects(RDF.type, CRM_E85_Joining))
        print(f"Found {len(marriage_uris):,} joining events (marriages)")

        marriage_count = 0
        for marriage_uri in tqdm(marriage_uris, desc="Processing marriages"):
            # Get persons joined (P143_joined)
            spouses = []
            for person_uri in self.graph.objects(marriage_uri, CRM_P143_joined):
                person_str = str(person_uri)
                if person_str in self.persons:
                    spouses.append(self.persons[person_str]['personId'])

            if len(spouses) < 2:
                continue

            # Get marriage date
            marriage_date = None
            for ts_uri in self.graph.objects(marriage_uri, CRM_P4_has_timespan):
                ts_str = str(ts_uri)
                if ts_str in self.time_spans:
                    marriage_date = self.time_spans[ts_str].get('display')

            # Add marriage relationship to both spouses
            for person_uri in self.graph.objects(marriage_uri, CRM_P143_joined):
                person_str = str(person_uri)
                if person_str in self.persons:
                    # Add other spouse(s) as relationships
                    for spouse_id in spouses:
                        if spouse_id != self.persons[person_str]['personId']:
                            self.persons[person_str]['relationships'].append({
                                'type': 'spouse',
                                'personId': spouse_id,
                                'date': marriage_date
                            })
                    marriage_count += 1

        print(f"Processed {marriage_count:,} marriage relationships")

    def save_to_json(self, output_file: str):
        """Save parsed data to JSON file."""
        print(f"\nSaving {len(self.persons):,} persons to {output_file}...")

        # Convert persons dict to list
        persons_list = list(self.persons.values())

        # Filter out persons with minimal data (only ID and name, no events)
        persons_with_data = [
            p for p in persons_list
            if p['birthEvent'] or p['deathEvent'] or p['wikidataQid'] or p['relationships']
        ]

        print(f"Persons with biographical data: {len(persons_with_data):,}")

        output = {
            'metadata': {
                'source': 'LINCS Historical Canadians',
                'totalPersons': len(self.persons),
                'personsWithData': len(persons_with_data),
                'rdfTriples': len(self.graph)
            },
            'persons': persons_with_data
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"✓ Saved to {output_file}")

    def print_statistics(self):
        """Print statistics about parsed data."""
        print("\n" + "="*60)
        print("LINCS HISTORICAL CANADIANS - PARSING STATISTICS")
        print("="*60)

        persons_list = list(self.persons.values())

        # Count persons with various attributes
        with_wikidata = sum(1 for p in persons_list if p['wikidataQid'])
        with_viaf = sum(1 for p in persons_list if p['viafId'])
        with_birth = sum(1 for p in persons_list if p['birthEvent'])
        with_death = sum(1 for p in persons_list if p['deathEvent'])
        with_relationships = sum(1 for p in persons_list if p['relationships'])

        # Count GeoNames links
        geonames_birth = 0
        geonames_death = 0
        for p in persons_list:
            if p['birthEvent'] and 'places' in p['birthEvent']:
                geonames_birth += sum(1 for place in p['birthEvent']['places'] if place.get('type') == 'geonames')
            if p['deathEvent'] and 'places' in p['deathEvent']:
                geonames_death += sum(1 for place in p['deathEvent']['places'] if place.get('type') == 'geonames')

        print(f"\nTotal persons: {len(persons_list):,}")
        print(f"Persons with Wikidata QIDs: {with_wikidata:,}")
        print(f"Persons with VIAF IDs: {with_viaf:,}")
        print(f"Persons with birth events: {with_birth:,}")
        print(f"Persons with death events: {with_death:,}")
        print(f"Persons with relationships: {with_relationships:,}")
        print(f"\nBirth places with GeoNames IDs: {geonames_birth:,}")
        print(f"Death places with GeoNames IDs: {geonames_death:,}")

        # Sample persons
        print("\n" + "="*60)
        print("SAMPLE PERSONS")
        print("="*60)

        # Show persons with Wikidata and birth/death data
        sample_count = 0
        for p in persons_list:
            if p['wikidataQid'] and p['birthEvent'] and p['deathEvent'] and sample_count < 3:
                print(f"\n{p['name']} ({p['personId']})")
                print(f"  Wikidata: {p['wikidataQid']}")
                if p['viafId']:
                    print(f"  VIAF: {p['viafId']}")

                if p['birthEvent']:
                    birth_date = p['birthEvent'].get('date', 'Unknown')
                    print(f"  Born: {birth_date}")
                    if 'places' in p['birthEvent']:
                        for place in p['birthEvent']['places'][:1]:
                            if place.get('type') == 'geonames':
                                print(f"    Place: GeoNames ID {place['id']}")

                if p['deathEvent']:
                    death_date = p['deathEvent'].get('date', 'Unknown')
                    print(f"  Died: {death_date}")
                    if 'places' in p['deathEvent']:
                        for place in p['deathEvent']['places'][:1]:
                            if place.get('type') == 'geonames':
                                print(f"    Place: GeoNames ID {place['id']}")

                if p['relationships']:
                    print(f"  Relationships: {len(p['relationships'])}")

                sample_count += 1

        print("\n" + "="*60)

    def parse(self, output_file: str):
        """Execute complete parsing workflow."""
        self.load_graph()
        self.cache_time_spans()
        self.cache_places()
        self.extract_persons()
        self.extract_birth_events()
        self.extract_death_events()
        self.extract_marriages()
        self.save_to_json(output_file)
        self.print_statistics()


def main():
    """Main execution."""
    import sys

    ttl_file = sys.argv[1] if len(sys.argv) > 1 else "LINCsDATA/hist-cdns.ttl"
    output_json = sys.argv[2] if len(sys.argv) > 2 else "lincs_historical_canadians.json"

    parser = HistoricalCanadiansParser(ttl_file)
    parser.parse(output_json)

    print(f"\n✓ Parsing complete! Output: {output_json}")


if __name__ == "__main__":
    main()
