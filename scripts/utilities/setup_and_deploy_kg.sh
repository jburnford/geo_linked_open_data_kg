#!/bin/bash
#SBATCH --account=def-jic823
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=48:00:00
#SBATCH --job-name=setup_kg
#SBATCH --output=setup_kg_%j.out
#SBATCH --error=setup_kg_%j.err

echo "=== Historical Knowledge Graph Setup & Deployment ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "Start time: $(date)"

# Load required modules
module load apptainer python/3.11

# Set directories
WORK_DIR="$HOME/projects/def-jic823/CanadaNeo4j"
NEO4J_CONTAINER="$WORK_DIR/neo4j.sif"
NEO4J_DATA_DIR="$WORK_DIR/neo4j_data"
NEO4J_LOGS_DIR="$WORK_DIR/neo4j_logs"
NEO4J_IMPORT_DIR="$WORK_DIR/neo4j_import"

cd "$WORK_DIR"

# Create persistent directories
mkdir -p "$NEO4J_DATA_DIR" "$NEO4J_LOGS_DIR" "$NEO4J_IMPORT_DIR"

echo "Directories:"
echo "  Work: $WORK_DIR"
echo "  Data: $NEO4J_DATA_DIR"
echo "  Logs: $NEO4J_LOGS_DIR"
echo "  Import: $NEO4J_IMPORT_DIR"

# Check if Neo4j container exists
if [ ! -f "$NEO4J_CONTAINER" ]; then
    echo "ERROR: Neo4j container not found at $NEO4J_CONTAINER"
    exit 1
fi

# Set Neo4j environment variables
export NEO4J_AUTH=neo4j/historicalkg2025
export NEO4J_ACCEPT_LICENSE_AGREEMENT=yes

echo ""
echo "=== Step 1: Starting Neo4j Container ==="
echo "Authentication: neo4j/historicalkg2025"
echo "Connection: bolt://localhost:7687"

# Start Neo4j with optimized memory settings for 64GB RAM
apptainer instance start \
    --bind "$NEO4J_DATA_DIR:/data" \
    --bind "$NEO4J_LOGS_DIR:/logs" \
    --bind "$NEO4J_IMPORT_DIR:/var/lib/neo4j/import" \
    --env NEO4J_AUTH="$NEO4J_AUTH" \
    --env NEO4J_ACCEPT_LICENSE_AGREEMENT=yes \
    --env NEO4J_dbms_memory_heap_initial__size=16g \
    --env NEO4J_dbms_memory_heap_max__size=16g \
    --env NEO4J_dbms_memory_pagecache_size=32g \
    "$NEO4J_CONTAINER" \
    neo4j_kg

if [ $? -eq 0 ]; then
    echo "✓ Neo4j instance started"
else
    echo "✗ Failed to start Neo4j"
    exit 1
fi

echo "Waiting for Neo4j to initialize (60 seconds)..."
sleep 60

# Test connection
echo "Testing Neo4j connection..."
for i in {1..12}; do
    if apptainer exec instance://neo4j_kg \
        cypher-shell -u neo4j -p historicalkg2025 \
        "RETURN 'connected' as status;" 2>/dev/null; then
        echo "✓ Neo4j is ready!"
        break
    fi
    echo "  Attempt $i/12 - waiting..."
    sleep 10
done

echo ""
echo "=== Step 2: Importing Database from Export ==="

# Install Python dependencies in local environment
pip3 install --user neo4j tqdm python-dotenv

# Run import script
echo "yes" | python3 import_to_nibi.py neo4j_export

if [ $? -eq 0 ]; then
    echo "✓ Database import complete"
else
    echo "✗ Import failed"
    exit 1
fi

echo ""
echo "=== Step 3: Building Administrative Hierarchies ==="

# Copy .env file for database connection
cat > .env << EOF
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=historicalkg2025
BATCH_SIZE=10000
EOF

# Run hierarchy builder
python3 create_admin_hierarchies_batched.py

if [ $? -eq 0 ]; then
    echo "✓ Admin hierarchies complete"
else
    echo "⚠ Admin hierarchies partially complete (can continue)"
fi

echo ""
echo "=== Step 4: Adding ADMIN3 Links ==="

python3 add_admin3_links.py

if [ $? -eq 0 ]; then
    echo "✓ ADMIN3 links complete"
else
    echo "⚠ ADMIN3 links partially complete (can continue)"
fi

echo ""
echo "=== Step 5: Verification ==="

apptainer exec instance://neo4j_kg \
    cypher-shell -u neo4j -p historicalkg2025 <<'CYPHER'
MATCH (n)
WITH labels(n) as labels, count(*) as count
RETURN labels[0] as label, count
ORDER BY count DESC;
CYPHER

apptainer exec instance://neo4j_kg \
    cypher-shell -u neo4j -p historicalkg2025 <<'CYPHER'
MATCH ()-[r]->()
WITH type(r) as relType, count(*) as count
RETURN relType, count
ORDER BY count DESC;
CYPHER

echo ""
echo "=== Knowledge Graph Ready! ==="
echo ""
echo "Connection Details:"
echo "  URL: bolt://localhost:7687"
echo "  Username: neo4j"
echo "  Password: historicalkg2025"
echo ""
echo "To connect from laptop:"
echo "  ssh -L 7687:localhost:7687 -L 7474:localhost:7474 nibi"
echo "  Then browse to: http://localhost:7474"
echo ""
echo "Database will remain running until:"
echo "  - Job time limit (48 hours): $(date -d '+48 hours')"
echo "  - Manual cancellation: scancel $SLURM_JOB_ID"
echo ""
echo "Next steps:"
echo "  1. Load Wikidata entities (after filtering completes)"
echo "  2. Connect UniversalNER grounding pipeline"
echo "  3. Build embedding layer"
echo ""

# Monitor logs and keep job alive
echo "Monitoring Neo4j logs..."
tail -f "$NEO4J_LOGS_DIR/debug.log" 2>/dev/null &
TAIL_PID=$!

# Wait for job duration
sleep 172800  # 48 hours

# Cleanup
kill $TAIL_PID 2>/dev/null
apptainer instance stop neo4j_kg

echo "=== Job Complete ==="
echo "End time: $(date)"
