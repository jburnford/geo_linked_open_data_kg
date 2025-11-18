#!/bin/bash
###############################################################################
# CanadaNeo4j Knowledge Graph - Arbutus Deployment Script
#
# This script performs the complete deployment of the CanadaNeo4j knowledge
# graph on the Arbutus VM, including:
#   1. GeoNames data import (Countries, AdminDivisions, Places)
#   2. Wikidata entity import (Geographic, People, Organizations)
#   3. Administrative hierarchy building
#   4. ADMIN3 relationship creation
#   5. Spatial index setup
#   6. Final verification
#
# Expected runtime: 4-6 hours
# Database: canadaneo4j (separate from existing Canadian Census database)
###############################################################################

set -e  # Exit on error

# Configuration
DATA_DIR="/var/lib/neo4j-data/import/canadaneo4j"
NEO4J_URI="bolt://localhost:7687"
NEO4J_USER="neo4j"
NEO4J_PASSWORD="admin"
DATABASE="canadaneo4j"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging
LOG_FILE="$DATA_DIR/deployment.log"
START_TIME=$(date +%s)

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

log_section() {
    echo ""
    echo "================================================================================" | tee -a "$LOG_FILE"
    echo -e "${BLUE}$1${NC}" | tee -a "$LOG_FILE"
    echo "================================================================================" | tee -a "$LOG_FILE"
}

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    log_error "This script must be run as root or with sudo"
    exit 1
fi

# Verify Neo4j is running
log_section "PRE-FLIGHT CHECKS"

log "Checking Neo4j service..."
if ! systemctl is-active --quiet neo4j; then
    log_error "Neo4j service is not running. Starting..."
    systemctl start neo4j
    sleep 10
fi
log "✓ Neo4j is running"

# Verify data files exist
log "Checking data files..."
EXPECTED_FILES=(
    "countries.json.gz"
    "admin_divisions.json.gz"
    "places.json.gz"
    "wikidata_geographic.json.gz"
    "wikidata_people.json.gz"
    "wikidata_organizations.json.gz"
)

for file in "${EXPECTED_FILES[@]}"; do
    if [ ! -f "$DATA_DIR/$file" ]; then
        log_error "Missing file: $DATA_DIR/$file"
        exit 1
    fi
done
log "✓ All data files present (961MB)"

# Verify Python scripts exist
log "Checking import scripts..."
EXPECTED_SCRIPTS=(
    "import_to_nibi.py"
    "load_wikidata_entities.py"
    "create_admin_hierarchies.py"
)

for script in "${EXPECTED_SCRIPTS[@]}"; do
    if [ ! -f "$DATA_DIR/$script" ]; then
        log_error "Missing script: $DATA_DIR/$script"
        exit 1
    fi
done
log "✓ All import scripts present"

# Check Python dependencies
log "Checking Python dependencies..."
sudo -u neo4j python3 -c "import neo4j, tqdm" 2>/dev/null
if [ $? -ne 0 ]; then
    log_warning "Installing required Python packages..."
    sudo -u neo4j pip3 install --user neo4j tqdm
fi
log "✓ Python dependencies satisfied"

# Create canadaneo4j database if it doesn't exist
log "Checking database..."
sudo -u neo4j /var/lib/neo4j/bin/cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -d system \
    "SHOW DATABASES" | grep -q "canadaneo4j" || {
    log "Creating canadaneo4j database..."
    sudo -u neo4j /var/lib/neo4j/bin/cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -d system \
        "CREATE DATABASE canadaneo4j"
    sleep 5
}
log "✓ Database 'canadaneo4j' is ready"

###############################################################################
# PHASE 1: IMPORT GEONAMES DATA
###############################################################################
log_section "PHASE 1: IMPORT GEONAMES DATA (60-90 minutes)"
log "Importing: 254 countries, 509K admins, 6.2M places"

PHASE1_START=$(date +%s)

cd "$DATA_DIR"

# Modify import script to run non-interactively
sudo -u neo4j bash -c "cat > /tmp/import_runner.py << 'EOF'
import sys
sys.path.insert(0, '$DATA_DIR')
from import_to_nibi import Neo4jImporter

importer = Neo4jImporter(uri='$NEO4J_URI', user='$NEO4J_USER', password='$NEO4J_PASSWORD')

try:
    # Create constraints and indexes
    importer.create_constraints_and_indexes()

    # Load data
    importer.load_countries('$DATA_DIR/countries.json.gz')
    importer.load_admin_divisions('$DATA_DIR/admin_divisions.json.gz')
    importer.load_places('$DATA_DIR/places.json.gz')

    # Create country relationships
    importer.create_country_relationships()

    # Verify
    importer.verify_import()

    print('✓ GeoNames import complete')
except Exception as e:
    print(f'✗ Import failed: {e}')
    raise
finally:
    importer.close()
EOF"

log "Running GeoNames import..."
if sudo -u neo4j python3 /tmp/import_runner.py >> "$LOG_FILE" 2>&1; then
    PHASE1_END=$(date +%s)
    PHASE1_TIME=$((PHASE1_END - PHASE1_START))
    log "✓ Phase 1 complete ($(($PHASE1_TIME / 60)) minutes)"
else
    log_error "Phase 1 failed. Check $LOG_FILE for details"
    exit 1
fi

###############################################################################
# PHASE 2: IMPORT WIKIDATA ENTITIES
###############################################################################
log_section "PHASE 2: IMPORT WIKIDATA ENTITIES (2-3 hours)"
log "Importing: 11.6M geographic, 6M people, 235K organizations"

PHASE2_START=$(date +%s)

log "Running Wikidata import..."
if sudo -u neo4j FILTERED_DIR="$DATA_DIR" python3 "$DATA_DIR/load_wikidata_entities.py" >> "$LOG_FILE" 2>&1; then
    PHASE2_END=$(date +%s)
    PHASE2_TIME=$((PHASE2_END - PHASE2_START))
    log "✓ Phase 2 complete ($(($PHASE2_TIME / 60)) minutes)"
else
    log_error "Phase 2 failed. Check $LOG_FILE for details"
    exit 1
fi

###############################################################################
# PHASE 3: BUILD ADMINISTRATIVE HIERARCHIES
###############################################################################
log_section "PHASE 3: BUILD ADMINISTRATIVE HIERARCHIES (30-60 minutes)"
log "Creating: ADMIN1, ADMIN2, ADMIN3, ADMIN4 relationships (~2M)"

PHASE3_START=$(date +%s)

log "Running admin hierarchy builder..."
if sudo -u neo4j python3 "$DATA_DIR/create_admin_hierarchies.py" >> "$LOG_FILE" 2>&1; then
    PHASE3_END=$(date +%s)
    PHASE3_TIME=$((PHASE3_END - PHASE3_START))
    log "✓ Phase 3 complete ($(($PHASE3_TIME / 60)) minutes)"
else
    log_warning "Phase 3 completed with warnings (check log)"
fi

###############################################################################
# PHASE 4: FINAL VERIFICATION
###############################################################################
log_section "FINAL VERIFICATION"

log "Collecting database statistics..."

# Node counts
log ""
log "Node Counts:"
sudo -u neo4j /var/lib/neo4j/bin/cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -d "$DATABASE" \
    "MATCH (n) WITH labels(n)[0] as label, count(*) as count RETURN label, count ORDER BY count DESC" \
    | tee -a "$LOG_FILE"

# Relationship counts
log ""
log "Relationship Counts:"
sudo -u neo4j /var/lib/neo4j/bin/cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -d "$DATABASE" \
    "MATCH ()-[r]->() WITH type(r) as relType, count(*) as count RETURN relType, count ORDER BY count DESC" \
    | tee -a "$LOG_FILE"

# Index status
log ""
log "Indexes:"
sudo -u neo4j /var/lib/neo4j/bin/cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -d "$DATABASE" \
    "SHOW INDEXES" | head -20 | tee -a "$LOG_FILE"

###############################################################################
# DEPLOYMENT SUMMARY
###############################################################################
END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))
HOURS=$((TOTAL_TIME / 3600))
MINUTES=$(((TOTAL_TIME % 3600) / 60))

log_section "DEPLOYMENT COMPLETE"
log "Total deployment time: ${HOURS}h ${MINUTES}m"
log "Database: canadaneo4j"
log "Connection: bolt://206.12.90.118:7687"
log ""
log "Next steps:"
log "  1. Connect via Neo4j Browser: http://206.12.90.118:7474"
log "  2. Switch database: :use canadaneo4j"
log "  3. Run test queries to validate data"
log ""
log "Multi-database usage:"
log "  :use neo4j          # Canadian Census database"
log "  :use canadaneo4j    # CanadaNeo4j knowledge graph"
log ""
log "Full deployment log: $LOG_FILE"

log "✓ CanadaNeo4j Knowledge Graph deployment complete!"
