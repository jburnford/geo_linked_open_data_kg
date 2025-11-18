# Geographic Linked Open Data Knowledge Graph

A comprehensive knowledge graph combining **GeoNames gazetteer** (6.2M places), **Wikidata entities** (17.8M entities), and **LINCS historical data** for Named Entity Recognition, historical research, and linked open data applications.

![Project Status](https://img.shields.io/badge/Status-Phase%203%20In%20Progress-yellow)
![Nodes](https://img.shields.io/badge/Nodes-24M+-blue)
![Database](https://img.shields.io/badge/Neo4j-5.13-green)

## Overview

**Scale**: 24+ million nodes across geographic entities, people, organizations, and administrative divisions
**Platform**: Neo4j 5.13 Community Edition on Arbutus Cloud VM
**Purpose**: Entity reconciliation, geographic context, historical research, linked open data integration

## Current Status

### ✅ Phase 1: GeoNames Import (COMPLETE)
- **6,252,512 places** from GeoNames global gazetteer
- **509,253 administrative divisions** (states, provinces, counties, districts)
- **254 countries** with full metadata
- **Spatial indexes** optimized for sub-100ms queries

### ✅ Phase 2: Wikidata Import (COMPLETE)
- **11,600,000 geographic entities** (WikidataPlace nodes with QIDs)
- **6,000,000 people** with biographical data
- **235,000 organizations** with temporal and location data
- **Authority control IDs**: VIAF, GND, LOC for library integration

### 🔄 Phase 3: Administrative Hierarchies (IN PROGRESS - 39%)
- Building hierarchical relationships: `Place → AdminDivision → Country`
- **Status**: 98/254 countries processed
- **Estimated completion**: 8-10 hours
- **Major achievement**: Successfully processed mega-countries (China: 883K places, India: 557K places)

## Architecture

### Data Sources

1. **GeoNames**: Global geographic gazetteer (allCountries.txt, admin codes)
2. **Wikidata**: Filtered dumps for places, people, organizations
3. **LINCS**: Linked Infrastructure for Networked Cultural Scholarship (Canadian historical data)

### Neo4j Data Model

#### Core Node Types

- **`Place`**: GeoNames entities with coordinates, population, feature codes
- **`WikidataPlace`**: Geographic entities with Q-numbers and linked data properties
- **`Person`**: Biographical data (birth/death dates, occupations, affiliations)
- **`Organization`**: Institutions with locations and temporal data
- **`AdminDivision`**: Administrative regions (ADM1-ADM4)
- **`Country`**: Country codes and metadata

#### Key Relationships

- `(Place)-[:LOCATED_IN_ADMIN1|ADMIN2|ADMIN3|ADMIN4]->(AdminDivision)`
- `(AdminDivision)-[:PART_OF]->(AdminDivision|Country)`
- `(Person)-[:BORN_IN|DIED_IN]->(WikidataPlace)`
- `(Organization)-[:LOCATED_IN]->(WikidataPlace)`

## Deployment

**Infrastructure**: Arbutus Cloud VM (Digital Research Alliance of Canada)
**Resources**: 32GB RAM, 4 vCPUs, 500GB storage
**Connection**: See [CREDENTIALS_TEMPLATE.md](CREDENTIALS_TEMPLATE.md) for setup

### Database Access

```bash
# Remote connection (requires credentials)
NEO4J_URI=bolt://206.12.90.118:7687
NEO4J_DATABASE=canadaneo4j

# Local development with .env file
python3 your_script.py  # Auto-loads from .env
```

## Use Cases

### 1. Named Entity Recognition (NER) Reconciliation

Resolve ambiguous place names from historical documents:

```cypher
// Find "Regina" in Saskatchewan context
MATCH (p:Place {name: 'Regina'})-[:LOCATED_IN_ADMIN1]->(a:AdminDivision {name: 'Saskatchewan'})
RETURN p.geonameId, p.name, p.latitude, p.longitude, p.population
```

### 2. Spatial Queries

Find entities within geographic areas:

```cypher
// Places within 50km of Ottawa
MATCH (ottawa:Place {name: 'Ottawa', countryCode: 'CA'})
MATCH (nearby:Place)
WHERE point.distance(ottawa.location, nearby.location) < 50000
RETURN nearby.name, point.distance(ottawa.location, nearby.location) AS distance
ORDER BY distance LIMIT 100
```

### 3. Administrative Hierarchies

Traverse geographic containment:

```cypher
// Full hierarchy for Toronto
MATCH path = (toronto:Place {name: 'Toronto'})-[:LOCATED_IN_ADMIN1|PART_OF*]->(c:Country)
RETURN [n IN nodes(path) | n.name] AS hierarchy
```

### 4. Biographical Research

Link people to places via Wikidata:

```cypher
// Find people born in Canadian places
MATCH (p:Person)-[:BORN_IN]->(wp:WikidataPlace)
MATCH (place:Place {geonameId: wp.geonamesId})
WHERE place.countryCode = 'CA'
RETURN p.name, place.name, p.birthDate
LIMIT 100
```

## Project Structure

```
geo_linked_open_data_kg/
├── README.md                          # This file
├── PROJECT_STATUS.md                  # Detailed status (primary documentation)
├── FILE_ORGANIZATION.md               # File locations and organization plan
├── CREDENTIALS_TEMPLATE.md            # Credentials setup guide
├── requirements.txt                   # Python dependencies
│
├── docs/                              # Documentation (planned reorganization)
│   ├── planning/                      # Planning documents
│   ├── deployment/                    # Deployment guides
│   └── lincs/                         # LINCS integration docs
│
├── scripts/                           # Python scripts (planned reorganization)
│   ├── loaders/                       # Data loading scripts
│   ├── linkers/                       # Relationship builders
│   └── parsers/                       # Data transformation scripts
│
├── data/                              # Data files (not in git)
│   ├── raw/                           # Original downloads
│   └── processed/                     # Transformed data
│
├── load_global_geonames.py            # Phase 1 loader
├── load_wikidata_entities.py          # Phase 2 loader
├── create_admin_hierarchies_robust.py # Phase 3 (current)
└── .env                               # Credentials (not in git)
```

## Documentation

- **[PROJECT_STATUS.md](PROJECT_STATUS.md)**: Comprehensive project status with metrics, challenges, and next steps
- **[FILE_ORGANIZATION.md](FILE_ORGANIZATION.md)**: Guide to repository structure and file locations
- **[CREDENTIALS_TEMPLATE.md](CREDENTIALS_TEMPLATE.md)**: Setup guide for database access
- **Planning docs**: See `docs/planning/` (after reorganization) for detailed strategy documents

## Getting Started

### Prerequisites

- Python 3.8+
- Neo4j connection credentials (see CREDENTIALS_TEMPLATE.md)
- Required packages: `pip install -r requirements.txt`

### Setup

1. **Clone the repository**:
   ```bash
   git clone git@github.com:jburnford/geo_linked_open_data_kg.git
   cd geo_linked_open_data_kg
   ```

2. **Create credentials file**:
   ```bash
   cp CREDENTIALS_TEMPLATE.md .env
   # Edit .env with actual credentials
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Test connection**:
   ```bash
   python3 review_database.py  # View database statistics
   ```

### Query Examples

See [PROJECT_STATUS.md](PROJECT_STATUS.md#research-capabilities-once-complete) for comprehensive query examples.

## Roadmap

### Completed
- ✅ Phase 1: GeoNames global import (6.2M places)
- ✅ Phase 2: Wikidata entity import (17.8M entities)

### In Progress
- 🔄 Phase 3: Administrative hierarchies (39% complete)

### Planned
- 📋 Phase 4: Indian Affairs pilot integration (2,468 agents)
- 📋 Phase 5: LINCS Historical Canadians (400K+ biographical entries)
- 📋 Phase 6: Graph-RAG integration with GPT-OSS-120B

## Performance

- **Query performance**: <100ms for simple lookups with spatial indexes
- **Database size**: ~180GB (after Phase 2)
- **Scalability**: Successfully handles mega-countries (China: 883K places, India: 557K places)

## Technical Achievements

1. **Three-tier adaptive chunking**: Handles countries of any size (normal/admin1/admin2 strategies)
2. **Memory optimization**: 10GB transaction pool for large-scale relationship creation
3. **Spatial indexing**: Optimized point queries with Neo4j native geometry
4. **Resume capability**: Can restart processing without losing progress

## Contributing

This is a research project. For questions or collaboration inquiries, see the project documentation.

## License

**Data Licenses**:
- GeoNames: Creative Commons Attribution 4.0 (CC BY 4.0)
- Wikidata: Creative Commons CC0 (public domain)
- LINCS: Various (see individual datasets)

**Code License**: TBD (specify your license)

## Citation

If you use this knowledge graph in your research, please cite:

```bibtex
@software{geo_lod_kg_2025,
  title = {Geographic Linked Open Data Knowledge Graph},
  author = {Burnford, J.},
  year = {2025},
  url = {https://github.com/jburnford/geo_linked_open_data_kg}
}
```

## Resources

- **GeoNames**: https://www.geonames.org/
- **Wikidata**: https://www.wikidata.org/
- **LINCS Project**: https://lincsproject.ca/
- **Neo4j Documentation**: https://neo4j.com/docs/

---

**For detailed status and monitoring**, see [PROJECT_STATUS.md](PROJECT_STATUS.md)
**For credentials setup**, see [CREDENTIALS_TEMPLATE.md](CREDENTIALS_TEMPLATE.md)
**For file organization**, see [FILE_ORGANIZATION.md](FILE_ORGANIZATION.md)

**Last Updated**: November 18, 2025
