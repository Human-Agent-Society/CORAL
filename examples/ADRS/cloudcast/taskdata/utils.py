import networkx as nx
from broadcast import *
import pandas as pd
import time
import functools
import os


GBIT_PER_GBYTE = 8


class Timer:
    def __init__(self, print_desc=None):
        self.print_desc = print_desc
        self.start = time.time()
        self.end = None

    def __enter__(self):
        return self

    def __exit__(self, exc_typ, exc_val, exc_tb):
        self.end = time.time()

    @property
    def elapsed(self):
        if self.end is None:
            end = time.time()
            return end - self.start
        else:
            return self.end - self.start


@functools.lru_cache(maxsize=None)
def get_path_cost(src, dst, src_tier="PREMIUM", dst_tier="PREMIUM"):
    from skyplane import compute

    assert src_tier == "PREMIUM" and dst_tier == "PREMIUM"
    return compute.CloudProvider.get_transfer_cost(src, dst)


def make_nx_graph(cost_path=None, throughput_path=None, num_vms=1):
    """
    Default graph with capacity constraints and cost info
    nodes: regions, edges: links
    per edge:
        throughput: max tput achievable (gbps)
        cost: $/GB
        flow: actual flow (gbps), must be < throughput, default = 0
    """
    if cost_path is None:
        # Use relative path from utils.py location
        utils_dir = os.path.dirname(os.path.abspath(__file__))
        cost = pd.read_csv(os.path.join(utils_dir, "profiles/cost.csv"))
    else:
        cost = pd.read_csv(cost_path)

    if throughput_path is None:
        # Use relative path from utils.py location
        utils_dir = os.path.dirname(os.path.abspath(__file__))
        throughput = pd.read_csv(os.path.join(utils_dir, "profiles/throughput.csv"))
    else:
        throughput = pd.read_csv(throughput_path)

    G = nx.DiGraph()
    for _, row in throughput.iterrows():
        if row["src_region"] == row["dst_region"]:
            continue
        G.add_edge(row["src_region"], row["dst_region"], cost=None, throughput=num_vms * row["throughput_sent"] / 1e9)

    for _, row in cost.iterrows():
        if row["src"] in G and row["dest"] in G[row["src"]]:
            G[row["src"]][row["dest"]]["cost"] = row["cost"]

    # some pairs not in the cost grid
    no_cost_pairs = []
    for edge in G.edges.data():
        src, dst = edge[0], edge[1]
        if edge[-1]["cost"] is None:
            no_cost_pairs.append((src, dst))
    print("Unable to get costs for: ", no_cost_pairs)

    return G


def push_flow_helper(src, g, ingress_limit=10 * 5, egress_limit=10 * 5):
    """
    Push positive flows in the constructed paths (g) under constraints
    """
    for child in list(g.successors(src)):
        dfs_edges = [edge for edge in nx.dfs_edges(g, source=child)]
        dfs_min = float("inf") if not dfs_edges else min([g[t[0]][t[1]]["throughput"] for t in dfs_edges])
        min_flow = min([dfs_min, g[src][child]["throughput"], ingress_limit, egress_limit])

        # assign flows
        g[src][child]["flow"] = min_flow
        for t in dfs_edges:
            g[t[0]][t[1]]["flow"] = min_flow
    return g


def append_src_dst_paths(src, dsts, G, bc_topology):
    # Append src dst paths for partitions (all partitions follow the same path)
    for dst in dsts:
        for path in list(nx.all_simple_paths(G, src, dst)):
            for i in range(0, len(path) - 1):
                s, t = path[i], path[i + 1]
                for j in range(bc_topology.num_partitions):
                    bc_topology.append_dst_partition_path(dst, j, [s, t, G[s][t]])
    return bc_topology