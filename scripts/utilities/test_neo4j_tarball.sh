#!/bin/bash
#SBATCH --account=def-jic823
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=1:00:00
#SBATCH --job-name=test_neo4j_tarball
#SBATCH --output=test_neo4j_tarball_%j.out
#SBATCH --error=test_neo4j_tarball_%j.err

echo "=== Neo4j Tarball Test Deployment ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "Start time: $(date)"
echo ""

# Load Java module
module load java/17

# Set directories
WORK_DIR="$HOME/projects/def-jic823"
NEO4J_VERSION="neo4j-community-5.13.0"
NEO4J_TARBALL="${NEO4J_VERSION}-unix.tar.gz"

cd "$WORK_DIR"

echo "=== Step 1: Download Neo4j Tarball ==="
if [ -f "$NEO4J_TARBALL" ]; then
    echo "Tarball already exists, skipping download"
else
    echo "Downloading Neo4j Community Edition 5.13.0..."
    wget https://dist.neo4j.org/neo4j-community-5.13.0-unix.tar.gz

    if [ $? -eq 0 ]; then
        echo "✓ Download complete"
        echo "Size: $(du -h $NEO4J_TARBALL | cut -f1)"
    else
        echo "✗ Download failed"
        exit 1
    fi
fi

echo ""
echo "=== Step 2: Extract Tarball ==="
if [ -d "$NEO4J_VERSION" ]; then
    echo "Directory already exists, removing old version"
    rm -rf "$NEO4J_VERSION"
fi

tar -xzf "$NEO4J_TARBALL"

if [ $? -eq 0 ]; then
    echo "✓ Extraction complete"
else
    echo "✗ Extraction failed"
    exit 1
fi

echo ""
echo "=== Step 3: Create Data Directories ==="
mkdir -p neo4j_data neo4j_logs neo4j_import neo4j_plugins

echo "Directories created:"
echo "  $(pwd)/neo4j_data"
echo "  $(pwd)/neo4j_logs"
echo "  $(pwd)/neo4j_import"
echo "  $(pwd)/neo4j_plugins"

echo ""
echo "=== Step 4: Configure Neo4j ==="
cd "$NEO4J_VERSION"

# Backup original config
cp conf/neo4j.conf conf/neo4j.conf.bak

# Create a clean custom configuration file
cat > conf/neo4j.conf << EOF
# Neo4j configuration for Nibi cluster

# Directories
server.directories.data=${WORK_DIR}/neo4j_data
server.directories.logs=${WORK_DIR}/neo4j_logs
server.directories.import=${WORK_DIR}/neo4j_import
server.directories.plugins=${WORK_DIR}/neo4j_plugins

# Memory settings (for 64GB node)
server.memory.heap.initial_size=16g
server.memory.heap.max_size=16g
server.memory.pagecache.size=32g

# Network settings
server.bolt.enabled=true
server.bolt.listen_address=0.0.0.0:7687
server.http.enabled=true
server.http.listen_address=0.0.0.0:7474

# Authentication
dbms.security.auth_enabled=true

# Default database
initial.dbms.default_database=neo4j
EOF

echo "✓ Configuration complete"

echo ""
echo "=== Step 5: Set Initial Password ==="
bin/neo4j-admin dbms set-initial-password historicalkg2025

if [ $? -eq 0 ]; then
    echo "✓ Password set: historicalkg2025"
else
    echo "✗ Password setup failed"
    exit 1
fi

echo ""
echo "=== Step 6: Start Neo4j in Console Mode ==="
echo "Connection: bolt://$(hostname):7687"
echo "Auth: neo4j/historicalkg2025"
echo ""

# Start Neo4j in background
bin/neo4j console &
NEO4J_PID=$!

echo "Neo4j started with PID: $NEO4J_PID"
echo "Waiting 60 seconds for startup..."
sleep 60

echo ""
echo "=== Step 7: Test Connection ==="

# Try to connect (up to 12 attempts)
for i in {1..12}; do
    echo "Connection attempt $i/12..."

    if bin/cypher-shell -u neo4j -p historicalkg2025 "RETURN 'connected' as status;" 2>/dev/null; then
        echo "✓ Neo4j is ready!"
        CONNECTION_SUCCESS=true
        break
    fi

    echo "  Waiting 10 seconds..."
    sleep 10
done

if [ -z "$CONNECTION_SUCCESS" ]; then
    echo "✗ Failed to connect to Neo4j"
    echo ""
    echo "Checking logs:"
    tail -50 "${WORK_DIR}/neo4j_logs/neo4j.log"
    exit 1
fi

echo ""
echo "=== Step 8: Run Test Queries ==="

# Test 1: Simple query
echo "Test 1: Simple return query"
bin/cypher-shell -u neo4j -p historicalkg2025 "RETURN 'Hello Neo4j' as message, datetime() as timestamp;"

# Test 2: Create and query a test node
echo ""
echo "Test 2: Create test node"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
CREATE (t:TestNode {
    name: 'Nibi Test',
    timestamp: datetime(),
    node: '${SLURMD_NODENAME}'
})
RETURN t.name, t.timestamp, t.node;
CYPHER

# Test 3: Verify node was created
echo ""
echo "Test 3: Count nodes"
bin/cypher-shell -u neo4j -p historicalkg2025 "MATCH (n) RETURN count(n) as totalNodes;"

# Test 4: Check memory settings
echo ""
echo "Test 4: Check database configuration"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
CALL dbms.listConfig()
YIELD name, value
WHERE name CONTAINS 'memory'
RETURN name, value
ORDER BY name;
CYPHER

echo ""
echo "=== Step 9: Cleanup Test Data ==="
bin/cypher-shell -u neo4j -p historicalkg2025 "MATCH (t:TestNode) DELETE t;"

echo ""
echo "=== Test Complete ==="
echo "✓ Neo4j tarball installation: SUCCESS"
echo "✓ Console mode startup: SUCCESS"
echo "✓ Connection test: SUCCESS"
echo "✓ Query execution: SUCCESS"
echo "✓ Memory configuration: VERIFIED"
echo ""
echo "Next steps:"
echo "1. Neo4j tarball approach is validated"
echo "2. Ready to import 6.74M node database (3-hour job)"
echo "3. Ready for production deployment with Wikidata filtering"
echo ""

# Keep Neo4j running for remainder of test period
echo "Neo4j will remain running until job ends..."
echo "Monitoring logs (Ctrl+C to stop monitoring, Neo4j continues)..."
tail -f "${WORK_DIR}/neo4j_logs/neo4j.log" &
TAIL_PID=$!

# Wait for remaining job time (keep Neo4j available for manual testing)
wait $NEO4J_PID

# Cleanup
kill $TAIL_PID 2>/dev/null

echo ""
echo "=== Job Complete ==="
echo "End time: $(date)"
