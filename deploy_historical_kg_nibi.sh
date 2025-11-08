#!/bin/bash
#SBATCH --account=def-jic823
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=48:00:00
#SBATCH --job-name=historical_kg
#SBATCH --output=historical_kg_%j.out
#SBATCH --error=historical_kg_%j.err

echo "=== Historical Knowledge Graph Deployment ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "Start time: $(date)"

# Load required modules
module load apptainer python/3.11

# Set directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEO4J_CONTAINER="$HOME/projects/def-jic823/CanadaNeo4j/neo4j.sif"
NEO4J_DATA_DIR="$HOME/projects/def-jic823/CanadaNeo4j/neo4j_data"
NEO4J_LOGS_DIR="$HOME/projects/def-jic823/CanadaNeo4j/neo4j_logs"
NEO4J_IMPORT_DIR="$HOME/projects/def-jic823/CanadaNeo4j/neo4j_import"

# Create persistent directories in project space
mkdir -p "$NEO4J_DATA_DIR" "$NEO4J_LOGS_DIR" "$NEO4J_IMPORT_DIR"

echo "Directories:"
echo "  Data: $NEO4J_DATA_DIR"
echo "  Logs: $NEO4J_LOGS_DIR"
echo "  Import: $NEO4J_IMPORT_DIR"

# Check if Neo4j container exists
if [ ! -f "$NEO4J_CONTAINER" ]; then
    echo "ERROR: Neo4j container not found at $NEO4J_CONTAINER"
    echo "Please run: sbatch build_neo4j_container.sh first"
    exit 1
fi

# Set Neo4j environment variables
export NEO4J_AUTH=neo4j/historicalkg2025
export NEO4J_ACCEPT_LICENSE_AGREEMENT=yes

echo "=== Starting Neo4j Container ==="
echo "Authentication: neo4j/historicalkg2025"
echo "Connection: bolt://localhost:7687"

# Start Neo4j in background with proper memory settings
apptainer exec \
    --bind "$NEO4J_DATA_DIR:/data" \
    --bind "$NEO4J_LOGS_DIR:/logs" \
    --bind "$NEO4J_IMPORT_DIR:/var/lib/neo4j/import" \
    --env NEO4J_AUTH="$NEO4J_AUTH" \
    --env NEO4J_ACCEPT_LICENSE_AGREEMENT=yes \
    --env NEO4J_dbms_memory_heap_initial__size=16g \
    --env NEO4J_dbms_memory_heap_max__size=16g \
    --env NEO4J_dbms_memory_pagecache_size=32g \
    "$NEO4J_CONTAINER" \
    neo4j start

echo "Waiting for Neo4j to start (60 seconds)..."
sleep 60

# Verify Neo4j is running
echo "Testing connection..."
for i in {1..12}; do
    if apptainer exec \
        --bind "$NEO4J_DATA_DIR:/data" \
        --env NEO4J_AUTH="$NEO4J_AUTH" \
        "$NEO4J_CONTAINER" \
        cypher-shell -u neo4j -p historicalkg2025 "RETURN 'connected' as status;" 2>/dev/null; then
        echo "✓ Neo4j is ready!"
        break
    fi
    echo "Waiting for Neo4j... attempt $i/12"
    sleep 10
done

# Run test query
echo "=== Database Status ==="
apptainer exec \
    --bind "$NEO4J_DATA_DIR:/data" \
    --env NEO4J_AUTH="$NEO4J_AUTH" \
    "$NEO4J_CONTAINER" \
    cypher-shell -u neo4j -p historicalkg2025 \
    "CALL dbms.components() YIELD name, versions, edition RETURN name, versions[0] as version, edition;"

echo ""
echo "=== Neo4j Running ==="
echo "Connection URL: bolt://localhost:7687"
echo "Username: neo4j"
echo "Password: historicalkg2025"
echo ""
echo "To load data, use the Python loading scripts in this directory"
echo "The database will remain running for the duration of this job (48 hours)"
echo ""
echo "Monitor with: tail -f historical_kg_$SLURM_JOB_ID.out"
echo ""

# Keep job alive to maintain Neo4j
echo "Neo4j will run until: $(date -d '+48 hours')"
echo "Press Ctrl+C or scancel $SLURM_JOB_ID to stop"

# Monitor Neo4j logs
tail -f "$NEO4J_LOGS_DIR/debug.log" 2>/dev/null &
TAIL_PID=$!

# Wait for job duration or manual cancellation
sleep 172800  # 48 hours

# Cleanup
kill $TAIL_PID 2>/dev/null
echo "=== Job Complete ==="
echo "End time: $(date)"
