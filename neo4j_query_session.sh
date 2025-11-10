#!/bin/bash
#SBATCH --account=def-jic823
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=2:00:00
#SBATCH --job-name=neo4j_query_session
#SBATCH --output=neo4j_query_%j.out
#SBATCH --error=neo4j_query_%j.err

echo "=== Neo4j Query Session ==="
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

cd "$NEO4J_HOME"

echo "=== Starting Neo4j Server ==="
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
echo "=== Neo4j Query Session Active ==="
echo "Connection Details:"
echo "  Bolt: bolt://$(hostname):7687"
echo "  HTTP: http://$(hostname):7474"
echo "  Auth: neo4j/historicalkg2025"
echo ""
echo "Database Statistics:"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
MATCH (n)
WITH labels(n)[0] as label, count(*) as count
RETURN label, count
ORDER BY count DESC;
CYPHER

echo ""
echo "Session will remain active for 2 hours..."
echo "Connect from your local machine using port forwarding:"
echo "  ssh -L 7687:$(hostname):7687 -L 7474:$(hostname):7474 nibi"
echo ""

# Keep Neo4j running for the session duration (1 hour 50 minutes)
sleep 6600

# Shutdown cleanly
echo ""
echo "Session time limit reached. Shutting down Neo4j..."
kill -TERM $NEO4J_PID
wait $NEO4J_PID

echo ""
echo "=== Session Complete ==="
echo "End time: $(date)"
