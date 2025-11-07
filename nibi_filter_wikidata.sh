#!/bin/bash
#SBATCH --job-name=wikidata_filter
#SBATCH --account=def-jic823
#SBATCH --time=12:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --output=%x-%j.out

# Filter full Wikidata dump to extract P625 (coordinates) entities
# Input: wikidata-latest-all.json.gz (~120-150 GB)
# Output: wikidata_p625_filtered.json.gz (~5-15 GB estimated)
# Processing time: ~6-10 hours (depends on dump size)

INPUT_DIR="$HOME/projects/def-jic823/wikidata"
INPUT_FILE="$INPUT_DIR/wikidata-latest-all.json.gz"
OUTPUT_FILE="$INPUT_DIR/wikidata_p625_filtered.json.gz"
SCRIPT_DIR="$HOME/projects/def-jic823/CanadaNeo4j"

echo "="$(printf '=%.0s' {1..60})
echo "WIKIDATA DUMP FILTERING"
echo "="$(printf '=%.0s' {1..60})
echo "Input: $INPUT_FILE"
echo "Output: $OUTPUT_FILE"
echo "Start time: $(date)"
echo ""

# Check input exists
if [ ! -f "$INPUT_FILE" ]; then
    echo "✗ Error: Input file not found: $INPUT_FILE"
    echo "Please run download script first:"
    echo "  sbatch nibi_download_wikidata.sh"
    exit 1
fi

# Run filtering script
echo "Processing full dump (this will take several hours)..."
echo ""

python3 "$SCRIPT_DIR/filter_wikidata_full_dump.py" "$INPUT_FILE" "$OUTPUT_FILE"

if [ $? -eq 0 ]; then
    echo ""
    echo "="$(printf '=%.0s' {1..60})
    echo "✓ FILTERING COMPLETE"
    echo "="$(printf '=%.0s' {1..60})
    echo "Output file: $OUTPUT_FILE"
    echo "Output size: $(du -h "$OUTPUT_FILE" | cut -f1)"
    echo "End time: $(date)"
    echo ""
    echo "Next step: Download to local machine"
    echo "  scp nibi:$OUTPUT_FILE /home/jic823/CanadaNeo4j/"
    echo ""
    echo "Then load into Neo4j:"
    echo "  python3 load_wikidata_from_cache.py --cache wikidata_p625_filtered.json.gz"
else
    echo ""
    echo "✗ Filtering failed!"
    exit 1
fi
