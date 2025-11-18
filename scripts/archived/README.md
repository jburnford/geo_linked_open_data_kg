# Archived Scripts

This directory contains older versions of scripts that have been superseded by improved implementations. These are preserved for reference but should not be used in production.

## Administrative Hierarchy Scripts

### create_admin_hierarchies.py (Original)
- **Status**: Failed on mega-countries (China, India, USA)
- **Issue**: Memory pool exhaustion, no batching strategy
- **Replaced by**: create_admin_hierarchies_robust.py

### create_admin_hierarchies_batched.py (Second Version)
- **Status**: Crashed at country ~107
- **Issue**: Still had memory issues, NOT EXISTS performance killer
- **Replaced by**: create_admin_hierarchies_robust.py

### Current Active Version
Use **scripts/linkers/create_admin_hierarchies_robust.py** which features:
- Three-tier adaptive chunking (normal/admin1/admin2)
- Memory optimization (10GB transaction pool)
- Resume capability
- Successfully processes all 254 countries including mega-countries

## LINCS Parser Scripts

### parse_lincs_historical_canadians_backup.py
- **Status**: Backup version
- **Replaced by**: scripts/parsers/parse_lincs_historical_canadians.py

## Wikidata Loader Scripts

### load_wikidata_entities_fixed.py
- **Status**: Fixed version for specific issues
- **Replaced by**: scripts/loaders/load_wikidata_entities.py (consolidated)

---

**Do not use these archived scripts** - They are kept only for historical reference and understanding the project evolution.
