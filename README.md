# Raft Lite Implementation

Distributed Computing Lab 3 — Implementation of the Raft Consensus Algorithm (Leader Election + Log Replication).

## Features
- **Leader Election**: Implements Raft's leader election mechanism with randomized timeout periods.
- **Log Replication**: Handles log replication across the cluster with consistency guarantees.
- **Fault Tolerance**: Maintains consistency even when nodes fail and recover.
- **HTTP Communication**: Nodes communicate via REST API endpoints.

## Project Structure
```
raft-lite/
├── raft.py            # Main Raft node implementation
├── client.py          # Client for sending commands to the cluster
├── requirements.txt   # Python dependencies
└── README.md          # This documentation
```

## Prerequisites
- Python 3.7+
- pip package manager

## Installation
Clone the repository:
```bash
git clone <repository-url>
cd raft-lite
```

Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Cluster

Start Raft nodes in separate terminal windows. Example for a 3-node cluster:

Node A (localhost:5000):
```bash
python raft.py --id A --port 5000 --peers http://localhost:5001,http://localhost:5002
```

Node B (localhost:5001):
```bash
python raft.py --id B --port 5001 --peers http://localhost:5000,http://localhost:5002
```

Node C (localhost:5002):
```bash
python raft.py --id C --port 5002 --peers http://localhost:5000,http://localhost:5001
```

## Command-Line Arguments
- `--id`: Unique identifier for the node (A, B, C, etc.)
- `--port`: Port number to run the HTTP server on
- `--peers`: Comma-separated list of other node URLs

## Using the Client
Send commands to the cluster:
```bash
python client.py "SET x=100"
```
The client will automatically discover the current leader and forward the command to it.

### Supported Commands
The system accepts any string command for replication. Examples:
- `SET x=100`
- `UPDATE status=active`

## API Endpoints

### Client-facing
- `POST /submit` — Submit a new command to the cluster  
  Example JSON:
  ```json
  {
    "command": "SET x=100"
  }
  ```

### Internal RPC (between nodes)
- `POST /request_vote` — Request votes for leader election
- `POST /append_entries` — Append entries to log (heartbeat & replication)

## How It Works

### Leader Election
- All nodes start as followers.
- If a follower doesn't hear from a leader within its timeout period, it becomes a candidate.
- The candidate requests votes from other nodes.
- If it receives votes from a majority, it becomes the leader.
- Leaders send regular heartbeats to maintain authority.

### Log Replication
- Client sends a command to the leader.
- Leader appends the command to its log.
- Leader replicates the log entry to followers.
- Once a majority of nodes have the entry, the leader commits it.
- Leader notifies followers to commit the entry.
- Leader responds to the client.

## Testing

### Basic Test
1. Start all three nodes.
2. Wait for leader election (check logs).
3. Send a command using the client:
   ```bash
   python client.py "SET test=hello"
   ```
4. Verify the command replicates across all nodes (look for `[COMMIT]` in logs).

### Fault Tolerance Test
1. Start the cluster and send some commands.
2. Kill the leader process (Ctrl+C).
3. Observe new leader election on remaining nodes.
4. Send more commands to the new leader — they should still be processed.
5. Restart the killed node — it should catch up with the log automatically.

## Monitoring
Check each node's logs to see:
- State changes (follower → candidate → leader)
- Vote requests and responses
- Log replication progress
- Heartbeat activity

## Limitations
- State is stored in memory (not persistent across restarts).
- No snapshotting mechanism for log compaction.
- Simplified network layer (no real network partition simulation).
