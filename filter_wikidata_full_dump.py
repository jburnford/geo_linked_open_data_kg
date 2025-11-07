#!/usr/bin/env python3
"""
Filter full Wikidata dump to extract only entities with P625 (coordinates).

Processes the compressed dump directly without decompressing.
Memory-efficient streaming approach.

Usage:
    python3 filter_wikidata_full_dump.py <input.json.gz> <output.json.gz>
"""

import json
import gzip
import sys
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime


class WikidataFullDumpFilter:
    """Filter full Wikidata dump for geographic entities."""

    def __init__(self, input_file: str, output_file: str):
        self.input_file = input_file
        self.output_file = output_file

        # Statistics
        self.stats = {
            'total_entities': 0,
            'with_coordinates': 0,
            'with_geonames': 0,
            'with_alternate_names': 0,
            'historical_entities': 0,
            'colonial_entities': 0,
            'with_cross_db_ids': 0,
            'parse_errors': 0,
        }

        # Historical entity types (instance of P31)
        self.historical_types = {
            'Q133156',  # colony
            'Q1750636', # colonial trading post
            'Q57821',   # fortification
            'Q16748868', # historical country
            'Q3024240', # historical country
            'Q28171280', # ancient city
            'Q839954',  # archaeological site
            'Q1266818', # historical region
            'Q1620908', # historical geographic location
            'Q15632617', # former administrative territorial entity
            'Q19953632', # former municipality
            'Q19730508', # historical administrative division
        }

        # Output buffer for batch writing
        self.output_buffer = []
        self.buffer_size = 1000  # Write every 1000 entities

    def _extract_string_value(self, claim) -> Optional[str]:
        """Extract string value from a claim."""
        try:
            mainsnak = claim.get('mainsnak', {})
            if mainsnak.get('snaktype') == 'value':
                datavalue = mainsnak.get('datavalue', {})
                if datavalue.get('type') == 'string':
                    return datavalue.get('value')
        except:
            pass
        return None

    def _extract_item_id(self, claim) -> Optional[str]:
        """Extract Wikidata item ID from a claim."""
        try:
            mainsnak = claim.get('mainsnak', {})
            if mainsnak.get('snaktype') == 'value':
                datavalue = mainsnak.get('datavalue', {})
                if datavalue.get('type') == 'wikibase-entityid':
                    return datavalue.get('value', {}).get('id')
        except:
            pass
        return None

    def _extract_time_value(self, claim) -> Optional[str]:
        """Extract time value from a claim."""
        try:
            mainsnak = claim.get('mainsnak', {})
            if mainsnak.get('snaktype') == 'value':
                datavalue = mainsnak.get('datavalue', {})
                if datavalue.get('type') == 'time':
                    time_str = datavalue.get('value', {}).get('time', '')
                    if time_str:
                        date = time_str.lstrip('+').split('T')[0]
                        return date
        except:
            pass
        return None

    def _extract_coordinates(self, claim) -> Optional[tuple]:
        """Extract latitude/longitude from a coordinate claim."""
        try:
            mainsnak = claim.get('mainsnak', {})
            if mainsnak.get('snaktype') == 'value':
                datavalue = mainsnak.get('datavalue', {})
                if datavalue.get('type') == 'globecoordinate':
                    value = datavalue.get('value', {})
                    lat = value.get('latitude')
                    lon = value.get('longitude')
                    if lat is not None and lon is not None:
                        return (lat, lon)
        except:
            pass
        return None

    def _extract_quantity_value(self, claim) -> Optional[int]:
        """Extract quantity value (for population)."""
        try:
            mainsnak = claim.get('mainsnak', {})
            if mainsnak.get('snaktype') == 'value':
                datavalue = mainsnak.get('datavalue', {})
                if datavalue.get('type') == 'quantity':
                    amount = datavalue.get('value', {}).get('amount', 0)
                    return int(float(amount))
        except:
            pass
        return None

    def _extract_all_labels(self, entity: Dict) -> List[str]:
        """Extract all language labels as alternate names."""
        labels = []
        try:
            for lang, label_obj in entity.get('labels', {}).items():
                value = label_obj.get('value')
                if value:
                    labels.append(value)
        except:
            pass
        return labels

    def _extract_all_aliases(self, entity: Dict) -> List[str]:
        """Extract all aliases in all languages."""
        aliases = []
        try:
            for lang, alias_list in entity.get('aliases', {}).items():
                for alias_obj in alias_list:
                    value = alias_obj.get('value')
                    if value:
                        aliases.append(value)
        except:
            pass
        return aliases

    def parse_entity(self, entity: Dict) -> Optional[Dict]:
        """Parse a single entity and extract relevant data if it has coordinates."""

        qid = entity.get('id')
        if not qid:
            return None

        claims = entity.get('claims', {})

        # Check for coordinates (P625) - required
        if 'P625' not in claims:
            return None  # Skip entities without coordinates

        coords = None
        for claim in claims['P625']:
            coords = self._extract_coordinates(claim)
            if coords:
                break

        if not coords:
            return None

        # We have coordinates - extract all data
        self.stats['with_coordinates'] += 1

        # Get primary label (English preferred)
        labels_dict = entity.get('labels', {})
        name = labels_dict.get('en', {}).get('value')
        if not name:
            # Fallback to first available label
            for lang, label_obj in labels_dict.items():
                name = label_obj.get('value')
                if name:
                    break
        if not name:
            name = qid

        # Get description
        descriptions_dict = entity.get('descriptions', {})
        description = descriptions_dict.get('en', {}).get('value')

        # Build result
        result = {
            'qid': qid,
            'name': name,
            'description': description,
            'latitude': coords[0],
            'longitude': coords[1],
        }

        # Extract alternate names (ALL languages and aliases)
        all_labels = self._extract_all_labels(entity)
        all_aliases = self._extract_all_aliases(entity)
        alternate_names = list(set(all_labels + all_aliases))
        alternate_names = [n for n in alternate_names if n != name]

        if alternate_names:
            result['alternateNames'] = alternate_names
            self.stats['with_alternate_names'] += 1

        # Extract instance of (P31)
        instance_of_list = []
        if 'P31' in claims:
            for claim in claims['P31']:
                instance_id = self._extract_item_id(claim)
                if instance_id:
                    instance_of_list.append(instance_id)
        if instance_of_list:
            result['instanceOfQid'] = instance_of_list[0]

        # Check if historical
        is_historical = bool(set(instance_of_list) & self.historical_types)
        if is_historical:
            self.stats['historical_entities'] += 1

        # GeoNames ID (P1566)
        if 'P1566' in claims:
            geonames_id = self._extract_string_value(claims['P1566'][0])
            if geonames_id:
                result['geonamesId'] = geonames_id
                self.stats['with_geonames'] += 1

        # Official names (P1448)
        if 'P1448' in claims:
            official_names = []
            for claim in claims['P1448']:
                val = self._extract_string_value(claim)
                if val:
                    official_names.append(val)
            if official_names:
                result['officialNames'] = official_names

        # Native label (P1705)
        if 'P1705' in claims:
            result['nativeLabel'] = self._extract_string_value(claims['P1705'][0])

        # Nickname (P1449)
        if 'P1449' in claims:
            result['nickname'] = self._extract_string_value(claims['P1449'][0])

        # Population (P1082)
        if 'P1082' in claims:
            pop = self._extract_quantity_value(claims['P1082'][0])
            if pop:
                result['population'] = pop

        # Temporal data
        if 'P571' in claims:
            result['inceptionDate'] = self._extract_time_value(claims['P571'][0])
        if 'P576' in claims:
            result['dissolvedDate'] = self._extract_time_value(claims['P576'][0])
            result['abolishedDate'] = self._extract_time_value(claims['P576'][0])

        # Historical succession
        if 'P1365' in claims:
            result['replacesQid'] = self._extract_item_id(claims['P1365'][0])
        if 'P1366' in claims:
            result['replacedByQid'] = self._extract_item_id(claims['P1366'][0])
        if 'P155' in claims:
            result['followsQid'] = self._extract_item_id(claims['P155'][0])
        if 'P156' in claims:
            result['followedByQid'] = self._extract_item_id(claims['P156'][0])

        # Colonial context
        if 'P112' in claims:
            founded_by = self._extract_item_id(claims['P112'][0])
            if founded_by:
                result['foundedByQid'] = founded_by
                self.stats['colonial_entities'] += 1

        if 'P127' in claims:
            owned_by = self._extract_item_id(claims['P127'][0])
            if owned_by:
                result['ownedByQid'] = owned_by
                self.stats['colonial_entities'] += 1

        if 'P1376' in claims:
            result['capitalOfQid'] = self._extract_item_id(claims['P1376'][0])

        # Country (P17)
        if 'P17' in claims:
            result['countryQid'] = self._extract_item_id(claims['P17'][0])

        # Cross-database identifiers
        cross_db = False
        if 'P227' in claims:
            result['gndId'] = self._extract_string_value(claims['P227'][0])
            cross_db = True
        if 'P214' in claims:
            result['viafId'] = self._extract_string_value(claims['P214'][0])
            cross_db = True
        if 'P244' in claims:
            result['locId'] = self._extract_string_value(claims['P244'][0])
            cross_db = True
        if 'P1667' in claims:
            result['tgnId'] = self._extract_string_value(claims['P1667'][0])
            cross_db = True
        if 'P402' in claims:
            result['osmId'] = self._extract_string_value(claims['P402'][0])
            cross_db = True
        if 'P6766' in claims:
            result['wofId'] = self._extract_string_value(claims['P6766'][0])
            cross_db = True

        if cross_db:
            self.stats['with_cross_db_ids'] += 1

        # Historic county (P7959)
        if 'P7959' in claims:
            result['historicCountyQid'] = self._extract_item_id(claims['P7959'][0])

        # Official website (P856)
        if 'P856' in claims:
            result['officialWebsite'] = self._extract_string_value(claims['P856'][0])

        # Wikipedia URL
        sitelinks = entity.get('sitelinks', {})
        if 'enwiki' in sitelinks:
            title = sitelinks['enwiki'].get('title')
            if title:
                result['wikipediaUrl'] = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"

        return result

    def flush_buffer(self, output_handle):
        """Write buffered entities to output file."""
        if self.output_buffer:
            for place in self.output_buffer:
                json.dump(place, output_handle, ensure_ascii=False)
                output_handle.write('\n')
            self.output_buffer = []

    def process_dump(self):
        """Process the full dump file."""

        print(f"Processing full Wikidata dump: {self.input_file}")
        print(f"Output: {self.output_file}")
        print(f"Start time: {datetime.now()}")
        print()

        # Open input (compressed)
        input_handle = gzip.open(self.input_file, 'rt', encoding='utf-8')

        # Open output (compressed)
        output_handle = gzip.open(self.output_file, 'wt', encoding='utf-8')

        # Write metadata header
        metadata = {
            'source': 'full Wikidata dump',
            'dump_file': self.input_file,
            'filter': 'P625 (coordinates)',
            'start_time': str(datetime.now()),
        }
        output_handle.write('{"metadata":')
        json.dump(metadata, output_handle, ensure_ascii=False)
        output_handle.write('}\n')

        try:
            print("Filtering entities with coordinates (P625)...")
            print("(This will take several hours for the full dump)")
            print()

            line_num = 0
            last_report = 0

            for line in input_handle:
                line = line.strip()

                # Skip array brackets and empty lines
                if not line or line == '[' or line == ']':
                    continue

                # Remove trailing comma
                if line.endswith(','):
                    line = line[:-1]

                line_num += 1
                self.stats['total_entities'] = line_num

                # Progress report every 100K entities
                if line_num - last_report >= 100000:
                    print(f"Processed {line_num:,} entities... "
                          f"Found {self.stats['with_coordinates']:,} with coordinates "
                          f"({self.stats['with_coordinates']/line_num*100:.2f}%)")
                    last_report = line_num

                try:
                    entity = json.loads(line)
                    place = self.parse_entity(entity)

                    if place:
                        self.output_buffer.append(place)

                        # Flush buffer periodically
                        if len(self.output_buffer) >= self.buffer_size:
                            self.flush_buffer(output_handle)

                except json.JSONDecodeError:
                    self.stats['parse_errors'] += 1
                    continue

            # Flush remaining buffer
            self.flush_buffer(output_handle)

        finally:
            input_handle.close()
            output_handle.close()

        print()
        print(f"✓ Filtering complete!")
        print(f"End time: {datetime.now()}")
        print()

        self.print_statistics()

    def print_statistics(self):
        """Print filtering statistics."""
        print("="*60)
        print("WIKIDATA FILTERING STATISTICS")
        print("="*60)

        total = self.stats['total_entities']
        found = self.stats['with_coordinates']

        print(f"\nTotal entities processed: {total:,}")
        print(f"  With coordinates (P625): {found:,} ({found/total*100:.2f}%)")

        if found > 0:
            print(f"\nOf entities with coordinates:")
            print(f"  With GeoNames ID: {self.stats['with_geonames']:,} ({self.stats['with_geonames']/found*100:.1f}%)")
            print(f"  With alternate names: {self.stats['with_alternate_names']:,} ({self.stats['with_alternate_names']/found*100:.1f}%)")
            print(f"  Historical entities: {self.stats['historical_entities']:,} ({self.stats['historical_entities']/found*100:.1f}%)")
            print(f"  Colonial context: {self.stats['colonial_entities']:,} ({self.stats['colonial_entities']/found*100:.1f}%)")
            print(f"  With cross-DB IDs: {self.stats['with_cross_db_ids']:,} ({self.stats['with_cross_db_ids']/found*100:.1f}%)")

        if self.stats['parse_errors'] > 0:
            print(f"\nParse errors: {self.stats['parse_errors']:,}")

        print("="*60)


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 filter_wikidata_full_dump.py <input.json.gz> <output.json.gz>")
        print("\nExample:")
        print("  python3 filter_wikidata_full_dump.py wikidata-latest-all.json.gz wikidata_p625_filtered.json.gz")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    if not Path(input_file).exists():
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)

    filter_tool = WikidataFullDumpFilter(input_file, output_file)
    filter_tool.process_dump()


if __name__ == '__main__':
    main()
