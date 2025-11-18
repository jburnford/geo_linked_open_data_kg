#!/usr/bin/env python3
"""
Parse Wikidata dump from wdumps.toolforge.org and extract geographic entities
with comprehensive historical and colonial context.

Processes the P625 (coordinate location) dump and extracts all properties
identified in WIKIDATA_PROPERTIES_ANALYSIS.md.
"""

import json
import gzip
import sys
from typing import Dict, List, Optional, Set
from pathlib import Path
from tqdm import tqdm


class WikidataDumpParser:
    """Parse Wikidata JSON dump and extract geographic entities."""

    def __init__(self, dump_file: str, output_file: str):
        self.dump_file = dump_file
        self.output_file = output_file

        # Track statistics
        self.stats = {
            'total_entities': 0,
            'with_coordinates': 0,
            'with_geonames': 0,
            'with_alternate_names': 0,
            'historical_entities': 0,
            'colonial_entities': 0,
            'with_cross_db_ids': 0,
        }

        # Historical entity types we care about (instance of)
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
                    # Format: +1858-11-01T00:00:00Z
                    if time_str:
                        # Extract date part
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

    def _extract_label(self, entity: Dict, qid: str, lang: str = 'en') -> Optional[str]:
        """Extract label in specified language."""
        try:
            labels = entity.get('labels', {})
            if lang in labels:
                return labels[lang].get('value')
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
        """Parse a single Wikidata entity and extract relevant data."""

        qid = entity.get('id')
        if not qid:
            return None

        claims = entity.get('claims', {})

        # Extract coordinates (P625) - required
        coords = None
        if 'P625' in claims:
            for claim in claims['P625']:
                coords = self._extract_coordinates(claim)
                if coords:
                    break

        if not coords:
            return None  # Skip entities without coordinates

        # Extract basic data
        name = self._extract_label(entity, qid, 'en')
        if not name:
            # Fallback to first available label
            labels = self._extract_all_labels(entity)
            name = labels[0] if labels else qid

        description = entity.get('descriptions', {}).get('en', {}).get('value')

        # Build result
        result = {
            'qid': qid,
            'name': name,
            'description': description,
            'latitude': coords[0],
            'longitude': coords[1],
        }

        # Extract instance of (P31)
        instance_of_list = []
        if 'P31' in claims:
            for claim in claims['P31']:
                instance_id = self._extract_item_id(claim)
                if instance_id:
                    instance_of_list.append(instance_id)

        result['instanceOfQid'] = instance_of_list[0] if instance_of_list else None

        # Check if historical entity
        is_historical = bool(set(instance_of_list) & self.historical_types)
        if is_historical:
            self.stats['historical_entities'] += 1

        # Extract GeoNames ID (P1566)
        if 'P1566' in claims:
            result['geonamesId'] = self._extract_string_value(claims['P1566'][0])
            if result['geonamesId']:
                self.stats['with_geonames'] += 1

        # Extract alternate names (CRITICAL FOR NER)
        all_labels = self._extract_all_labels(entity)
        all_aliases = self._extract_all_aliases(entity)

        # Combine and deduplicate
        alternate_names = list(set(all_labels + all_aliases))
        # Remove the primary name
        alternate_names = [n for n in alternate_names if n != name]

        if alternate_names:
            result['alternateNames'] = alternate_names
            self.stats['with_alternate_names'] += 1

        # Extract official name (P1448)
        if 'P1448' in claims:
            official_names = []
            for claim in claims['P1448']:
                val = self._extract_string_value(claim)
                if val:
                    official_names.append(val)
            if official_names:
                result['officialNames'] = official_names

        # Extract native label (P1705)
        if 'P1705' in claims:
            result['nativeLabel'] = self._extract_string_value(claims['P1705'][0])

        # Extract nickname (P1449)
        if 'P1449' in claims:
            result['nickname'] = self._extract_string_value(claims['P1449'][0])

        # Extract population (P1082)
        if 'P1082' in claims:
            try:
                mainsnak = claims['P1082'][0].get('mainsnak', {})
                if mainsnak.get('snaktype') == 'value':
                    datavalue = mainsnak.get('datavalue', {})
                    if datavalue.get('type') == 'quantity':
                        result['population'] = int(float(datavalue.get('value', {}).get('amount', 0)))
            except:
                pass

        # Extract temporal data
        if 'P571' in claims:  # inception
            result['inceptionDate'] = self._extract_time_value(claims['P571'][0])
        if 'P576' in claims:  # dissolved/abolished
            result['dissolvedDate'] = self._extract_time_value(claims['P576'][0])
        if 'P576' in claims:  # abolished (same as dissolved)
            result['abolishedDate'] = self._extract_time_value(claims['P576'][0])

        # Extract historical succession
        if 'P1365' in claims:  # replaces
            result['replacesQid'] = self._extract_item_id(claims['P1365'][0])
        if 'P1366' in claims:  # replaced by
            result['replacedByQid'] = self._extract_item_id(claims['P1366'][0])
        if 'P155' in claims:  # follows
            result['followsQid'] = self._extract_item_id(claims['P155'][0])
        if 'P156' in claims:  # followed by
            result['followedByQid'] = self._extract_item_id(claims['P156'][0])

        # Extract colonial context
        if 'P112' in claims:  # founded by
            founded_by_qid = self._extract_item_id(claims['P112'][0])
            if founded_by_qid:
                result['foundedByQid'] = founded_by_qid
                # Note: We don't have labels in dump, will need to fetch or use second pass
                self.stats['colonial_entities'] += 1

        if 'P127' in claims:  # owned by
            owned_by_qid = self._extract_item_id(claims['P127'][0])
            if owned_by_qid:
                result['ownedByQid'] = owned_by_qid
                self.stats['colonial_entities'] += 1

        if 'P1376' in claims:  # capital of
            capital_of_qid = self._extract_item_id(claims['P1376'][0])
            if capital_of_qid:
                result['capitalOfQid'] = capital_of_qid

        # Extract country (P17)
        if 'P17' in claims:
            result['countryQid'] = self._extract_item_id(claims['P17'][0])

        # Extract cross-database identifiers
        cross_db_found = False

        if 'P227' in claims:  # GND ID
            result['gndId'] = self._extract_string_value(claims['P227'][0])
            cross_db_found = True
        if 'P214' in claims:  # VIAF ID
            result['viafId'] = self._extract_string_value(claims['P214'][0])
            cross_db_found = True
        if 'P244' in claims:  # Library of Congress ID
            result['locId'] = self._extract_string_value(claims['P244'][0])
            cross_db_found = True
        if 'P1667' in claims:  # Getty TGN ID
            result['tgnId'] = self._extract_string_value(claims['P1667'][0])
            cross_db_found = True
        if 'P402' in claims:  # OpenStreetMap relation ID
            result['osmId'] = self._extract_string_value(claims['P402'][0])
            cross_db_found = True
        if 'P6766' in claims:  # Who's on First ID
            result['wofId'] = self._extract_string_value(claims['P6766'][0])
            cross_db_found = True

        if cross_db_found:
            self.stats['with_cross_db_ids'] += 1

        # Extract historic county (P7959)
        if 'P7959' in claims:
            result['historicCountyQid'] = self._extract_item_id(claims['P7959'][0])

        # Extract official website (P856)
        if 'P856' in claims:
            result['officialWebsite'] = self._extract_string_value(claims['P856'][0])

        # Extract Wikipedia URL (enwiki sitelink)
        sitelinks = entity.get('sitelinks', {})
        if 'enwiki' in sitelinks:
            title = sitelinks['enwiki'].get('title')
            if title:
                result['wikipediaUrl'] = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"

        return result

    def process_dump(self):
        """Process the entire dump file."""

        print(f"Processing Wikidata dump: {self.dump_file}")
        print(f"Output: {self.output_file}")

        # Detect if gzipped
        is_gzipped = self.dump_file.endswith('.gz')

        places = []

        # Open file
        if is_gzipped:
            file_handle = gzip.open(self.dump_file, 'rt', encoding='utf-8')
        else:
            file_handle = open(self.dump_file, 'r', encoding='utf-8')

        try:
            # Wikidata dumps are newline-delimited JSON
            print("\nParsing entities...")

            for line in tqdm(file_handle, desc="Processing entities"):
                line = line.strip()
                if not line or line == '[' or line == ']':
                    continue

                # Remove trailing comma if present
                if line.endswith(','):
                    line = line[:-1]

                try:
                    entity = json.loads(line)
                    self.stats['total_entities'] += 1

                    place = self.parse_entity(entity)
                    if place:
                        places.append(place)
                        self.stats['with_coordinates'] += 1

                except json.JSONDecodeError as e:
                    print(f"\nWarning: Failed to parse entity: {e}")
                    continue

        finally:
            file_handle.close()

        # Write output
        print(f"\nWriting {len(places):,} places to {self.output_file}...")

        output_data = {
            'metadata': {
                'source': 'wdumps.toolforge.org',
                'dump_file': self.dump_file,
                'total_records': len(places),
                'statistics': self.stats,
            },
            'places': places
        }

        # Compress output if large
        if self.output_file.endswith('.gz'):
            with gzip.open(self.output_file, 'wt', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
        else:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

        print(f"✓ Done!")

        # Print statistics
        self.print_statistics()

    def print_statistics(self):
        """Print parsing statistics."""
        print("\n" + "="*60)
        print("WIKIDATA DUMP PARSING STATISTICS")
        print("="*60)

        total = self.stats['total_entities']

        print(f"\nTotal entities in dump: {total:,}")
        print(f"  With coordinates (P625): {self.stats['with_coordinates']:,} ({self.stats['with_coordinates']/total*100:.1f}%)")
        print(f"  With GeoNames ID: {self.stats['with_geonames']:,} ({self.stats['with_geonames']/total*100:.1f}%)")
        print(f"  With alternate names: {self.stats['with_alternate_names']:,} ({self.stats['with_alternate_names']/total*100:.1f}%)")
        print(f"  Historical entities: {self.stats['historical_entities']:,} ({self.stats['historical_entities']/total*100:.1f}%)")
        print(f"  Colonial context: {self.stats['colonial_entities']:,} ({self.stats['colonial_entities']/total*100:.1f}%)")
        print(f"  With cross-database IDs: {self.stats['with_cross_db_ids']:,} ({self.stats['with_cross_db_ids']/total*100:.1f}%)")

        print("="*60)


def main():
    """Main execution."""

    if len(sys.argv) < 2:
        print("Usage: python3 parse_wikidata_dump.py <dump_file.json[.gz]> [output_file.json[.gz]]")
        print("\nExample:")
        print("  python3 parse_wikidata_dump.py wikidata_dump_5175.json.gz wikidata_global_complete.json.gz")
        sys.exit(1)

    dump_file = sys.argv[1]

    if len(sys.argv) >= 3:
        output_file = sys.argv[2]
    else:
        # Auto-generate output filename
        output_file = 'wikidata_global_complete.json.gz'

    if not Path(dump_file).exists():
        print(f"Error: Dump file not found: {dump_file}")
        sys.exit(1)

    parser = WikidataDumpParser(dump_file, output_file)
    parser.process_dump()


if __name__ == '__main__':
    main()
