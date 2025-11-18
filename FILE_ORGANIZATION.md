# CanadaNeo4j File Organization

**Project**: Global Knowledge Graph with GeoNames + Wikidata + LINCS
**Status**: Phase 3 Complete (November 13, 2025)
**Location**: `/home/jic823/CanadaNeo4j/` (main) and `/home/jic823/CanadaNeo4j_transfer/` (transfer/staging)

---

## Directory Structure

### Main Project: `/home/jic823/CanadaNeo4j/`

#### Documentation (`docs/`)
- **Current Status**: `PROJECT_STATUS.md` (comprehensive project documentation)
- **Planning Docs** (`docs/planning/`):
  - Entity linking strategies
  - Spatial optimization plans
  - Wikidata workflow documentation
  - Storage and scaling plans
- **Deployment Docs** (`docs/deployment/`):
  - Arbutus VM deployment
  - Neo4j configuration
  - Monitoring guides
- **LINCS Docs** (`docs/lincs/`):
  - LINCS integration plan
  - LINCS summary guide
  - Indian Affairs pilot documentation

#### Scripts (`scripts/`)
- **Loaders** (`scripts/loaders/`):
  - `load_global_geonames.py` - Import GeoNames gazetteer
  - `load_wikidata_entities.py` - Import filtered Wikidata
  - `load_indian_affairs_agents.py` - Import LINCS pilot data
- **Linkers** (`scripts/linkers/`):
  - `create_admin_hierarchies_robust.py` - **Final Phase 3 script (SUCCESS)**
  - `link_wikidata_places_global.py` - GeoNames↔Wikidata linking
  - `link_spatial_optimized.py` - Spatial proximity linking
- **Parsers** (`scripts/parsers/`):
  - `parse_indian_affairs_rdf.py` - RDF/Turtle → JSON parser (CIDOC-CRM)
  - `parse_wikidata_dump.py` - Wikidata dump parser
  - `filter_wikidata_*.py` - Wikidata filtering scripts

#### Data (`data/`)
- **Raw Data** (`data/raw/`):
  - GeoNames files (allCountries.txt, admin codes)
  - Wikidata JSON dumps
  - LINCS RDF files (indian_affairs_agents.ttl)
- **Processed Data** (`data/processed/`):
  - Parsed JSON outputs
  - Export snapshots
  - Neo4j database dumps

### Transfer/Staging: `/home/jic823/CanadaNeo4j_transfer/`

**Purpose**: Staging area for large data files and deployment artifacts
**Contents**:
- Compressed export files (*.json.gz) for VM transfer
- LINCS documentation (being consolidated to main project)
- Deployment status snapshots
- **Credentials** (CREDENTIALS.txt - sensitive, not in main repo)

---

## File Locations (Current)

### Documentation Files

**Main Status**:
- `/home/jic823/CanadaNeo4j/PROJECT_STATUS.md` - **PRIMARY DOCUMENTATION** (most current)
- `/home/jic823/CanadaNeo4j/README.md` - Original project README

**Planning Documents** (all in main `/home/jic823/CanadaNeo4j/`):
- `ENTITY_LINKING_PLAN.md`, `ENTITY_LINKING_PLAN_UPDATED.md`
- `EXPANSION_STRATEGY.md`
- `HISTORICAL_KG_PIPELINE.md`
- `NEO4J_ON_NIBI_PLAN.md`
- `NEO4J_SCALING_LIMITS.md`
- `NIBI_WIKIDATA_WORKFLOW.md`
- `READY_TO_LINK.md`
- `SPATIAL_LINKING_OPTIMIZED.md`
- `WIKIDATA_*` planning docs (7 files)

**Deployment Documents** (in `/home/jic823/CanadaNeo4j_transfer/`):
- `ARBUTUS_DEPLOYMENT_PLAN.md`
- `DEPLOYMENT_STATUS.md`
- `DEPLOYMENT_SUMMARY.md`
- `MONITOR_DEPLOYMENT.md`

**LINCS Documents** (in `/home/jic823/CanadaNeo4j_transfer/`):
- `LINCS_INTEGRATION_PLAN.md` - Full integration plan (8 pages)
- `LINCS_SUMMARY.md` - Quick reference guide
- `lincs_quickstart.py` - SPARQL reconnaissance script

### Python Scripts

**Loaders** (all in main `/home/jic823/CanadaNeo4j/`):
- `load_global_geonames.py` - ✅ Phase 1 (6.2M places loaded)
- `load_wikidata_entities.py` - ✅ Phase 2 (11.6M geographic + 6M people + 235K orgs)
- `load_indian_affairs_agents.py` - 🔄 Ready to run (2,468 agents)

**Administrative Hierarchy Scripts**:
- `create_admin_hierarchies.py` - Original (failed on mega-countries)
- `create_admin_hierarchies_batched.py` - Batched version (crashed at country ~107)
- `create_admin_hierarchies_robust.py` - **FINAL VERSION** ✅ (5.6M relationships, all 254 countries)

**Linkers**:
- `link_wikidata_places_global.py` - GeoNames↔Wikidata linking
- `link_spatial_optimized.py` - Spatial proximity matching
- `link_direct_geonames_ids.py` - Direct ID linking
- `link_by_geography.py`, `link_hgis_to_lod.py` - Older linking scripts

**Parsers/Filters**:
- `parse_indian_affairs_rdf.py` - RDF → JSON (CIDOC-CRM ontology)
- `filter_wikidata_people.py`, `filter_wikidata_organizations.py` - Wikidata filtering
- `filter_wikidata_full_dump.py` - Geographic entity filtering

**Deployment Scripts**:
- `deploy_canadaneo4j.sh` - Main deployment script (VM)
- `deploy_simple.sh`, `deploy_final.sh` - Deployment variants
- `import_to_nibi.py`, `import_database_to_nibi.sh` - Nibi cluster scripts (deprecated)

**Utilities**:
- `check_database_stats.py` - Database statistics
- `export_database.py` - Export to JSON
- `review_database.py` - Query and review data
- `add_spatial_indexes.py`, `add_wikidata_indexes.py` - Index creation

### Data Files

**GeoNames** (main `/home/jic823/CanadaNeo4j/`):
- `allCountries.txt` (1.7GB uncompressed) - **SOURCE FILE FOR PHASE 1**
- `allCountries.zip` (396MB) - Original download
- Admin code files (admin1CodesASCII.txt, admin2Codes.txt)

**Wikidata Exports** (main `/home/jic823/CanadaNeo4j/`):
- `wikidata_canada_*.json`, `wikidata_canada_*.json.gz` - Canada-specific exports (legacy)

**Wikidata Filtered** (transfer `/home/jic823/CanadaNeo4j_transfer/`):
- `wikidata_geographic.json.gz` (613MB) - **SOURCE FOR PHASE 2** (11.6M entities)
- `wikidata_people.json.gz` (214MB) - **SOURCE FOR PHASE 2** (6M people)
- `wikidata_organizations.json.gz` (6MB) - **SOURCE FOR PHASE 2** (235K orgs)

**LINCS Pilot** (transfer `/home/jic823/CanadaNeo4j_transfer/`):
- `indian_affairs_agents.ttl` (12MB) - Original RDF data (Turtle format)
- `indian_affairs_agents.json` (2.7MB) - **Parsed JSON for import**
- `indian_affairs_agents_fixed.json` (2.7MB) - Fixed version

**Neo4j Exports** (transfer `/home/jic823/CanadaNeo4j_transfer/`):
- `places.json.gz` (123MB) - GeoNames place export
- `admin_divisions.json.gz` (5.5MB) - AdminDivision export
- `countries.json.gz` (781 bytes) - Country export

---

## File Movement Plan

### Consolidate LINCS Docs
```bash
cd /home/jic823/CanadaNeo4j
mkdir -p docs/lincs

# Copy from transfer folder
cp ../CanadaNeo4j_transfer/LINCS_INTEGRATION_PLAN.md docs/lincs/
cp ../CanadaNeo4j_transfer/LINCS_SUMMARY.md docs/lincs/
cp ../CanadaNeo4j_transfer/lincs_quickstart.py scripts/parsers/
```

### Organize Documentation
```bash
# Move planning docs
mv DATABASE_INFO.md EXPANSION_STRATEGY.md HISTORICAL_KG_PIPELINE.md docs/planning/
mv ENTITY_LINKING_*.md SPATIAL_LINKING_OPTIMIZED.md docs/planning/
mv WIKIDATA_*.md NIBI_*.md docs/planning/
mv LOADING_ORDER.md READY_TO_LINK.md docs/planning/
mv NEO4J_*.md STATUS.md STORAGE_*.md docs/planning/

# Copy deployment docs from transfer folder
cp ../CanadaNeo4j_transfer/ARBUTUS_DEPLOYMENT_PLAN.md docs/deployment/
cp ../CanadaNeo4j_transfer/DEPLOYMENT_*.md docs/deployment/
cp ../CanadaNeo4j_transfer/MONITOR_DEPLOYMENT.md docs/deployment/
```

### Organize Scripts
```bash
# Loaders
mv load_global_geonames.py load_wikidata_entities.py scripts/loaders/
mv load_indian_affairs_agents.py scripts/loaders/
mv load_post_offices.py load_from_cache.py scripts/loaders/

# Linkers
mv create_admin_hierarchies*.py scripts/linkers/
mv link_*.py scripts/linkers/
mv add_admin3_links.py add_spatial_indexes.py add_wikidata_indexes.py scripts/linkers/

# Parsers
mv parse_*.py filter_wikidata_*.py scripts/parsers/
mv fetch_*.py scripts/parsers/

# Utilities
mv check_*.py review_database.py export_database.py scripts/
mv test_*.py diagnose_*.py analyze_*.py scripts/
```

---

## What to Keep Where

### Keep in Main Project (`/home/jic823/CanadaNeo4j/`)
- **All documentation** (organized in docs/)
- **All Python scripts** (organized in scripts/)
- **Small data files** (<100MB)
- **Version-controlled files**

### Keep in Transfer Folder (`/home/jic823/CanadaNeo4j_transfer/`)
- **Large compressed exports** (*.json.gz for VM transfer)
- **Deployment snapshots**
- **CREDENTIALS.txt** (sensitive, not in git)
- **Temporary staging files**

### Delete/Archive
- Legacy files (old versions of scripts with "_OLD" suffix)
- Duplicate data files (keep only latest versions)
- Log files (admin3_links.log, spatial_index_setup.log, etc.) - move to logs/

---

## Quick Reference

### Where to Find Things

**"Where is the current status?"**
→ `/home/jic823/CanadaNeo4j/PROJECT_STATUS.md`

**"How do I load the Indian Affairs pilot?"**
→ `/home/jic823/CanadaNeo4j/scripts/loaders/load_indian_affairs_agents.py`
→ Data: `/home/jic823/CanadaNeo4j_transfer/indian_affairs_agents.json`

**"How do I integrate LINCS Historical Canadians?"**
→ `/home/jic823/CanadaNeo4j/docs/lincs/LINCS_INTEGRATION_PLAN.md`

**"What scripts created Phase 3?"**
→ `/home/jic823/CanadaNeo4j/scripts/linkers/create_admin_hierarchies_robust.py`

**"Where are the Wikidata data files?"**
→ `/home/jic823/CanadaNeo4j_transfer/wikidata_*.json.gz`

**"Where are the database credentials?"**
→ `/home/jic823/CanadaNeo4j_transfer/CREDENTIALS.txt` (sensitive)

---

## Reorganization Status

**Current**: Files scattered across two directories (legacy organization)
**Plan**: Consolidate docs and scripts to main project, keep large data in transfer folder
**Status**: ⚠️ Not yet executed (need user approval before moving files)

**Recommendation**: Execute consolidation plan to improve organization before LINCS integration

---

**Last Updated**: November 13, 2025
**Author**: Claude Code
**Purpose**: Clarify file organization for CanadaNeo4j project
