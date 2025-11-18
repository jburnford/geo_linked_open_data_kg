# Storage-Constrained Plan: Laptop Database

## Constraints
- **Windows drive**: 95% full, ~50 GB available
- **Cannot expand** without major cleanup
- **Goal**: Keep laptop database under 50 GB

## Laptop Database (Local - Keep Lean)

### **What to Load:**
1. ✓ **GeoNames places** (6.2M) - Already loaded (~5-10 GB)
2. ✓ **Wikidata geographic entities** (5-10M with P625) (~20-30 GB)
3. ✓ **Admin hierarchies** (current) (~minimal overhead)

**Total estimated size: 30-50 GB** ✓ Within budget

### **What NOT to Load:**
- ✗ People (~2M) - Would add ~10-20 GB
- ✗ Organizations (~500K) - Would add ~5-10 GB
- ✗ Events (~300K) - Would add ~3-5 GB
- ✗ Works (~1M) - Would add ~5-10 GB

## Nibi Cluster Database (Remote - Can Be Large)

### **Available Resources:**
- Storage: 251 GB free
- Can run Neo4j in container
- Access remotely when needed

### **What to Build There:**
1. **Full geographic database** (same as laptop)
2. **People** with place connections
3. **Organizations** (colonial companies, etc.)
4. **Events** (battles, treaties, etc.)
5. **Complete historical knowledge graph**

**Total size: 100-150 GB** ✓ Fits on Nibi

### **Access Pattern:**
- **Laptop**: Quick local queries for places, NER reconciliation
- **Nibi**: Complex queries involving people/orgs/events

## Wikidata Extraction Strategy

### **Extract Everything on Nibi** (Don't Delete Dump!)

**Pass 1: Geographic (P625)** ← Load on laptop
- Filter: Entities with coordinates
- Output: `wikidata_geographic.json.gz` (~5-15 GB)
- Load locally: ✓ Yes

**Pass 2: People**
- Filter: P31=Q5 + place connections
- Output: `wikidata_people.json.gz` (~1-3 GB)
- Load locally: ✗ No (keep on Nibi)
- Load on Nibi: ✓ Yes

**Pass 3: Organizations**
- Filter: P31=Q43229 + place connections
- Output: `wikidata_organizations.json.gz` (~300-600 MB)
- Load locally: ✗ No (keep on Nibi)
- Load on Nibi: ✓ Yes

**Pass 4: Events**
- Filter: Event types + P276 (location)
- Output: `wikidata_events.json.gz` (~100-300 MB)
- Load locally: ✗ No (keep on Nibi)
- Load on Nibi: ✓ Yes

### **Storage on Nibi After All Passes:**
- Raw dump: 145 GB
- Filtered outputs: ~10-20 GB total
- Neo4j database: ~100-150 GB
- **Total**: ~255-315 GB

**Problem**: Only 251 GB available on Nibi!

**Solution**:
1. Extract all passes (outputs = 20 GB)
2. Load into Neo4j on Nibi (~150 GB)
3. **Delete raw dump** (saves 145 GB)
4. Final: 170 GB used, 81 GB free ✓

## Timeline

### **Day 1: Geographic Entities**
1. Download completes (~5-6 hours from now)
2. Filter Pass 1 (P625) on Nibi (~6-10 hours)
3. Download filtered to laptop
4. Load into laptop Neo4j (~1-3 hours)
**Result**: Laptop database ready for NER/place queries

### **Day 2: People & Organizations**
1. Filter Pass 2 (people) on Nibi (~6-10 hours)
2. Filter Pass 3 (orgs) on Nibi (~6-10 hours)
3. Keep outputs on Nibi, don't download
**Result**: Extractions complete, stored on Nibi

### **Day 3: Events & Nibi Database Setup**
1. Filter Pass 4 (events) on Nibi (~6-10 hours)
2. Set up Neo4j container on Nibi
3. Load all filtered data into Nibi Neo4j
4. **Delete raw dump** (free up 145 GB)
**Result**: Full database on Nibi, accessible remotely

## Access Patterns

### **Laptop Database Use Cases:**
```cypher
// Find place by name (local, fast)
MATCH (p:Place {name: "Toronto"})
RETURN p

// Geographic proximity search (local, fast)
MATCH (p:Place)
WHERE distance(p.location, point({latitude: 43.65, longitude: -79.38})) < 10000
RETURN p.name, p.latitude, p.longitude

// Admin hierarchy traversal (local, fast)
MATCH (p:Place {name: "Seattle"})-[:LOCATED_IN_ADMIN1]->(state)
RETURN state.name
```

### **Nibi Database Use Cases (SSH tunnel):**
```cypher
// Find people born in a place
MATCH (person:Person)-[:BORN_IN]->(place:Place {name: "Mumbai"})
RETURN person.name, person.dateOfBirth

// Colonial company locations
MATCH (org:Organization {name: "Hudson's Bay Company"})-[:FOUNDED]->(place:Place)
RETURN place.name, place.inceptionDate, place.latitude, place.longitude

// Historical events at location
MATCH (event:Event)-[:OCCURRED_AT]->(place:Place)
WHERE place.countryCode = 'IN'
  AND event.instanceOfLabel CONTAINS 'battle'
RETURN event.name, place.name, event.date
```

## Neo4j on Nibi Setup

### **Option 1: Docker Container (Recommended)**
```bash
# On Nibi
cd ~/projects/def-jic823
mkdir neo4j_data

# Create docker-compose.yml
cat > docker-compose.yml << EOF
version: '3'
services:
  neo4j:
    image: neo4j:5.13-community
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - ./neo4j_data:/data
      - ./wikidata_filtered:/import
    environment:
      - NEO4J_AUTH=neo4j/password123
      - NEO4J_dbms_memory_heap_max__size=32G
      - NEO4J_dbms_memory_pagecache_size=64G
EOF

# Start Neo4j
docker-compose up -d
```

### **Option 2: Apptainer/Singularity (Cluster-Friendly)**
```bash
# Build container
singularity build neo4j.sif docker://neo4j:5.13-community

# Run with SLURM
sbatch neo4j_server.sh
```

### **Access from Laptop:**
```bash
# SSH tunnel to Nibi
ssh -L 7474:localhost:7474 -L 7687:localhost:7687 nibi

# Then access Neo4j Browser at http://localhost:7474
```

## Disk Space Monitoring

### **Laptop:**
```bash
# Check WSL usage
df -h /home/jic823/CanadaNeo4j

# Check Windows drive
df -h /mnt/c
```

### **Nibi:**
```bash
ssh nibi "df -h ~/projects/def-jic823"
```

### **Neo4j Database Size:**
```bash
# Laptop
du -sh /var/lib/neo4j/data/databases/neo4j

# Nibi
ssh nibi "du -sh ~/projects/def-jic823/neo4j_data"
```

## Benefits of This Approach

**Laptop:**
- ✓ Fast local access to geographic data
- ✓ Under 50 GB database size
- ✓ Perfect for NER reconciliation
- ✓ No network latency for place queries

**Nibi:**
- ✓ Can handle full historical knowledge graph
- ✓ 100+ GB database no problem
- ✓ Better hardware for complex queries
- ✓ Can be accessed remotely when needed

**Best of both worlds**: Lean local database for common tasks, full remote database for complex research.

## Summary

**Laptop Database**: ~40 GB
- 6.2M GeoNames places
- 5-10M Wikidata geographic entities
- Admin hierarchies
- **Use for**: Place lookup, geographic queries, NER

**Nibi Database**: ~150 GB
- Everything in laptop +
- 2M people with place connections
- 500K organizations
- 300K events
- **Use for**: Biographical research, organizational networks, historical events

**Storage constraints respected, maximum research capability achieved!**
