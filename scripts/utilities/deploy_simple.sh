#!/bin/bash
###############################################################################
# Simplified CanadaNeo4j Deployment Script
# Runs as ubuntu user with Neo4j credentials
###############################################################################

set -e

# Configuration
DATA_DIR="/var/lib/neo4j-data/import/canadaneo4j"
LOG_FILE="$HOME/canadaneo4j_deployment.log"

echo "================================================================================"
echo "CanadaNeo4j Knowledge Graph Deployment"
echo "================================================================================"
echo "Start time: $(date)"
echo "Data directory: $DATA_DIR"
echo "Log file: $LOG_FILE"
echo ""

# Phase 1: Import GeoNames
echo "================================================================================"
echo "PHASE 1: IMPORT GEONAMES DATA (60-90 minutes)"
echo "================================================================================"
echo "Importing: 254 countries, 509K admins, 6.2M places"
echo ""

cd "$DATA_DIR"

# Run import script with automatic yes response
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="admin"

cat > /tmp/geonames_import.py << 'EOF'
#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, '/var/lib/neo4j-data/import/canadaneo4j')

from import_to_nibi import Neo4jImporter

uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
user = os.getenv('NEO4J_USER', 'neo4j')
password = os.getenv('NEO4J_PASSWORD', 'admin')

data_dir = '/var/lib/neo4j-data/import/canadaneo4j'

importer = Neo4jImporter(uri=uri, user=user, password=password)

try:
    print("Creating constraints and indexes...")
    importer.create_constraints_and_indexes()

    print("\nLoading countries...")
    importer.load_countries(f'{data_dir}/countries.json.gz')

    print("\nLoading admin divisions...")
    importer.load_admin_divisions(f'{data_dir}/admin_divisions.json.gz')

    print("\nLoading places...")
    importer.load_places(f'{data_dir}/places.json.gz')

    print("\nCreating country relationships...")
    importer.create_country_relationships()

    print("\nVerifying import...")
    importer.verify_import()

    print('\n✓ GeoNames import complete!')
except Exception as e:
    print(f'\n✗ Import failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    importer.close()
EOF

echo "Running GeoNames import..."
python3 /tmp/geonames_import.py 2>&1 | tee -a "$LOG_FILE"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo "✓ Phase 1 complete"
else
    echo "✗ Phase 1 failed. Check $LOG_FILE"
    exit 1
fi

# Phase 2: Import Wikidata
echo ""
echo "================================================================================"
echo "PHASE 2: IMPORT WIKIDATA ENTITIES (2-3 hours)"
echo "================================================================================"
echo "Importing: 11.6M geographic, 6M people, 235K organizations"
echo ""

FILTERED_DIR="$DATA_DIR" python3 "$DATA_DIR/load_wikidata_entities.py" 2>&1 | tee -a "$LOG_FILE"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo "✓ Phase 2 complete"
else
    echo "✗ Phase 2 failed. Check $LOG_FILE"
    exit 1
fi

# Phase 3: Build admin hierarchies
echo ""
echo "================================================================================"
echo "PHASE 3: BUILD ADMINISTRATIVE HIERARCHIES (30-60 minutes)"
echo "================================================================================"
echo "Creating: ADMIN1, ADMIN2, ADMIN3, ADMIN4 relationships (~2M)"
echo ""

python3 "$DATA_DIR/create_admin_hierarchies.py" 2>&1 | tee -a "$LOG_FILE"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo "✓ Phase 3 complete"
else
    echo "⚠ Phase 3 completed with warnings"
fi

# Final verification
echo ""
echo "================================================================================"
echo "DEPLOYMENT COMPLETE"
echo "================================================================================"
echo "End time: $(date)"
echo ""
echo "Connection details:"
echo "  Bolt: bolt://206.12.90.118:7687"
echo "  HTTP: http://206.12.90.118:7474"
echo "  Database: canadaneo4j"
echo "  User: neo4j / admin"
echo ""
echo "Switch databases:"
echo "  :use neo4j          # Canadian Census database"
echo "  :use canadaneo4j    # CanadaNeo4j knowledge graph"
echo ""
echo "Full log: $LOG_FILE"
echo "================================================================================"
