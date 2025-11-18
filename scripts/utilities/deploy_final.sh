#!/bin/bash
###############################################################################
# Final CanadaNeo4j Deployment Script
# Runs from local machine, connects to Arbutus VM
###############################################################################

set -e

echo "================================================================================"
echo "CanadaNeo4j Knowledge Graph Deployment"
echo "================================================================================"
echo ""
echo "This script will import the complete CanadaNeo4j knowledge graph to Arbutus VM."
echo "Expected deployment time: 4-6 hours"
echo ""
echo "Target: 206.12.90.118"
echo "Database: canadaneo4j (separate from existing Canadian Census database)"
echo "Data: 24.6M nodes, 961MB compressed exports"
echo ""
echo "================================================================================"
echo ""

# Get Neo4j password
read -s -p "Enter Neo4j password for 206.12.90.118: " NEO4J_PASSWORD
echo ""
echo ""

# Test connection first
echo "Testing Neo4j connection..."
ssh ubuntu@206.12.90.118 << EOF
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="$NEO4J_PASSWORD"

python3 << 'PYTHON'
from neo4j import GraphDatabase
import sys

uri = "bolt://localhost:7687"
user = "neo4j"
password = "$NEO4J_PASSWORD"

try:
    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        result = session.run("RETURN 1 as test")
        print("✓ Neo4j connection successful")
    driver.close()
except Exception as e:
    print(f"✗ Connection failed: {e}")
    sys.exit(1)
PYTHON
EOF

if [ $? -ne 0 ]; then
    echo ""
    echo "✗ Cannot connect to Neo4j. Please check the password and try again."
    exit 1
fi

echo ""
echo "================================================================================"
echo "Starting deployment..."
echo "================================================================================"
echo ""

# Create deployment script on Arbutus
ssh ubuntu@206.12.90.118 "cat > /tmp/canadaneo4j_deploy.sh << 'REMOTESCRIPT'
#!/bin/bash
set -e

export NEO4J_URI=\"bolt://localhost:7687\"
export NEO4J_USER=\"neo4j\"
export NEO4J_PASSWORD=\"$NEO4J_PASSWORD\"
export DATA_DIR=\"/var/lib/neo4j-data/import/canadaneo4j\"
export LOG_FILE=\"\$HOME/canadaneo4j_deployment.log\"

echo \"\" > \"\$LOG_FILE\"
echo \"================================================================================\"  | tee -a \"\$LOG_FILE\"
echo \"CanadaNeo4j Knowledge Graph Deployment\" | tee -a \"\$LOG_FILE\"
echo \"================================================================================\"  | tee -a \"\$LOG_FILE\"
echo \"Start time: \$(date)\" | tee -a \"\$LOG_FILE\"
echo \"\" | tee -a \"\$LOG_FILE\"

# Phase 1: Import GeoNames
echo \"================================================================================\"  | tee -a \"\$LOG_FILE\"
echo \"PHASE 1: IMPORT GEONAMES DATA (60-90 minutes)\" | tee -a \"\$LOG_FILE\"
echo \"================================================================================\"  | tee -a \"\$LOG_FILE\"
echo \"Importing: 254 countries, 509K admins, 6.2M places\" | tee -a \"\$LOG_FILE\"
echo \"\" | tee -a \"\$LOG_FILE\"

cd \"\$DATA_DIR\"

python3 << 'GEONAMES'
import sys
import os
sys.path.insert(0, '/var/lib/neo4j-data/import/canadaneo4j')

from import_to_nibi import Neo4jImporter

uri = os.getenv('NEO4J_URI')
user = os.getenv('NEO4J_USER')
password = os.getenv('NEO4J_PASSWORD')
data_dir = os.getenv('DATA_DIR')

print(f\"Connecting to {uri}...\")
importer = Neo4jImporter(uri=uri, user=user, password=password)

try:
    print(\"Creating constraints and indexes...\")
    importer.create_constraints_and_indexes()

    print(\"Loading countries...\")
    importer.load_countries(f'{data_dir}/countries.json.gz')

    print(\"Loading admin divisions...\")
    importer.load_admin_divisions(f'{data_dir}/admin_divisions.json.gz')

    print(\"Loading places...\")
    importer.load_places(f'{data_dir}/places.json.gz')

    print(\"Creating country relationships...\")
    importer.create_country_relationships()

    importer.verify_import()
    print('✓ GeoNames import complete!')
except Exception as e:
    print(f'✗ Import failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    importer.close()
GEONAMES

if [ \$? -ne 0 ]; then
    echo \"✗ Phase 1 failed\" | tee -a \"\$LOG_FILE\"
    exit 1
fi

echo \"\" | tee -a \"\$LOG_FILE\"
echo \"✓ Phase 1 complete\" | tee -a \"\$LOG_FILE\"
echo \"\" | tee -a \"\$LOG_FILE\"

# Phase 2: Import Wikidata
echo \"================================================================================\"  | tee -a \"\$LOG_FILE\"
echo \"PHASE 2: IMPORT WIKIDATA ENTITIES (2-3 hours)\" | tee -a \"\$LOG_FILE\"
echo \"================================================================================\"  | tee -a \"\$LOG_FILE\"
echo \"Importing: 11.6M geographic, 6M people, 235K organizations\" | tee -a \"\$LOG_FILE\"
echo \"\" | tee -a \"\$LOG_FILE\"

FILTERED_DIR=\"\$DATA_DIR\" python3 \"\$DATA_DIR/load_wikidata_entities.py\" 2>&1 | tee -a \"\$LOG_FILE\"

if [ \${PIPESTATUS[0]} -eq 0 ]; then
    echo \"\" | tee -a \"\$LOG_FILE\"
    echo \"✓ Phase 2 complete\" | tee -a \"\$LOG_FILE\"
else
    echo \"\" | tee -a \"\$LOG_FILE\"
    echo \"✗ Phase 2 failed\" | tee -a \"\$LOG_FILE\"
    exit 1
fi

# Phase 3: Build admin hierarchies
echo \"\" | tee -a \"\$LOG_FILE\"
echo \"================================================================================\"  | tee -a \"\$LOG_FILE\"
echo \"PHASE 3: BUILD ADMINISTRATIVE HIERARCHIES (30-60 minutes)\" | tee -a \"\$LOG_FILE\"
echo \"================================================================================\"  | tee -a \"\$LOG_FILE\"
echo \"Creating: ADMIN1, ADMIN2, ADMIN3, ADMIN4 relationships (~2M)\" | tee -a \"\$LOG_FILE\"
echo \"\" | tee -a \"\$LOG_FILE\"

python3 \"\$DATA_DIR/create_admin_hierarchies.py\" 2>&1 | tee -a \"\$LOG_FILE\"

echo \"\" | tee -a \"\$LOG_FILE\"
echo \"✓ Phase 3 complete\" | tee -a \"\$LOG_FILE\"

# Final summary
echo \"\" | tee -a \"\$LOG_FILE\"
echo \"================================================================================\"  | tee -a \"\$LOG_FILE\"
echo \"DEPLOYMENT COMPLETE\" | tee -a \"\$LOG_FILE\"
echo \"================================================================================\"  | tee -a \"\$LOG_FILE\"
echo \"End time: \$(date)\" | tee -a \"\$LOG_FILE\"
echo \"\" | tee -a \"\$LOG_FILE\"
echo \"Connection details:\" | tee -a \"\$LOG_FILE\"
echo \"  Bolt: bolt://206.12.90.118:7687\" | tee -a \"\$LOG_FILE\"
echo \"  HTTP: http://206.12.90.118:7474\" | tee -a \"\$LOG_FILE\"
echo \"  Database: canadaneo4j\" | tee -a \"\$LOG_FILE\"
echo \"  User: neo4j / [password provided]\" | tee -a \"\$LOG_FILE\"
echo \"\" | tee -a \"\$LOG_FILE\"
echo \"Switch databases:\" | tee -a \"\$LOG_FILE\"
echo \"  :use neo4j          # Canadian Census database\" | tee -a \"\$LOG_FILE\"
echo \"  :use canadaneo4j    # CanadaNeo4j knowledge graph\" | tee -a \"\$LOG_FILE\"
echo \"\" | tee -a \"\$LOG_FILE\"
echo \"Full log: \$LOG_FILE\" | tee -a \"\$LOG_FILE\"
echo \"================================================================================\"  | tee -a \"\$LOG_FILE\"
REMOTESCRIPT

chmod +x /tmp/canadaneo4j_deploy.sh"

echo ""
echo "Deployment script created on Arbutus VM."
echo "Starting deployment in background..."
echo ""

# Run deployment in background with nohup
ssh ubuntu@206.12.90.118 "nohup /tmp/canadaneo4j_deploy.sh > /tmp/deployment_output.log 2>&1 &"

echo "✓ Deployment started in background on Arbutus VM"
echo ""
echo "To monitor progress:"
echo "  ssh ubuntu@206.12.90.118"
echo "  tail -f /home/ubuntu/canadaneo4j_deployment.log"
echo ""
echo "Or check output:"
echo "  ssh ubuntu@206.12.90.118 'tail -50 /tmp/deployment_output.log'"
echo ""
echo "================================================================================"
