import importlib.util
import traceback
import json
import os
import sys
from pathlib import Path

# Add parent directory to Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from utils import *
from simulator import *
from broadcast import *
from initial_program import search_algorithm
import networkx as nx


def validate_broadcast_topology(bc_t, source_node, terminal_nodes, num_partitions, G):
    """
    Validate that the broadcast topology is complete and correct.
    
    Returns:
        (is_valid, error_message) tuple
    """
    # Check 1: Verify all destinations are present
    if set(bc_t.dsts) != set(terminal_nodes):
        missing_dsts = set(terminal_nodes) - set(bc_t.dsts)
        extra_dsts = set(bc_t.dsts) - set(terminal_nodes)
        return False, f"Destination mismatch: missing={missing_dsts}, extra={extra_dsts}"
    
    # Check 2: Verify source matches
    if bc_t.src != source_node:
        return False, f"Source mismatch: expected={source_node}, got={bc_t.src}"
    
    # Check 3: Verify all partitions exist for all destinations
    missing_partitions = []
    empty_partitions = []
    invalid_paths = []
    
    for dst in terminal_nodes:
        if dst not in bc_t.paths:
            return False, f"Missing destination '{dst}' in paths"
        
        for partition_id in range(num_partitions):
            partition_key = str(partition_id)
            
            # Check if partition exists
            if partition_key not in bc_t.paths[dst]:
                missing_partitions.append((dst, partition_id))
                continue
            
            partition_paths = bc_t.paths[dst][partition_key]
            
            # Check if partition paths are None or empty
            if partition_paths is None or len(partition_paths) == 0:
                empty_partitions.append((dst, partition_id))
                continue
            
            # Check 4: Verify paths form valid routes from source to destination
            # Build a path from edges
            path_nodes = [source_node]
            path_valid = True
            
            for edge in partition_paths:
                if len(edge) < 3:
                    invalid_paths.append((dst, partition_id, "edge format invalid"))
                    path_valid = False
                    break
                
                edge_src, edge_dst, edge_data = edge[0], edge[1], edge[2]
                
                # Verify edge exists in graph
                if not G.has_edge(edge_src, edge_dst):
                    invalid_paths.append((dst, partition_id, f"edge {edge_src}->{edge_dst} not in graph"))
                    path_valid = False
                    break
                
                # Verify path continuity
                if path_nodes[-1] != edge_src:
                    invalid_paths.append((dst, partition_id, f"path discontinuity: expected {path_nodes[-1]}, got {edge_src}"))
                    path_valid = False
                    break
                
                path_nodes.append(edge_dst)
            
            # Check if path reaches destination (only if path was valid so far)
            if path_valid and path_nodes[-1] != dst:
                invalid_paths.append((dst, partition_id, f"path does not reach destination: ends at {path_nodes[-1]}, expected {dst}"))
    
    # Compile validation errors
    errors = []
    if missing_partitions:
        errors.append(f"Missing partitions: {missing_partitions}")
    if empty_partitions:
        errors.append(f"Empty partitions: {empty_partitions}")
    if invalid_paths:
        errors.append(f"Invalid paths: {invalid_paths}")
    
    if errors:
        return False, "Validation failed: " + "; ".join(errors)
    
    # Check 5: Verify all data volumes are accounted for
    # Count total partitions that should be transferred
    expected_total_partitions = len(terminal_nodes) * num_partitions
    
    # Count partitions actually present
    actual_partitions = 0
    for dst in terminal_nodes:
        for partition_id in range(num_partitions):
            partition_key = str(partition_id)
            if (partition_key in bc_t.paths[dst] and 
                bc_t.paths[dst][partition_key] is not None and 
                len(bc_t.paths[dst][partition_key]) > 0):
                actual_partitions += 1
    
    if actual_partitions != expected_total_partitions:
        return False, f"Data loss detected: expected {expected_total_partitions} partitions, got {actual_partitions}"
    
    return True, None


def evaluate(program_path):
    """
    Evaluate the evolved broadcast optimization program across multiple configurations.
    
    Args:
        program_path: Path to the evolved program file
        
    Returns:
        Dictionary with evaluation metrics including required 'combined_score'
    """
    try:
        # Load the evolved program
        spec = importlib.util.spec_from_file_location("program", program_path)
        program = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(program)
        
        # Check if the required function exists
        if not hasattr(program, "search_algorithm"):
            return {
                "combined_score": 0.0,
                "runs_successfully": 0.0,
                "error": "Missing search_algorithm function"
            }
        
        # Configuration - individual JSON file paths (relative to evaluator location)
        evaluator_dir = os.path.dirname(os.path.abspath(__file__))
        config_files = [
            os.path.join(evaluator_dir, "examples/config/intra_aws.json"),
            os.path.join(evaluator_dir, "examples/config/intra_azure.json"), 
            os.path.join(evaluator_dir, "examples/config/intra_gcp.json"),
            os.path.join(evaluator_dir, "examples/config/inter_agz.json"),
            os.path.join(evaluator_dir, "examples/config/inter_gaz2.json")
        ]
        
        # Filter to only include files that exist
        existing_configs = [f for f in config_files if os.path.exists(f)]
        
        if not existing_configs:
            return {
                "combined_score": 0.0,
                "runs_successfully": 0.0,
                "error": f"No configuration files found. Checked: {config_files}"
            }
        
        num_vms = 2
        total_cost = 0.0
        successful_configs = 0
        failed_configs = 0
        
        # Process each configuration file
        for jsonfile in existing_configs:
            try:
                print(f"Processing config: {os.path.basename(jsonfile)}")
                
                # Load configuration
                with open(jsonfile, "r") as f:
                    config_name = os.path.basename(jsonfile).split(".")[0]
                    config = json.loads(f.read())

                # Create graph
                G = make_nx_graph(num_vms=int(num_vms))

                # Source and destination nodes
                source_node = config["source_node"]
                terminal_nodes = config["dest_nodes"]

                # Create output directory
                directory = f"paths/{config_name}"
                if not os.path.exists(directory):
                    Path(directory).mkdir(parents=True, exist_ok=True)

                # Run the evolved algorithm
                num_partitions = config["num_partitions"]
                bc_t = program.search_algorithm(source_node, terminal_nodes, G, num_partitions)

                bc_t.set_num_partitions(config["num_partitions"])
                
                # Validate the broadcast topology before evaluation
                is_valid, validation_error = validate_broadcast_topology(
                    bc_t, source_node, terminal_nodes, num_partitions, G
                )
                
                if not is_valid:
                    print(f"Validation failed for {config_name}: {validation_error}")
                    # raise ValueError(f"Invalid broadcast topology: {validation_error}")
                    return {
                        "combined_score": 0.0,
                        "runs_successfully": 0.0,
                        "error": f"Invalid broadcast topology: {validation_error}"
                    }
                
                # Save the generated paths
                outf = f"{directory}/search_algorithm.json"
                with open(outf, "w") as outfile:
                    outfile.write(
                        json.dumps(
                            {
                                "algo": "search_algorithm",
                                "source_node": bc_t.src,
                                "terminal_nodes": bc_t.dsts,
                                "num_partitions": bc_t.num_partitions,
                                "generated_path": bc_t.paths,
                            }
                        )
                    )

                # Evaluate the generated paths
                input_dir = f"paths/{config_name}"
                output_dir = f"evals/{config_name}"
                if not os.path.exists(output_dir):
                    Path(output_dir).mkdir(parents=True, exist_ok=True)

                # Run simulation
                simulator = BCSimulator(int(num_vms), output_dir)
                _, cost = simulator.evaluate_path(outf, config)
                
                # Accumulate results
                total_cost += cost
                successful_configs += 1
                
                print(f"Config {config_name}: cost={cost:.2f}")
                
            except Exception as e:
                print(f"Failed to process {os.path.basename(jsonfile)}: {str(e)}")
                failed_configs += 1
                break
        
        # Check if we have any successful evaluations
        if failed_configs != 0:
            return {
                "combined_score": 0.0,
                "runs_successfully": 0.0,
                "error": "1 or more configuration files failed to process"
            }
        
        # Calculate aggregate metrics
        avg_cost = total_cost / successful_configs
        success_rate = successful_configs / (successful_configs + failed_configs)
        
        print(f"Summary: {successful_configs} successful, {failed_configs} failed")
        print(f"Total cost: {total_cost:.2f}")
        
        # Calculate metrics for SkyDiscover
        # Normalize scores (higher is better)
        cost_score = 1.0 / (1.0 + total_cost)  # Lower cost = higher score
        
        # Combined score considering total cost, and success rate
        combined_score = cost_score
        
        return {
            "combined_score": combined_score,  # Required by SkyDiscover
            "runs_successfully": success_rate,
            "total_cost": total_cost,
            "avg_cost": avg_cost,
            "successful_configs": successful_configs,
            "failed_configs": failed_configs,
            "cost_score": cost_score,
            "success_rate": success_rate
        }

    except Exception as e:
        print(f"Evaluation failed: {str(e)}")
        print(traceback.format_exc())
        return {
            "combined_score": 0.0,  # Required by SkyDiscover
            "runs_successfully": 0.0,
            "error": str(e)
        }


if __name__ == "__main__":
    # Backwards-compat: bridges old evaluate() -> dict to the container JSON
    # protocol.  wrapper.py is auto-injected at build time from
    # skydiscover/evaluation/wrapper.py.
    from wrapper import run

    run(evaluate)