from typing import List
import networkx as nx
import json
from broadcast import *
from utils import *

class BCSimulator:
    # Default variables
    data_vol: float = 4.0  # size of data to be sent to multiple dsts
    num_partitions: int = 1
    partition_data_vol: int = data_vol / num_partitions
    default_vms_per_region: int = 1
    cost_per_instance_hr: float = 0.54  # based on m5.8xlarge spot
    src: str
    dsts: List[str]
    algo: str
    g = nx.DiGraph

    def __init__(self, num_vms, output_dir=None):
        # write output to file
        self.output_dir = output_dir
        self.default_vms_per_region = num_vms

    def initialization(self, path, config):
        # check if path is dict
        if isinstance(path, str):
            # Read from json
            with open(path, "r") as f:
                data = json.loads(f.read())
        else:
            data = {
                "algo": "none",
                "source_node": path.src,
                "terminal_nodes": path.dsts,
                "num_partitions": path.num_partitions,
                "generated_path": path.paths,
            }

        self.src = data["source_node"]
        self.dsts = data["terminal_nodes"]
        self.algo = data["algo"]
        self.paths = data["generated_path"]

        self.num_partitions = config["num_partitions"]
        self.data_vol = config["data_vol"]
        self.partition_data_vol = self.data_vol / self.num_partitions

        # Default in/egress limit if not set
        providers = ["aws", "gcp", "azure"]
        provider_ingress = [10, 16, 16]
        provider_egress = [5, 7, 16]
        self.ingress_limits = {providers[i]: provider_ingress[i] for i in range(len(providers))}
        self.egress_limits = {providers[i]: provider_egress[i] for i in range(len(providers))}

        if "ingress_limit" in config:
            for p, limit in config["ingress_limit"].items():
                self.ingress_limits[p] = self.default_vms_per_region * limit

        if "egress_limit" in config:
            for p, limit in config["egress_limit"].items():
                self.egress_limits[p] = self.default_vms_per_region * limit
        # print("Data vol (Gbit): ", self.data_vol * 8)
        print("Ingress limits: ", self.ingress_limits)
        print("Egress limits: ", self.egress_limits)

    def evaluate_path(self, path, config, write_to_file=False):
        print(f"\n==============> Evaluation")
        self.initialization(path, config)

        # construct graph
        print(f"\n--------- Algo: {self.algo}")
        self.g = self.__construct_g()
        print("\n=> Data path to dests")
        for path in self.__get_path():
            print("--")
            print(path)
            for i in range(len(path) - 1):
                print(f"Flow: {self.g[path[i]][path[i+1]]['flow']}")
                print(f"Actual throughput: {round(self.g[path[i]][path[i+1]]['throughput'], 4)}")
                print(f"Cost: {self.g[path[i]][path[i+1]]['cost']}\n")

        # evaluate transfer time and total cost
        max_t, avg_t, last_dst = self.__transfer_time()
        self.cost = self.__total_cost()

        # output to json file
        if write_to_file:
            open(f"{self.output_dir}/{self.algo}_eval.json", "w").write(
                json.dumps(
                    {
                        "path": path,
                        "max_transfer_time": max_t,
                        "avg_transfer_time": avg_t,
                        "last_dst": last_dst,
                        "tot_cost": self.cost,
                    }
                )
            )
        return max_t, self.cost

    def __construct_g(self):
        # construct a graph based on the given topology
        g = nx.DiGraph()
        for dst in self.dsts:
            for partition_id in range(self.num_partitions):
                print(self.paths)
                print("Num of partitions: ", self.num_partitions)
                for edge in self.paths[dst][str(partition_id)]:
                    src, dst, edge_data = edge[0], edge[1], edge[2]
                    if not g.has_edge(src, dst):
                        cost = edge_data["cost"]
                        throughput = edge_data["throughput"]  # * self.default_vms_per_region
                        g.add_edge(src, dst, throughput=throughput, cost=edge_data["cost"], flow=throughput)
                        g[src][dst]["partitions"] = set()
                    g[src][dst]["partitions"].add(partition_id)

        print(f"Default vms: {self.default_vms_per_region}")
        # Proportionally share if exceed in/egress limit of any node
        for node in g.nodes:
            provider = node.split(":")[0]

            in_edges, out_edges = g.in_edges(node), g.out_edges(node)
            in_flow_sum = sum([g[i[0]][i[1]]["flow"] for i in in_edges])
            out_flow_sum = sum([g[o[0]][o[1]]["flow"] for o in out_edges])

            if in_flow_sum > self.ingress_limits[provider]:
                # print("\nExceed ingress limit")
                for edge in in_edges:
                    src, dst = edge[0], edge[1]
                    # assign based on flow proportion
                    # flow_proportion = g[src][dst]['throughput'] / in_flow_sum

                    # or assign based on num of incoming flows
                    flow_proportion = 1 / len(list(in_edges))

                    g[src][dst]["flow"] = min(g[src][dst]["flow"], self.ingress_limits[provider] * flow_proportion)

            if out_flow_sum > self.egress_limits[provider]:
                # print("\nExceed egress limit")
                for edge in out_edges:
                    src, dst = edge[0], edge[1]

                    # assign based on flow proportion
                    # flow_proportion = g[src][dst]['throughput'] / out_flow_sum

                    # or assign based on num of incoming flows
                    flow_proportion = 1 / len(list(out_edges))

                    print(f"src: {src}, dst: {dst}, flow proportion: {flow_proportion}")
                    g[src][dst]["flow"] = min(g[src][dst]["flow"], self.egress_limits[provider] * flow_proportion)

        return g

    def __get_path(self):
        all_paths = [path for node in self.dsts for path in nx.all_simple_paths(self.g, self.src, node)]
        return all_paths

    def __slowest_capacity_link(self):
        min_tput = min([edge[-1]["throughput"] for edge in self.g.edges().data()])
        return min_tput

    def __transfer_time(self, log=True):
        # time for each (src, dst) pair
        t_dict = dict()
        for dst in self.dsts:
            partition_time = float("-inf")
            for i in range(self.num_partitions):
                for edge in self.paths[dst][str(i)]:
                    edge_data = self.g[edge[0]][edge[1]]
            t_dict[dst] = partition_time

        max_t = max(t_dict.values())
        last_dst = [k for k, v in t_dict.items() if v == max_t]  # last dst receiving obj
        avg_t = sum(t_dict.values()) / len(t_dict.values())
        return max_t, avg_t, last_dst

    def __total_cost(self):
        sum_egress_cost = 0
        for edge in self.g.edges.data():
            edge_data = edge[-1]
            sum_egress_cost += (
                len(edge_data["partitions"]) * self.partition_data_vol * edge_data["cost"]
            )  

        runtime_s, _, _ = self.__transfer_time(log=False)
        runtime_s = round(runtime_s, 2)
        sum_instance_cost = 0
        for node in self.g.nodes():
            # print("Default vm per region: ", self.default_vms_per_region)
            # print("Cost per instance hr: ", (self.cost_per_instance_hr / 3600) * runtime_s)
            sum_instance_cost += self.default_vms_per_region * (self.cost_per_instance_hr / 3600) * runtime_s

        sum_cost = sum_egress_cost + sum_instance_cost
        return sum_cost
