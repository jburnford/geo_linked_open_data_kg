#!/bin/bash
#SBATCH --account=def-jic823
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --job-name=neo4j_spatial_opt
#SBATCH --output=neo4j_spatial_opt_%j.out
#SBATCH --error=neo4j_spatial_opt_%j.err

echo "=== Optimized Spatial Linking ==="
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
echo "=== Step 2: Create Indexes ==="
echo "Creating indexes on WikidataPlace properties..."
cd "$CODE_DIR"
python3 add_wikidata_indexes.py

if [ $? -ne 0 ]; then
    echo "✗ Index creation failed"
    kill $NEO4J_PID 2>/dev/null
    exit 1
fi

echo ""
echo "=== Step 3: Current Database State ==="
cd "$NEO4J_HOME"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
MATCH (wp:WikidataPlace)
WITH count(wp) as total
OPTIONAL MATCH (linked:WikidataPlace)-[:SAME_AS]->()
WITH total, count(DISTINCT linked) as linked_same_as
RETURN total, linked_same_as, total - linked_same_as as unlinked;
CYPHER

echo ""
echo "=== Step 4: Run Optimized Spatial Linking ==="
echo "This processes 1000 places at a time per country"
echo "Target: <0.1 sec/place → ~320 hours for 11.5M places"
echo "Job will run for up to 24 hours, then can be resumed"
echo ""

cd "$CODE_DIR"

# Run the optimized linking script
python3 link_spatial_optimized.py

LINK_STATUS=$?

if [ $LINK_STATUS -eq 0 ]; then
    echo "✓ Spatial linking batch complete"
else
    echo "⚠ Spatial linking interrupted (can resume)"
fi

echo ""
echo "=== Step 5: Progress Statistics ==="
cd "$NEO4J_HOME"

echo ""
echo "WikidataPlace linking coverage:"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
MATCH (wp:WikidataPlace)
WITH count(wp) as total
OPTIONAL MATCH (same:WikidataPlace)-[:SAME_AS]->()
WITH total, count(DISTINCT same) as same_as
OPTIONAL MATCH (near:WikidataPlace)-[:NEAR]->()
WITH total, same_as, count(DISTINCT near) as near
OPTIONAL MATCH (located:WikidataPlace)-[:LOCATED_IN]->()
WITH total, same_as, near, count(DISTINCT located) as located_in
OPTIONAL MATCH (linked:WikidataPlace)--()
WITH total, same_as, near, located_in, count(DISTINCT linked) as linked
RETURN total, same_as, near, located_in, total - linked as unlinked;
CYPHER

echo ""
echo "Relationship counts:"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
MATCH ()-[r]->()
WITH type(r) as relType, count(r) as count
RETURN relType, count
ORDER BY count DESC
LIMIT 15;
CYPHER

echo ""
echo "=== Session Complete ==="
echo "End time: $(date)"
echo ""
echo "Note: Job can be resumed by resubmitting this script."
echo "Script automatically skips WikidataPlace nodes already linked."
echo ""

# Shutdown cleanly
echo "Shutting down Neo4j cleanly..."
kill -TERM $NEO4J_PID
wait $NEO4J_PID

echo "=== Job Complete ==="
