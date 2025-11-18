#!/usr/bin/env python3
"""
Filter Wikidata dump for organizations with place connections.

Extracts organizations like:
- Colonial companies (Hudson's Bay Company, etc.)
- Government agencies
- Religious organizations
- Trading companies

Usage:
    python3 filter_wikidata_organizations.py <input.json.gz> <output.json.gz>
"""

import json
import gzip
import sys
from typing import Dict, Optional, Set

class WikidataOrganizationsFilter:
    def __init__(self, input_file: str, output_file: str):
        self.input_file = input_file
        self.output_file = output_file
        self.stats = {
            'total_entities': 0,
            'orgs_found': 0,
            'orgs_with_places': 0,
            'parse_errors': 0,
        }
        self.output_buffer = []
        self.buffer_size = 1000

        # Organization types (P31)
        self.org_types: Set[str] = {
            'Q43229',    # organization
            'Q4830453',  # business
            'Q783794',   # company
            'Q6881511',  # enterprise
            'Q4830453',  # business
            'Q891723',   # public company
            'Q166280',   # trading company
            'Q7210356',  # government agency
            'Q16917',    # religious organization
            'Q1664720',  # institute
            'Q31855',    # research institute
            'Q2659904',  # government organization
        }

    def is_organization(self, claims: Dict) -> bool:
        """Check if entity is an organization."""
        instance_of = claims.get('P31', [])
        for claim in instance_of:
            try:
                qid = self.extract_item_id(claim)
                if qid in self.org_types:
                    return True
            except:
                pass
        return False

    def has_place_connection(self, claims: Dict) -> bool:
        """Check if organization has place connections."""
        place_properties = ['P740', 'P159', 'P2541', 'P131']
        return any(prop in claims for prop in place_properties)

    def extract_item_id(self, claim) -> Optional[str]:
        """Extract Wikidata item ID from claim."""
        try:
            mainsnak = claim.get('mainsnak', {})
            if mainsnak.get('snaktype') == 'value':
                datavalue = mainsnak.get('datavalue', {})
                if datavalue.get('type') == 'wikibase-entityid':
                    return datavalue.get('value', {}).get('id')
        except:
            pass
        return None

    def extract_string_value(self, claim) -> Optional[str]:
        """Extract string value from claim."""
        try:
            mainsnak = claim.get('mainsnak', {})
            if mainsnak.get('snaktype') == 'value':
                datavalue = mainsnak.get('datavalue', {})
                if datavalue.get('type') == 'string':
                    return datavalue.get('value')
        except:
            pass
        return None

    def extract_time_value(self, claim) -> Optional[str]:
        """Extract time value from claim."""
        try:
            mainsnak = claim.get('mainsnak', {})
            if mainsnak.get('snaktype') == 'value':
                datavalue = mainsnak.get('datavalue', {})
                if datavalue.get('type') == 'time':
                    time_str = datavalue.get('value', {}).get('time', '')
                    if time_str:
                        return time_str.lstrip('+').split('T')[0]
        except:
            pass
        return None

    def extract_label(self, labels: Dict, lang: str = 'en') -> Optional[str]:
        """Extract label in specified language."""
        if lang in labels:
            return labels[lang].get('value')
        return None

    def parse_entity(self, entity: Dict) -> Optional[Dict]:
        """Parse organization entity."""
        try:
            qid = entity.get('id')
            claims = entity.get('claims', {})

            if not self.is_organization(claims):
                return None

            self.stats['orgs_found'] += 1

            if not self.has_place_connection(claims):
                return None

            self.stats['orgs_with_places'] += 1

            labels = entity.get('labels', {})
            name = self.extract_label(labels, 'en')

            if not name:
                return None

            result = {
                'wikidataId': qid,
                'name': name,
            }

            # Extract founding/dissolution dates
            if 'P571' in claims:
                result['founded'] = self.extract_time_value(claims['P571'][0])
            if 'P576' in claims:
                result['dissolved'] = self.extract_time_value(claims['P576'][0])

            # Extract place connections
            if 'P740' in claims:  # location of formation
                result['foundedInQid'] = self.extract_item_id(claims['P740'][0])
            if 'P159' in claims:  # headquarters
                result['headquartersQid'] = self.extract_item_id(claims['P159'][0])

            # Extract operating areas (multiple)
            if 'P2541' in claims:
                operating_areas = []
                for claim in claims['P2541'][:10]:
                    qid = self.extract_item_id(claim)
                    if qid:
                        operating_areas.append(qid)
                if operating_areas:
                    result['operatingAreaQids'] = operating_areas

            # Extract located in
            if 'P131' in claims:
                result['locatedInQid'] = self.extract_item_id(claims['P131'][0])

            # Extract founders
            if 'P112' in claims:
                founders = []
                for claim in claims['P112'][:5]:
                    qid = self.extract_item_id(claim)
                    if qid:
                        founders.append(qid)
                if founders:
                    result['founderQids'] = founders

            # Extract parent organization
            if 'P749' in claims:
                result['parentOrgQid'] = self.extract_item_id(claims['P749'][0])

            # Extract industry
            if 'P452' in claims:
                result['industryQid'] = self.extract_item_id(claims['P452'][0])

            # Extract official name
            if 'P1448' in claims:
                result['officialName'] = self.extract_string_value(claims['P1448'][0])

            return result

        except Exception as e:
            self.stats['parse_errors'] += 1
            return None

    def filter_dump(self):
        """Process the full dump and extract organizations."""
        print(f"Processing {self.input_file}...")
        print(f"Output: {self.output_file}")

        with gzip.open(self.input_file, 'rt', encoding='utf-8') as infile, \
             gzip.open(self.output_file, 'wt', encoding='utf-8') as outfile:

            for line_num, line in enumerate(infile, 1):
                self.stats['total_entities'] += 1

                line = line.rstrip().rstrip(',')
                if line in ['[', ']']:
                    continue

                try:
                    entity = json.loads(line)
                    result = self.parse_entity(entity)

                    if result:
                        self.output_buffer.append(result)

                        if len(self.output_buffer) >= self.buffer_size:
                            for item in self.output_buffer:
                                outfile.write(json.dumps(item) + '\n')
                            self.output_buffer = []

                except json.JSONDecodeError:
                    self.stats['parse_errors'] += 1

                if line_num % 100000 == 0:
                    print(f"Processed {line_num:,} entities... "
                          f"Found {self.stats['orgs_with_places']:,} organizations")

            if self.output_buffer:
                for item in self.output_buffer:
                    outfile.write(json.dumps(item) + '\n')

        self.print_stats()

    def print_stats(self):
        """Print statistics."""
        print("\n" + "="*60)
        print("EXTRACTION COMPLETE")
        print("="*60)
        for key, value in self.stats.items():
            print(f"{key}: {value:,}")
        print("="*60)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 filter_wikidata_organizations.py <input.json.gz> <output.json.gz>")
        sys.exit(1)

    filter = WikidataOrganizationsFilter(sys.argv[1], sys.argv[2])
    filter.filter_dump()
