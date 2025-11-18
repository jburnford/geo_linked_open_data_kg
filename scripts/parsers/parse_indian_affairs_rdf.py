#!/usr/bin/env python3
"""
Parse LINCS Indian Affairs Agents RDF (Turtle format) and convert to Neo4j-friendly JSON.

RDF Structure (CIDOC-CRM):
- crm:E21_Person: Individual agents
- crm:E7_Activity: Occupation events (role, location, dates)
- crm:E52_Time-Span: Date ranges
- crm:E33_E41_Linguistic_Appellation: Names
- crm:P14_carried_out_by: Links activity → person
- crm:P7_took_place_at: Links activity → place (GeoNames URLs)
- crm:P4_has_time-span: Links activity → time span
"""

import json
import re
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS
from typing import Dict, List, Set
from tqdm import tqdm

# Define namespaces
CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
LINCS = Namespace("http://lod.lincsproject.ca/")
EVENT = Namespace("http://linkedevents.org/ontology/")
WIKIDATA = Namespace("http://www.wikidata.org/entity/")
VIAF = Namespace("http://viaf.org/viaf/")
GEONAMES = Namespace("https://sws.geonames.org/")


def parse_indian_affairs_rdf(ttl_file: str, output_json: str):
    """
    Parse Indian Affairs Agents RDF and extract structured data.

    Output format:
    {
        "persons": [
            {
                "lincsId": "lincs:abc123",
                "name": "William Shives Fisher",
                "viafId": "16905756",
                "wikidataQid": "Q1585303",
                "occupations": [
                    {
                        "role": "Indian Agent",
                        "agency": "Department of Indian Affairs",
                        "startDate": "1913",
                        "geonamesId": 6098717,
                        "location": "Ottawa"
                    }
                ]
            }
        ]
    }
    """

    print(f"Loading RDF from {ttl_file}...")
    g = Graph()
    g.parse(ttl_file, format="turtle")

    print(f"Loaded {len(g):,} triples")

    # Extract all persons
    print("\nExtracting persons...")
    persons = {}

    person_uris = set(g.subjects(RDF.type, CRM.E21_Person))
    print(f"Found {len(person_uris):,} persons")

    OWL_SAME_AS = URIRef("http://www.w3.org/2002/07/owl#sameAs")

    for person_uri in tqdm(person_uris, desc="Processing persons"):
        lincs_id = str(person_uri).replace(str(LINCS), "lincs:")

        # Get label (name)
        name = None
        for label in g.objects(person_uri, RDFS.label):
            name = str(label)
            break

        # Get external IDs
        viaf_id = None
        wikidata_qid = None

        # Check if person itself has owl:sameAs (direct link)
        for same_as in g.objects(person_uri, OWL_SAME_AS):
            same_as_str = str(same_as)
            if "viaf.org" in same_as_str:
                viaf_id = same_as_str.split("/")[-1]
            elif "wikidata.org" in same_as_str:
                wikidata_qid = same_as_str.split("/")[-1]

        # CIDOC-CRM pattern: Person → P1_is_identified_by → Name Appellation → owl:sameAs → Wikidata
        for name_appellation_uri in g.objects(person_uri, CRM.P1_is_identified_by):
            for same_as in g.objects(name_appellation_uri, OWL_SAME_AS):
                same_as_str = str(same_as)
                if "viaf.org" in same_as_str:
                    viaf_id = same_as_str.split("/")[-1]
                elif "wikidata.org" in same_as_str:
                    wikidata_qid = same_as_str.split("/")[-1]

        persons[person_uri] = {
            "lincsId": lincs_id,
            "name": name,
            "viafId": viaf_id,
            "wikidataQid": wikidata_qid,
            "occupations": []
        }

    # Extract occupation activities
    print("\nExtracting occupation activities...")
    activities = list(g.subjects(RDF.type, CRM.E7_Activity))
    print(f"Found {len(activities):,} activities")

    for activity_uri in tqdm(activities, desc="Processing activities"):
        # Get person who carried out activity
        person_uri = None
        for p in g.objects(activity_uri, CRM.P14_carried_out_by):
            person_uri = p
            break

        if not person_uri or person_uri not in persons:
            continue

        # Get activity label (contains role info)
        activity_label = None
        for label in g.objects(activity_uri, RDFS.label):
            activity_label = str(label)
            break

        # Extract role from label like "Indian Agent occupation of Johnson, J.A. starting in 1913"
        role = "Unknown"
        if activity_label:
            match = re.match(r"^(.+?)\s+occupation\s+of", activity_label)
            if match:
                role = match.group(1).strip()

        # Get location (GeoNames URL)
        geonames_id = None
        for place_uri in g.objects(activity_uri, CRM.P7_took_place_at):
            place_str = str(place_uri)
            if "geonames.org" in place_str:
                try:
                    # Extract numeric ID from URL like https://sws.geonames.org/6098717/
                    id_str = place_str.rstrip("/").split("/")[-1]
                    # Remove any non-numeric characters (sometimes has trailing 'l')
                    id_str = ''.join(c for c in id_str if c.isdigit())
                    if id_str:
                        geonames_id = int(id_str)
                except (ValueError, IndexError):
                    pass  # Skip malformed GeoNames IDs
                break

        # Get time span
        start_date = None
        for time_span_uri in g.objects(activity_uri, CRM.P4_has_time_span):
            # Get start date from time span
            for date_val in g.objects(time_span_uri, CRM.P82_at_some_time_within):
                start_date = str(date_val)
                break

        # Get agency (participant)
        agency = "Department of Indian Affairs"  # Default
        for agency_uri in g.objects(activity_uri, CRM.P11_had_participant):
            # Try to get agency label
            for ag_label in g.objects(agency_uri, RDFS.label):
                agency = str(ag_label)
                break

        # Add occupation to person
        persons[person_uri]["occupations"].append({
            "role": role,
            "agency": agency,
            "startDate": start_date,
            "geonamesId": geonames_id
        })

    # Convert to list and save
    persons_list = list(persons.values())

    # Filter out persons with no occupations or no name
    persons_list = [p for p in persons_list if p["name"] and p["occupations"]]

    print(f"\nSaving {len(persons_list):,} persons with occupation data to {output_json}")

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump({"persons": persons_list}, f, indent=2, ensure_ascii=False)

    # Print statistics
    print("\n" + "="*60)
    print("EXTRACTION STATISTICS")
    print("="*60)
    print(f"Total persons: {len(persons_list):,}")
    print(f"Persons with VIAF IDs: {sum(1 for p in persons_list if p['viafId']):,}")
    print(f"Persons with Wikidata QIDs: {sum(1 for p in persons_list if p['wikidataQid']):,}")
    print(f"Total occupations: {sum(len(p['occupations']) for p in persons_list):,}")
    print(f"Occupations with GeoNames IDs: {sum(1 for p in persons_list for o in p['occupations'] if o['geonamesId']):,}")

    # Sample data
    print("\nSample person:")
    for person in persons_list[:3]:
        if person["occupations"]:
            print(f"\n  {person['name']} ({person['lincsId']})")
            if person["viafId"]:
                print(f"    VIAF: {person['viafId']}")
            if person["wikidataQid"]:
                print(f"    Wikidata: {person['wikidataQid']}")
            for occ in person["occupations"][:2]:
                print(f"    - {occ['role']} at GeoNames {occ['geonamesId']} ({occ['startDate']})")
            break

    print("="*60)

    return persons_list


if __name__ == "__main__":
    import sys

    ttl_file = sys.argv[1] if len(sys.argv) > 1 else "indian_affairs_agents.ttl"
    output_json = sys.argv[2] if len(sys.argv) > 2 else "indian_affairs_agents.json"

    persons = parse_indian_affairs_rdf(ttl_file, output_json)
    print(f"\n✓ Parsing complete! Output: {output_json}")
