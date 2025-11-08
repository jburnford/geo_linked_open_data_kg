#!/bin/bash
#SBATCH --account=def-jic823
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=48:00:00
#SBATCH --job-name=wikidata_filter_all
#SBATCH --output=wikidata_filter_all_%j.out
#SBATCH --error=wikidata_filter_all_%j.err

echo "=== Wikidata Multi-Pass Extraction ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "Start time: $(date)"

# Load Python
module load python/3.11

# Set paths
WORK_DIR="$HOME/projects/def-jic823/CanadaNeo4j"
WIKIDATA_DIR="$HOME/projects/def-jic823/wikidata"
INPUT_FILE="$WIKIDATA_DIR/wikidata-latest-all.json.gz"
OUTPUT_DIR="$WIKIDATA_DIR/filtered"

cd "$WORK_DIR"

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "Input: $INPUT_FILE"
echo "Input size: $(du -h $INPUT_FILE | cut -f1)"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Check input file exists
if [ ! -f "$INPUT_FILE" ]; then
    echo "ERROR: Input file not found: $INPUT_FILE"
    exit 1
fi

echo "=== Pass 1: Geographic Entities (P625) ==="
echo "Extracting entities with coordinates..."
echo "Start time: $(date)"

python3 filter_wikidata_full_dump.py \
    "$INPUT_FILE" \
    "$OUTPUT_DIR/wikidata_geographic.json.gz"

if [ $? -eq 0 ]; then
    echo "✓ Pass 1 complete"
    echo "Output size: $(du -h $OUTPUT_DIR/wikidata_geographic.json.gz | cut -f1)"
else
    echo "✗ Pass 1 failed"
    exit 1
fi

echo ""
echo "=== Pass 2: People with Place Connections ==="
echo "Extracting people (P31=Q5) with birth/death/residence places..."
echo "Start time: $(date)"

python3 filter_wikidata_people.py \
    "$INPUT_FILE" \
    "$OUTPUT_DIR/wikidata_people.json.gz"

if [ $? -eq 0 ]; then
    echo "✓ Pass 2 complete"
    echo "Output size: $(du -h $OUTPUT_DIR/wikidata_people.json.gz | cut -f1)"
else
    echo "⚠ Pass 2 failed (continuing)"
fi

echo ""
echo "=== Pass 3: Organizations ==="
echo "Extracting organizations with place connections..."
echo "Start time: $(date)"

python3 filter_wikidata_organizations.py \
    "$INPUT_FILE" \
    "$OUTPUT_DIR/wikidata_organizations.json.gz"

if [ $? -eq 0 ]; then
    echo "✓ Pass 3 complete"
    echo "Output size: $(du -h $OUTPUT_DIR/wikidata_organizations.json.gz | cut -f1)"
else
    echo "⚠ Pass 3 failed (continuing)"
fi

echo ""
echo "=== Summary ==="
echo "End time: $(date)"
echo ""
echo "Output files:"
ls -lh "$OUTPUT_DIR"/*.json.gz

echo ""
echo "Total output size:"
du -sh "$OUTPUT_DIR"

echo ""
echo "=== Extraction Complete ==="
echo ""
echo "Next steps:"
echo "1. Download filtered files to local:"
echo "   scp -r nibi:$OUTPUT_DIR /path/to/local/"
echo ""
echo "2. Load into Neo4j (on Nibi or locally):"
echo "   python3 load_wikidata_geographic.py --cache wikidata_geographic.json.gz"
echo "   python3 load_wikidata_people.py --cache wikidata_people.json.gz"
echo "   python3 load_wikidata_organizations.py --cache wikidata_organizations.json.gz"
echo ""
echo "3. Optionally delete raw dump to free space (145GB):"
echo "   rm $INPUT_FILE"
echo ""
