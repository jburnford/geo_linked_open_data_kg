#!/usr/bin/env python3
"""
Filter Wikidata dump for people (P31=Q5) with place connections.

Extracts:
- Birth place (P19)
- Death place (P20)
- Residence (P551)
- Work location (P937)
- Citizenship (P27)
- Occupation (P106)
- Position held (P39)
- Employer (P108)

Usage:
    python3 filter_wikidata_people.py <input.json.gz> <output.json.gz>
"""

import json
import gzip
import sys
from typing import Dict, Optional

class WikidataPeopleFilter:
    def __init__(self, input_file: str, output_file: str):
        self.input_file = input_file
        self.output_file = output_file
        self.stats = {
            'total_entities': 0,
            'people_found': 0,
            'people_with_places': 0,
            'parse_errors': 0,
        }
        self.output_buffer = []
        self.buffer_size = 1000

    def is_person(self, claims: Dict) -> bool:
        """Check if entity is a person (P31=Q5)."""
        instance_of = claims.get('P31', [])
        for claim in instance_of:
            try:
                mainsnak = claim.get('mainsnak', {})
                if mainsnak.get('snaktype') == 'value':
                    datavalue = mainsnak.get('datavalue', {})
                    if datavalue.get('type') == 'wikibase-entityid':
                        qid = datavalue.get('value', {}).get('id')
                        if qid == 'Q5':  # human
                            return True
            except:
                pass
        return False

    def has_place_connection(self, claims: Dict) -> bool:
        """Check if person has any place-related claims."""
        place_properties = ['P19', 'P20', 'P551', 'P937', 'P27']
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
        """Parse person entity and extract relevant data."""
        try:
            qid = entity.get('id')
            claims = entity.get('claims', {})

            # Check if person
            if not self.is_person(claims):
                return None

            self.stats['people_found'] += 1

            # Check if has place connections
            if not self.has_place_connection(claims):
                return None

            self.stats['people_with_places'] += 1

            # Extract labels
            labels = entity.get('labels', {})
            name = self.extract_label(labels, 'en')

            if not name:
                return None

            result = {
                'wikidataId': qid,
                'name': name,
            }

            # Extract birth/death dates
            if 'P569' in claims:
                result['dateOfBirth'] = self.extract_time_value(claims['P569'][0])
            if 'P570' in claims:
                result['dateOfDeath'] = self.extract_time_value(claims['P570'][0])

            # Extract place connections
            if 'P19' in claims:
                result['birthPlaceQid'] = self.extract_item_id(claims['P19'][0])
            if 'P20' in claims:
                result['deathPlaceQid'] = self.extract_item_id(claims['P20'][0])

            # Extract residences (multiple)
            if 'P551' in claims:
                residences = []
                for claim in claims['P551'][:5]:  # Limit to 5
                    qid = self.extract_item_id(claim)
                    if qid:
                        residences.append(qid)
                if residences:
                    result['residenceQids'] = residences

            # Extract work locations
            if 'P937' in claims:
                work_locations = []
                for claim in claims['P937'][:5]:
                    qid = self.extract_item_id(claim)
                    if qid:
                        work_locations.append(qid)
                if work_locations:
                    result['workLocationQids'] = work_locations

            # Extract citizenship
            if 'P27' in claims:
                result['citizenshipQid'] = self.extract_item_id(claims['P27'][0])

            # Extract occupations
            if 'P106' in claims:
                occupations = []
                for claim in claims['P106'][:5]:
                    qid = self.extract_item_id(claim)
                    if qid:
                        occupations.append(qid)
                if occupations:
                    result['occupationQids'] = occupations

            # Extract positions held
            if 'P39' in claims:
                positions = []
                for claim in claims['P39'][:5]:
                    qid = self.extract_item_id(claim)
                    if qid:
                        positions.append(qid)
                if positions:
                    result['positionQids'] = positions

            # Extract employers
            if 'P108' in claims:
                employers = []
                for claim in claims['P108'][:3]:
                    qid = self.extract_item_id(claim)
                    if qid:
                        employers.append(qid)
                if employers:
                    result['employerQids'] = employers

            # Extract cross-database IDs
            if 'P214' in claims:  # VIAF
                result['viafId'] = self.extract_string_value(claims['P214'][0])
            if 'P227' in claims:  # GND
                result['gndId'] = self.extract_string_value(claims['P227'][0])
            if 'P244' in claims:  # LOC
                result['locId'] = self.extract_string_value(claims['P244'][0])

            return result

        except Exception as e:
            self.stats['parse_errors'] += 1
            return None

    def filter_dump(self):
        """Process the full dump and extract people."""
        print(f"Processing {self.input_file}...")
        print(f"Output: {self.output_file}")

        with gzip.open(self.input_file, 'rt', encoding='utf-8') as infile, \
             gzip.open(self.output_file, 'wt', encoding='utf-8') as outfile:

            for line_num, line in enumerate(infile, 1):
                self.stats['total_entities'] += 1

                # Strip trailing comma and newline
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

                # Progress
                if line_num % 100000 == 0:
                    print(f"Processed {line_num:,} entities... "
                          f"Found {self.stats['people_with_places']:,} people with places")

            # Write remaining buffer
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
        print("Usage: python3 filter_wikidata_people.py <input.json.gz> <output.json.gz>")
        sys.exit(1)

    filter = WikidataPeopleFilter(sys.argv[1], sys.argv[2])
    filter.filter_dump()
