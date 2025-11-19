# Historical Migration Patterns Visualization

An interactive map showing birth-to-death migration patterns from the Geographic Linked Open Data Knowledge Graph.

## View the Visualization

**[Open Interactive Map](index.html)**

## Data

- **5,196 people** with complete birth and death location data
- **1,250 unique birth locations** worldwide
- **1,019 unique death locations**
- **390 significant migration flows** (2+ people per route)

## Key Patterns

### Immigration to Canada (Top Sources)
1. United Kingdom → Canada: 971 people
2. United States → Canada: 360 people
3. France → Canada: 346 people
4. Ireland → Canada: 177 people

### Emigration from Canada
1. Canada → United States: 131 people
2. Canada → France: 62 people
3. Canada → United Kingdom: 29 people

### Top Destinations
- Montréal: 1,099 people
- Québec City: 533 people
- Saint John, NB: 132 people
- St. John's, NL: 127 people
- Victoria, BC: 121 people

## Map Legend

- **Green markers**: Birth places (size indicates number of births)
- **Red markers**: Death places (size indicates number of deaths)
- **Lines**: Migration flows
  - Blue = to Canada
  - Orange = to Asia
  - Purple = to Europe
  - Red = to USA
  - Line thickness = number of people

## Data Source

This visualization is generated from the [Geographic Linked Open Data Knowledge Graph](https://github.com/jburnford/geo_linked_open_data_kg), which combines:
- GeoNames gazetteer (6.2M places)
- LINCS Historical Canadians data (14K+ biographical entries)
- Wikidata entities

## About

Created with Neo4j graph database and Plotly visualization library. The data represents historical migration patterns primarily from the 19th and early 20th centuries.

---

**Project**: [geo_linked_open_data_kg](https://github.com/jburnford/geo_linked_open_data_kg)
