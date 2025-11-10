#!/bin/bash
#SBATCH --account=def-jic823
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=6:00:00
#SBATCH --job-name=neo4j_load_wikidata
#SBATCH --output=neo4j_load_wikidata_%j.out
#SBATCH --error=neo4j_load_wikidata_%j.err

echo "=== Neo4j Wikidata Loading ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "Start time: $(date)"
echo ""

# Load Java module
module load java/17

# Set directories
WORK_DIR="$HOME/projects/def-jic823"
NEO4J_VERSION="neo4j-community-5.13.0"
NEO4J_HOME="$WORK_DIR/$NEO4J_VERSION"
CODE_DIR="$WORK_DIR/CanadaNeo4j"
FILTERED_DIR="$WORK_DIR/wikidata/filtered"

cd "$NEO4J_HOME"

echo "=== Step 1: Start Neo4j Server ==="
echo "Starting Neo4j in background..."

# Start Neo4j in background
bin/neo4j console &
NEO4J_PID=$!

echo "Neo4j PID: $NEO4J_PID"
echo "Waiting for startup (60 seconds)..."
sleep 60

# Test connection
echo "Testing connection..."
for i in {1..12}; do
    if bin/cypher-shell -u neo4j -p historicalkg2025 "RETURN 1;" 2>/dev/null; then
        echo "✓ Neo4j is ready!"
        CONNECTION_SUCCESS=true
        break
    fi
    echo "  Attempt $i/12 - waiting 10 seconds..."
    sleep 10
done

if [ -z "$CONNECTION_SUCCESS" ]; then
    echo "✗ Failed to connect to Neo4j"
    exit 1
fi

echo ""
echo "=== Step 2: Check Current Database State ==="
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
MATCH (n)
WITH labels(n)[0] as label, count(*) as count
RETURN label, count
ORDER BY count DESC
LIMIT 10;
CYPHER

echo ""
echo "=== Step 3: Load Wikidata Entities ==="
echo "Filtered data location: $FILTERED_DIR"
echo ""
echo "Files to load:"
ls -lh "$FILTERED_DIR"/*.json.gz

cd "$CODE_DIR"

# Install Python dependencies if needed
pip3 install --user neo4j tqdm 2>&1 | grep -v "already satisfied" || true

# Set environment variable for script
export FILTERED_DIR="$FILTERED_DIR"

echo ""
echo "Starting Wikidata load (estimated: 2-4 hours)..."
python3 load_wikidata_entities.py

if [ $? -eq 0 ]; then
    echo "✓ Wikidata loading complete"
else
    echo "✗ Wikidata loading failed"
    kill $NEO4J_PID 2>/dev/null
    exit 1
fi

echo ""
echo "=== Step 4: Final Database Verification ==="
cd "$NEO4J_HOME"

echo ""
echo "Node counts:"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
MATCH (n)
WITH labels(n)[0] as label, count(*) as count
RETURN label, count
ORDER BY count DESC;
CYPHER

echo ""
echo "Index status:"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
SHOW INDEXES;
CYPHER

echo ""
echo "Sample Person nodes:"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
MATCH (p:Person)
RETURN p.name, p.birthDate, p.deathDate
LIMIT 5;
CYPHER

echo ""
echo "Sample Organization nodes:"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
MATCH (o:Organization)
RETURN o.name, o.inceptionDate
LIMIT 5;
CYPHER

echo ""
echo "=== Import Complete ==="
echo "✓ All Wikidata entities loaded"
echo "✓ Database ready for queries"
echo ""
echo "Database Statistics:"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
MATCH (n)
RETURN count(n) as totalNodes;
CYPHER

echo ""
echo "Connection Details:"
echo "  Bolt: bolt://$(hostname):7687"
echo "  HTTP: http://$(hostname):7474"
echo "  Auth: neo4j/historicalkg2025"
echo ""

# Keep Neo4j running briefly for verification
echo "Keeping Neo4j running for 5 minutes for verification..."
sleep 300

# Shutdown cleanly
echo "Shutting down Neo4j cleanly..."
kill -TERM $NEO4J_PID
wait $NEO4J_PID

echo ""
echo "=== Job Complete ==="
echo "End time: $(date)"
