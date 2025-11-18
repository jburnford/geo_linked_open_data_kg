# Neo4j on Nibi: User-Space Tarball Deployment Plan

> **⚠️ HISTORICAL DOCUMENT - SUPERSEDED**
>
> This plan was created for deploying Neo4j on the Nibi HPC cluster but was **superseded by Arbutus Cloud VM deployment**. The project is now running on an Arbutus Cloud VM (206.12.90.118) with dedicated resources.
>
> **Current Infrastructure**: See [PROJECT_STATUS.md](PROJECT_STATUS.md) for active deployment details.
>
> **Preserved For**: Reference for potential future HPC deployments or as an alternative approach.
>
> ---

## Problem Statement

Running Neo4j on Alliance Canada HPC clusters (Nibi) has challenges:
- ❌ Cannot use `sudo` for system installs
- ❌ Apptainer containers don't bind ports reliably in SLURM
- ❌ No pre-configured Neo4j DBaaS (only MySQL/PostgreSQL available)

## Solution: Neo4j Community Edition from Tarball

Neo4j distributes official tarballs that run entirely in user space without root privileges.

### Why This Works

1. **Alliance Canada Policy**: User-space software installations are standard practice
2. **Neo4j Design**: Tarball distribution designed for non-root users
3. **No Compilation**: Pre-built Java binaries, just extract and run
4. **Full Control**: All paths configurable via environment variables
5. **SLURM Compatible**: Runs as foreground console process in job

### Research Sources

- **Neo4j Official Docs**: [Linux Tarball Installation](https://neo4j.com/docs/operations-manual/current/installation/linux/tarball/)
  - "You should untar/unzip Neo4j as the user who will own and manage it, and not with sudo"
  - "NEO4J_HOME refers to the location the archive was extracted to"

- **Alliance Canada Docs**: [Database Servers](https://docs.alliancecan.ca/wiki/Database_servers)
  - Users run databases by connecting to services or installing in user space
  - Software must be capable of installation without root/sudo

- **HPC Best Practices**: Standard to install software in `$HOME` or project directories

## Architecture

### Directory Structure

```
~/projects/def-jic823/
├── neo4j-community-5.13.0/     # Extracted tarball
│   ├── bin/                     # neo4j executable
│   ├── conf/                    # neo4j.conf (customized)
│   ├── lib/                     # Java libraries
│   └── ...
├── neo4j_data/                  # Database storage
│   ├── databases/
│   ├── transactions/
│   └── dbms/
├── neo4j_logs/                  # Log files
├── neo4j_import/                # Import directory
└── neo4j_plugins/               # Plugins (GDS, APOC)
```

### Configuration

**Custom neo4j.conf** settings:
```properties
# Directories
dbms.directories.data=/home/jic823/projects/def-jic823/neo4j_data
dbms.directories.logs=/home/jic823/projects/def-jic823/neo4j_logs
dbms.directories.import=/home/jic823/projects/def-jic823/neo4j_import
dbms.directories.plugins=/home/jic823/projects/def-jic823/neo4j_plugins

# Memory (for 64GB node)
server.memory.heap.initial_size=16g
server.memory.heap.max_size=16g
server.memory.pagecache.size=32g

# Network
server.bolt.enabled=true
server.bolt.listen_address=0.0.0.0:7687
server.http.enabled=true
server.http.listen_address=0.0.0.0:7474

# Authentication
dbms.security.auth_enabled=true
# Initial password set via neo4j-admin
```

## Implementation Plan

### Phase 1: Download and Setup (5 minutes)

```bash
# On Nibi (can run on login node)
cd ~/projects/def-jic823

# Download Neo4j 5.13.0 Community Edition
wget https://dist.neo4j.org/neo4j-community-5.13.0-unix.tar.gz

# Extract
tar -xzf neo4j-community-5.13.0-unix.tar.gz

# Create data directories
mkdir -p neo4j_data neo4j_logs neo4j_import neo4j_plugins

# Cleanup tarball
rm neo4j-community-5.13.0-unix.tar.gz
```

### Phase 2: Configuration (5 minutes)

**Create custom conf/neo4j.conf:**
- Set all directory paths to project space
- Configure memory for 64GB nodes
- Enable remote connections (bolt + http)
- Set initial password

**Set initial password:**
```bash
cd neo4j-community-5.13.0
bin/neo4j-admin dbms set-initial-password historicalkg2025
```

### Phase 3: Test Deployment (SLURM Job, 1 hour)

**Purpose**: Verify Neo4j starts, accepts connections, runs queries

**Test Script** (`test_neo4j.sh`):
```bash
#!/bin/bash
#SBATCH --time=1:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=8

cd ~/projects/def-jic823/neo4j-community-5.13.0

# Start Neo4j in foreground
bin/neo4j console
```

**Verification Steps**:
1. Check logs for successful startup
2. Test connection from login node: `bin/cypher-shell -u neo4j -p historicalkg2025`
3. Run simple query: `RETURN 'Hello Neo4j' as message;`
4. Verify memory settings
5. Check port bindings (7687, 7474)

### Phase 4: Import Database (SLURM Job, 3 hours)

**Combined Import Script** (`import_database.sh`):
```bash
#!/bin/bash
#SBATCH --time=3:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=8

# Start Neo4j in background
cd ~/projects/def-jic823/neo4j-community-5.13.0
bin/neo4j console &
NEO4J_PID=$!

# Wait for startup
sleep 60

# Run import
cd ~/projects/def-jic823/CanadaNeo4j
python3 import_to_nibi.py neo4j_export

# Build hierarchies
python3 create_admin_hierarchies_batched.py
python3 add_admin3_links.py

# Verify
bin/cypher-shell -u neo4j -p historicalkg2025 <<EOF
MATCH (n) RETURN labels(n)[0] as label, count(*) as count ORDER BY count DESC;
MATCH ()-[r]->() RETURN type(r) as relType, count(*) as count ORDER BY count DESC;
EOF

# Keep running
wait $NEO4J_PID
```

**Expected Results**:
- 6,233,958 Place nodes
- 509,913 AdminDivision nodes
- 254 Country nodes
- 11.5M+ relationships
- Total time: ~2-3 hours

### Phase 5: Production Deployment (SLURM Job, 48 hours)

**Long-Running Server** (`deploy_neo4j_production.sh`):
```bash
#!/bin/bash
#SBATCH --time=48:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=8
#SBATCH --job-name=neo4j_server

cd ~/projects/def-jic823/neo4j-community-5.13.0

echo "Starting Neo4j server..."
echo "Connection: bolt://$(hostname):7687"
echo "Auth: neo4j/historicalkg2025"

# Start Neo4j (runs until job ends)
bin/neo4j console
```

**Access from Laptop**:
```bash
# Get compute node name from SLURM output
# Example: c136

# SSH tunnel through login node
ssh -L 7687:c136:7687 -L 7474:c136:7474 nibi

# Connect Neo4j Browser
# http://localhost:7474
```

## Integration with Wikidata Filtering

### Combined Workflow Script

**Goal**: Filter Wikidata while Neo4j runs, then load results incrementally

```bash
#!/bin/bash
#SBATCH --time=48:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=8
#SBATCH --job-name=wikidata_pipeline

# Step 1: Start Neo4j (background)
cd ~/projects/def-jic823/neo4j-community-5.13.0
bin/neo4j console &
NEO4J_PID=$!
sleep 60

# Step 2: Filter Wikidata (8-10 hours per pass)
cd ~/projects/def-jic823/CanadaNeo4j

# Pass 1: Geographic entities
python3 filter_wikidata_full_dump.py \
    ~/projects/def-jic823/wikidata/wikidata-latest-all.json.gz \
    ~/projects/def-jic823/wikidata/filtered/wikidata_geographic.json.gz

# Load into Neo4j
python3 load_wikidata_geographic.py \
    --cache ~/projects/def-jic823/wikidata/filtered/wikidata_geographic.json.gz

# Pass 2: People
python3 filter_wikidata_people.py \
    ~/projects/def-jic823/wikidata/wikidata-latest-all.json.gz \
    ~/projects/def-jic823/wikidata/filtered/wikidata_people.json.gz

python3 load_wikidata_people.py \
    --cache ~/projects/def-jic823/wikidata/filtered/wikidata_people.json.gz

# Pass 3: Organizations
python3 filter_wikidata_organizations.py \
    ~/projects/def-jic823/wikidata/wikidata-latest-all.json.gz \
    ~/projects/def-jic823/wikidata/filtered/wikidata_organizations.json.gz

python3 load_wikidata_organizations.py \
    --cache ~/projects/def-jic823/wikidata/filtered/wikidata_organizations.json.gz

# Keep Neo4j running
wait $NEO4J_PID
```

## Timeline

### Testing Phase
- **Download & Setup**: 5 minutes
- **Configuration**: 5 minutes
- **Test Deployment**: 1 hour (SLURM job)
- **Total**: ~1.5 hours to verify approach works

### Production Deployment
- **Initial Import**: 3 hours (SLURM job)
  - Load 6.74M nodes from export
  - Build admin hierarchies
  - Verify database state

- **Wikidata Processing**: 48 hours (SLURM job)
  - Filter Pass 1: 8-10 hours → Load: 2-3 hours
  - Filter Pass 2: 8-10 hours → Load: 1-2 hours
  - Filter Pass 3: 8-10 hours → Load: 30-60 minutes
  - Total: ~30-36 hours actual work
  - Buffer: 12-18 hours

### Total Project Timeline
- **Day 1**: Test deployment, verify approach works
- **Day 2**: Import base database (6.74M nodes)
- **Day 3-4**: Filter and load Wikidata entities
- **Day 5+**: Knowledge graph ready for UniversalNER grounding

## Advantages of This Approach

### Technical Benefits
1. ✅ **Standard Installation**: Official Neo4j distribution
2. ✅ **No Root Required**: Runs entirely in user space
3. ✅ **SLURM Native**: Foreground console process
4. ✅ **Port Binding**: Direct network access (no container translation)
5. ✅ **Full Control**: All paths, configs, memory settings customizable
6. ✅ **Debuggable**: Standard logs, clear error messages
7. ✅ **Upgradeable**: Easy to download newer versions

### Operational Benefits
1. ✅ **Reliable**: Standard approach used by many researchers
2. ✅ **Documented**: Official Neo4j docs apply directly
3. ✅ **Flexible**: Can run 1 hour tests or 48 hour production
4. ✅ **Resumable**: Database persists in project space
5. ✅ **Accessible**: SSH tunnel for Neo4j Browser access
6. ✅ **Integrable**: Combine with Wikidata filtering in one job

### Alignment with Alliance Canada
1. ✅ **Policy Compliant**: User-space software encouraged
2. ✅ **Storage Appropriate**: Uses project space (correct location)
3. ✅ **Resource Efficient**: 64GB RAM, 8 cores for database+processing
4. ✅ **Job Scheduler**: Standard SLURM approach

## Risk Mitigation

### Potential Issues and Solutions

**Issue 1: Java not available**
- Check: `module avail java`
- Solution: Load Java module in SLURM script: `module load java/17`

**Issue 2: Port conflicts**
- Check: Another Neo4j instance running
- Solution: Use `bin/neo4j stop` or different ports in config

**Issue 3: Memory limits**
- Check: SLURM job memory vs Neo4j heap+pagecache
- Solution: Ensure heap (16GB) + pagecache (32GB) < job memory (64GB)

**Issue 4: Connection from laptop**
- Check: Firewall rules, SSH tunnel setup
- Solution: Use correct compute node hostname in tunnel

**Issue 5: Database corruption**
- Check: Clean shutdown (`bin/neo4j stop`)
- Solution: Always stop gracefully, not `scancel`

## Alternative: Embedded Neo4j

If console mode has issues, we can use **embedded Neo4j** in Python:

```python
from neo4j import GraphDatabase

# Embedded mode - no server needed
driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", "password")
)
```

But this loses:
- Neo4j Browser access
- Real-time querying during processing
- Separate server/client model

**Recommendation**: Start with console mode (standard approach).

## Success Criteria

**Phase 1 (Testing) Success**:
- [ ] Neo4j starts in SLURM job
- [ ] Accepts cypher-shell connections
- [ ] Runs queries successfully
- [ ] Logs show no errors
- [ ] Memory settings applied correctly

**Phase 2 (Import) Success**:
- [ ] 6.74M nodes loaded
- [ ] All relationships created
- [ ] Indexes built and online
- [ ] Query performance acceptable
- [ ] Database size reasonable (~10-20GB)

**Phase 3 (Production) Success**:
- [ ] Wikidata filtering completes
- [ ] Entities loaded incrementally
- [ ] Final database: 15-20M nodes
- [ ] SSH tunnel access works
- [ ] Ready for UniversalNER integration

## Next Steps

1. **Create test deployment script**
2. **Submit 1-hour test job**
3. **Verify Neo4j works**
4. **If successful: Create production deployment**
5. **If issues: Debug and iterate**

## Resources

- Neo4j Tarball Installation: https://neo4j.com/docs/operations-manual/current/installation/linux/tarball/
- Alliance Canada Database Docs: https://docs.alliancecan.ca/wiki/Database_servers
- Neo4j Configuration Reference: https://neo4j.com/docs/operations-manual/current/configuration/
- Neo4j Console Mode: https://neo4j.com/docs/operations-manual/current/installation/linux/systemd/#linux-console

---

**Status**: Ready to implement
**Confidence**: High (standard approach, well-documented, policy-compliant)
**Timeline**: 1.5 hours to validate, then production deployment
