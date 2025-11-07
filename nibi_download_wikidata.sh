#!/bin/bash
#SBATCH --job-name=wikidata_download
#SBATCH --account=def-jic823
#SBATCH --time=6:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --output=%x-%j.out

# Download full Wikidata dump to Nibi cluster
# Compressed size: ~120-150 GB
# Download time: ~2-4 hours (depends on network)

DUMP_URL="https://dumps.wikimedia.org/wikidatawiki/entities/latest-all.json.gz"
OUTPUT_DIR="$HOME/projects/def-jic823/wikidata"
OUTPUT_FILE="$OUTPUT_DIR/wikidata-latest-all.json.gz"

echo "="$(printf '=%.0s' {1..60})
echo "WIKIDATA FULL DUMP DOWNLOAD"
echo "="$(printf '=%.0s' {1..60})
echo "URL: $DUMP_URL"
echo "Output: $OUTPUT_FILE"
echo "Start time: $(date)"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"
cd "$OUTPUT_DIR"

# Download with resume capability
echo "Downloading Wikidata dump..."
echo "(This will take 2-4 hours for ~120-150 GB)"
echo ""

wget -c "$DUMP_URL" -O "$OUTPUT_FILE"

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Download complete!"
    echo "File size: $(du -h "$OUTPUT_FILE" | cut -f1)"
    echo "Location: $OUTPUT_FILE"
    echo "End time: $(date)"
    echo ""
    echo "Next step: Run filtering script to extract P625 entities"
    echo "  sbatch nibi_filter_wikidata.sh"
else
    echo ""
    echo "✗ Download failed!"
    echo "You can resume by running this script again (wget -c will continue)"
    exit 1
fi
