Cloudcast Broadcast Optimization Problem
========================================

Problem Setting
---------------
Design broadcast topology optimization for multi-cloud data distribution. Given a source node and multiple destination nodes across AWS, Azure, and GCP, find the optimal broadcast paths that minimize transfer cost while respecting bandwidth constraints.

The data is split into multiple partitions that can be transmitted independently. Different partitions can take different routes to the same destination, allowing for parallel transmission and load balancing across the network.

**Optimization Goal**: Minimize total cost ($)

$$
\text{Total Cost} = C_{\text{egress}} + C_{\text{instance}}
$$

Where:

$$
C_{\text{egress}} = \sum_{e \in E} \left( |P_e| \times s_{\text{partition}} \times c_e \right)
$$

$$
C_{\text{instance}} = |V| \times n_{\text{vm}} \times \frac{r_{\text{instance}}}{3600} \times t_{\text{transfer}}
$$

**Notation**:
- $E$: Set of all edges used in the broadcast topology (union of all partition paths)
- $P_e$: Set of partitions using edge $e$ (automatically computed by evaluator)
- $s_{\text{partition}}$: Size of each partition (GB) = $\frac{\text{data\_vol}}{\text{num\_partitions}}$
- $c_e$: Cost per GB for edge $e$ (\$/GB)
- $V$: Set of all nodes appearing in any partition path (automatically computed by evaluator)
- $n_{\text{vm}}$: Number of VMs per region (default: 2)
- $r_{\text{instance}}$: Instance hourly rate (\$/hour) = \$0.54
- $t_{\text{transfer}}$: Total transfer time (seconds) = $\max_{d \in D} \max_{p \in [0, n_p)} \max_{e \in \text{path}(d,p)} \frac{|P_e| \times s_{\text{partition}} \times 8}{f_e}$
  - $D$: Set of destination nodes
  - $n_p$: Number of partitions
  - $f_e$: Actual throughput (flow) on edge $e$ after bandwidth constraint enforcement (Gbps)

API Specification
-----------------
Implement a `Solution` class that returns a search algorithm:

```python
class Solution:
    def solve(self, spec_path: str = None) -> dict:
        """
        Returns a dict with either:
        - {"code": "python_code_string"}
        - {"program_path": "path/to/algorithm.py"}
        """
        # Your implementation
        pass
```

Your algorithm code must implement:

```python
import networkx as nx

def search_algorithm(src: str, dsts: list[str], G: nx.DiGraph, num_partitions: int) -> BroadCastTopology:
    """
    Design routing paths for broadcasting data partitions to multiple destinations.

    Args:
        src: Source node (e.g., "aws:ap-northeast-1")
        dsts: List of destination nodes (e.g., ["aws:us-east-1", "gcp:us-central1"])
        G: NetworkX DiGraph with edge attributes:
           - "cost": float ($/GB) - egress cost for transferring data
           - "throughput": float (Gbps) - maximum bandwidth capacity
        num_partitions: Number of data partitions to broadcast

    Returns:
        BroadCastTopology object with routing paths for all (destination, partition) pairs
    """
    pass


class BroadCastTopology:
    def __init__(self, src: str, dsts: list[str], num_partitions: int):
        self.src = src
        self.dsts = dsts
        self.num_partitions = int(num_partitions)
        # Structure: {dst: {partition_id: [edges]}}
        # Each edge is [src_node, dst_node, edge_data_dict]
        self.paths = {dst: {str(i): None for i in range(self.num_partitions)} for dst in dsts}

    def append_dst_partition_path(self, dst: str, partition: int, path: list):
        """
        Append an edge to the path for a specific destination-partition pair.

        Args:
            dst: Destination node
            partition: Partition ID (0 to num_partitions-1)
            path: Edge represented as [src_node, dst_node, edge_data_dict]
                  where edge_data_dict = G[src_node][dst_node]
        """
        partition = str(partition)
        if self.paths[dst][partition] is None:
            self.paths[dst][partition] = []
        self.paths[dst][partition].append(path)

    def set_dst_partition_paths(self, dst: str, partition: int, paths: list[list]):
        """
        Set the complete path (list of edges) for a destination-partition pair.

        Args:
            dst: Destination node
            partition: Partition ID
            paths: List of edges, each edge is [src_node, dst_node, edge_data_dict]
        """
        partition = str(partition)
        self.paths[dst][partition] = paths

    def set_num_partitions(self, num_partitions: int):
        """Update number of partitions"""
        self.num_partitions = num_partitions
```

Bandwidth Constraints
---------------------
Each cloud provider has ingress/egress limits (Gbps) per region:
- AWS: 10 Gbps ingress, 5 Gbps egress
- GCP: 16 Gbps ingress, 7 Gbps egress
- Azure: 16 Gbps ingress, 16 Gbps egress

These limits are multiplied by the number of VMs per region.

When multiple edges share a node and exceed its limits:
- Flow is **equally distributed** among incoming/outgoing edges (each edge gets $\frac{\text{limit}}{n_{\text{edges}}}$)
- Transfer time increases as actual throughput decreases
- Example: If a node has 3 outgoing edges and 5 Gbps egress limit, each edge gets min(original_flow, 5/3 Gbps)

**Strategy tip**: Different partitions can use different paths to the same destination, potentially avoiding bottlenecks by distributing load across the network.

Scoring (0-100)
---------------
```python
score = 1.0 / (1.0 + total_cost) * 100
```

Lower total cost → higher score

Example: Basic Implementation
------------------------------
```python
def search_algorithm(src, dsts, G, num_partitions):
    bc_topology = BroadCastTopology(src, dsts, num_partitions)

    for dst in dsts:
        path = nx.dijkstra_path(G, src, dst, weight="cost")
        for i in range(len(path) - 1):
            for partition_id in range(num_partitions):
                bc_topology.append_dst_partition_path(dst, partition_id,
                    [path[i], path[i + 1], G[path[i]][path[i + 1]]])

    return bc_topology
```

Evaluation Details
------------------
- **Test configurations**: 5 network scenarios
  - intra-AWS: Broadcasting within AWS regions
  - intra-Azure: Broadcasting within Azure regions
  - intra-GCP: Broadcasting within GCP regions
  - inter-AGZ: Broadcasting across AWS, GCP, Azure
  - inter-GAZ2: Another multi-cloud scenario
- **Network scale**: ~20-50 regions per provider
- **Default setup**: 2 VMs per region
- **Data volume**: Varies by configuration (e.g., 300 GB)
- **Partitions**: Varies by configuration (e.g., 10 partitions)
- **Instance cost**: $0.54/hour (based on m5.8xlarge spot instances)

Input Format
------------
The `spec_path` parameter is a string containing the file path to the specification JSON file.

**spec_path file format:**
```json
{
    "config_files": ["examples/config/intra_aws.json", ...],
    "num_vms": 2
}
```

Each config file contains:
```json
{
    "source_node": "aws:ap-northeast-1",
    "dest_nodes": ["aws:us-east-1", "aws:eu-west-1", ...],
    "data_vol": 300,
    "num_partitions": 10,
    "ingress_limit": {"aws": 10, "gcp": 16, "azure": 16},
    "egress_limit": {"aws": 5, "gcp": 7, "azure": 16}
}
```

Requirements and Constraints
-----------------------------
- All partitions (0 to num_partitions-1) must have valid paths to each destination
- Paths must start from the source node and end at the specified destination
- Self-loops are not allowed
- Different partitions can use different routes to the same destination
- Multiple destinations can share intermediate nodes (tree topology)
- The BroadCastTopology class is provided in the evaluation environment
