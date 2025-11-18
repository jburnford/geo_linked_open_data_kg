# Credentials Setup Guide

This file documents the credentials needed for the CanadaNeo4j project. **DO NOT commit actual credentials to git.**

## Required Credentials

### 1. Neo4j Database Connection

Create a `.env` file in the project root with the following variables:

```bash
# Neo4j Connection
NEO4J_URI=bolt://206.12.90.118:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<your-password-here>
NEO4J_DATABASE=canadaneo4j
```

### 2. Arbutus Cloud VM Access

**SSH Connection**:
- Host: `206.12.90.118`
- User: `ubuntu`
- Authentication: SSH key (not password)

**Setup SSH Key** (if not already configured):
```bash
# Add VM to SSH config (~/.ssh/config)
Host arbutus-neo4j
    HostName 206.12.90.118
    User ubuntu
    IdentityFile ~/.ssh/your_key_name
```

### 3. CREDENTIALS.txt Format

Create a `CREDENTIALS.txt` file in the project root (gitignored):

```
Neo4j Arbutus VM Credentials
=============================

Database Connection:
- URI: bolt://206.12.90.118:7687
- HTTP: http://206.12.90.118:7474
- User: neo4j
- Password: <actual-password>
- Database: canadaneo4j

VM SSH Access:
- Host: 206.12.90.118
- User: ubuntu
- Key: ~/.ssh/<key-name>

VM File Locations:
- Scripts: /var/lib/neo4j-data/import/canadaneo4j/
- Logs: /home/ubuntu/
- Neo4j Config: /etc/neo4j/neo4j.conf
```

## Using Credentials in Scripts

### Python Scripts

All Python scripts should read from environment variables:

```python
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Read credentials
uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
user = os.getenv('NEO4J_USER', 'neo4j')
password = os.getenv('NEO4J_PASSWORD')
database = os.getenv('NEO4J_DATABASE', 'canadaneo4j')

# Connect
from neo4j import GraphDatabase
driver = GraphDatabase.driver(uri, auth=(user, password))
```

### Shell Commands

Export environment variables before running commands:

```bash
# Export password for cypher-shell
export NEO4J_PASSWORD="<your-password>"

# Use in commands
ssh ubuntu@206.12.90.118 'echo "MATCH (n) RETURN count(n);" | cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -d canadaneo4j'
```

## Security Best Practices

1. ✅ **Never commit** `.env`, `CREDENTIALS.txt`, or any file containing passwords
2. ✅ **Use environment variables** in all scripts (no hardcoded passwords)
3. ✅ **Restrict file permissions**: `chmod 600 .env CREDENTIALS.txt`
4. ✅ **Use SSH keys** for VM access (not passwords)
5. ✅ **Rotate credentials** periodically
6. ✅ **Share credentials securely** (encrypted channels, password managers)

## Required Python Package

Install `python-dotenv` to load environment variables:

```bash
pip install python-dotenv
```

Or add to `requirements.txt`:
```
python-dotenv>=1.0.0
```

## Troubleshooting

### "Authentication failed" errors
- Verify `.env` file exists and contains correct password
- Check `NEO4J_PASSWORD` environment variable is set
- Test connection manually: `cypher-shell -a bolt://206.12.90.118:7687 -u neo4j -p "$NEO4J_PASSWORD"`

### "Connection refused" errors
- Verify Neo4j is running on VM: `ssh ubuntu@206.12.90.118 'systemctl status neo4j'`
- Check firewall rules allow port 7687
- Verify VM IP address is correct

### ".env file not loading"
- Ensure `python-dotenv` is installed
- Check file is named `.env` (not `.env.txt`)
- Verify file is in the same directory as your script or project root

## Contact

For access to credentials, contact the project maintainer.
