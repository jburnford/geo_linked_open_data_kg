#!/bin/bash
#SBATCH --account=def-jic823
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=8:00:00
#SBATCH --job-name=neo4j_wikidata_linking
#SBATCH --output=neo4j_wikidata_linking_%j.out
#SBATCH --error=neo4j_wikidata_linking_%j.err

echo "=== WikidataPlace → Place Linking ===="
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
echo "=== Step 2: Check Current Database State ==="
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
MATCH (n)
WITH labels(n)[0] as label, count(*) as count
RETURN label, count
ORDER BY count DESC
LIMIT 10;
CYPHER

echo ""
echo "=== Step 3: Run WikidataPlace Linking ==="
echo "This will take 4-8 hours for 11.5M WikidataPlace nodes"
echo ""

cd "$CODE_DIR"

# Install Python dependencies if needed
pip3 install --user neo4j tqdm 2>&1 | grep -v "already satisfied" || true

# Run the linking script
python3 link_wikidata_places_global.py

if [ $? -eq 0 ]; then
    echo "✓ WikidataPlace linking complete"
else
    echo "✗ WikidataPlace linking failed"
    kill $NEO4J_PID 2>/dev/null
    exit 1
fi

echo ""
echo "=== Step 4: Final Verification ==="
cd "$NEO4J_HOME"

echo ""
echo "Relationship counts:"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
MATCH ()-[r]->()
WITH type(r) as relType, count(r) as count
RETURN relType, count
ORDER BY count DESC
LIMIT 20;
CYPHER

echo ""
echo "Sample WikidataPlace → Place links:"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
MATCH (wp:WikidataPlace)-[r:SAME_AS]->(p:Place)
RETURN wp.name, p.name, r.confidence, r.distance_km
LIMIT 5;
CYPHER

echo ""
echo "=== Linking Complete ==="
echo "✓ All WikidataPlace nodes linked to Place nodes"
echo ""

# Shutdown cleanly
echo "Shutting down Neo4j cleanly..."
kill -TERM $NEO4J_PID
wait $NEO4J_PID

echo ""
echo "=== Job Complete ==="
echo "End time: $(date)"
