#!/bin/bash
#SBATCH --account=def-jic823
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=1:00:00
#SBATCH --job-name=build_neo4j
#SBATCH --output=build_neo4j_%j.out
#SBATCH --error=build_neo4j_%j.err

echo "=== Building Neo4j Container for Historical Knowledge Graph ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "Start time: $(date)"

# Load Apptainer module
module load apptainer

# Set container location
CONTAINER_DIR="$HOME/projects/def-jic823/CanadaNeo4j"
CONTAINER_FILE="$CONTAINER_DIR/neo4j.sif"

# Create directory if needed
mkdir -p "$CONTAINER_DIR"

echo "Building Neo4j Community Edition container..."
echo "Output: $CONTAINER_FILE"

# Build Neo4j container from Docker Hub
# Using Neo4j 5.13 Community Edition (latest stable)
apptainer build "$CONTAINER_FILE" docker://neo4j:5.13-community

if [ $? -eq 0 ]; then
    echo "✓ Neo4j container built successfully!"
    echo "Size: $(du -h "$CONTAINER_FILE" | cut -f1)"
    echo "Location: $CONTAINER_FILE"
else
    echo "✗ Container build failed!"
    exit 1
fi

echo "=== Build Complete ==="
echo "End time: $(date)"
