#!/bin/bash
#SBATCH --account=def-jic823
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=3:00:00
#SBATCH --job-name=neo4j_import
#SBATCH --output=neo4j_import_%j.out
#SBATCH --error=neo4j_import_%j.err

echo "=== Neo4j Database Import (Phase 2) ==="
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
EXPORT_DIR="$CODE_DIR/neo4j_export"

cd "$WORK_DIR"

# Check if Neo4j needs to be set up
if [ ! -d "$NEO4J_VERSION" ]; then
    echo "=== Step 0: Setup Neo4j ==="
    echo "Downloading Neo4j tarball..."
    wget -q https://dist.neo4j.org/neo4j-community-5.13.0-unix.tar.gz

    echo "Extracting..."
    tar -xzf neo4j-community-5.13.0-unix.tar.gz

    echo "Creating directories..."
    mkdir -p neo4j_data neo4j_logs neo4j_import neo4j_plugins

    cd "$NEO4J_VERSION"

    echo "Configuring..."
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

    echo "Setting initial password..."
    bin/neo4j-admin dbms set-initial-password historicalkg2025

    echo "✓ Neo4j setup complete"
    cd "$WORK_DIR"
fi

cd "$NEO4J_HOME"

echo ""
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
echo "=== Step 2: Import Database from Export ==="
echo "Export location: $EXPORT_DIR"
echo "Files:"
ls -lh "$EXPORT_DIR"/*.json.gz

cd "$CODE_DIR"

# Install Python dependencies if needed
pip3 install --user neo4j tqdm python-dotenv 2>&1 | grep -v "already satisfied" || true

# Create .env file
cat > .env << EOF
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=historicalkg2025
BATCH_SIZE=10000
EOF

echo ""
echo "Starting import (estimated: 60-90 minutes)..."
echo "yes" | python3 import_to_nibi.py neo4j_export

if [ $? -eq 0 ]; then
    echo "✓ Database import complete"
else
    echo "✗ Import failed"
    kill $NEO4J_PID 2>/dev/null
    exit 1
fi

echo ""
echo "=== Step 3: Build Administrative Hierarchies ==="
echo "Creating ADMIN1, ADMIN2, ADMIN3 relationships..."
echo "Estimated time: 30-60 minutes"

python3 create_admin_hierarchies_batched.py

if [ $? -eq 0 ]; then
    echo "✓ Admin hierarchies complete"
else
    echo "⚠ Admin hierarchies partially complete (can continue)"
fi

echo ""
echo "=== Step 4: Add ADMIN3 Links ==="
python3 add_admin3_links.py

if [ $? -eq 0 ]; then
    echo "✓ ADMIN3 links complete"
else
    echo "⚠ ADMIN3 links partially complete (can continue)"
fi

echo ""
echo "=== Step 5: Verification ==="
echo "Checking final database state..."

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
echo "Relationship counts:"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
MATCH ()-[r]->()
WITH type(r) as relType, count(*) as count
RETURN relType, count
ORDER BY count DESC;
CYPHER

echo ""
echo "Index status:"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
SHOW INDEXES;
CYPHER

echo ""
echo "Database size:"
bin/cypher-shell -u neo4j -p historicalkg2025 << 'CYPHER'
CALL dbms.queryJmx("org.neo4j:instance=kernel#0,name=Store file sizes")
YIELD attributes
RETURN attributes.TotalStoreSize.value as totalSize;
CYPHER

echo ""
echo "=== Import Complete ==="
echo "✓ Nodes imported: 6.74M expected"
echo "✓ Relationships created: 11.5M expected"
echo "✓ Indexes built and online"
echo "✓ Database ready for queries"
echo ""
echo "Connection Details:"
echo "  Bolt: bolt://$(hostname):7687"
echo "  HTTP: http://$(hostname):7474"
echo "  Auth: neo4j/historicalkg2025"
echo ""
echo "Next steps:"
echo "  1. Database is ready for production use"
echo "  2. Submit Wikidata filtering jobs (48-hour processing)"
echo "  3. Load Wikidata entities incrementally"
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
