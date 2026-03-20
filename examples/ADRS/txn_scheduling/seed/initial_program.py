import random

from txn_simulator import Workload
from workloads import WORKLOAD_1, WORKLOAD_2, WORKLOAD_3

# EVOLVE-BLOCK-START

def get_best_schedule(workload, num_seqs):
    """
    Get optimal schedule using greedy cost sampling strategy.

    Returns:
        Tuple of (lowest makespan, corresponding schedule)
    """
    def get_greedy_cost_sampled(num_samples, sample_rate):
        # greedy with random starting point
        start_txn = random.randint(0, workload.num_txns - 1)
        txn_seq = [start_txn]
        remaining_txns = [x for x in range(0, workload.num_txns)]
        remaining_txns.remove(start_txn)
        running_cost = workload.txns[start_txn][0][3]
        # min_costs = []
        # key_map, total_cost = workload.get_incremental_seq_cost(start_txn, {}, 0)
        for i in range(0, workload.num_txns - 1):
            min_cost = 100000 # MAX
            min_relative_cost = 10
            min_txn = -1
            # min_index = 0
            holdout_txns = []
            done = False
            key_maps = []

            sample = random.random()
            if sample > sample_rate:
                idx = random.randint(0, len(remaining_txns) - 1)
                t = remaining_txns[idx]
                txn_seq.append(t)
                remaining_txns.pop(idx)
                continue

            for j in range(0, num_samples):
                idx = 0
                if len(remaining_txns) > 1:
                    idx = random.randint(0, len(remaining_txns) - 1)
                else:
                    done = True
                t = remaining_txns[idx]
                holdout_txns.append(remaining_txns.pop(idx))
                if workload.debug:
                    print(remaining_txns, holdout_txns)
                txn_len = workload.txns[t][0][3]
                test_seq = txn_seq.copy()
                test_seq.append(t)
                cost = 0
                cost = workload.get_opt_seq_cost(test_seq)
                if cost < min_cost:
                # if relative_cost < min_relative_cost:
                    min_cost = cost
                    min_txn = t
                    # min_relative_cost = relative_cost
                    # min_index = j
                if done:
                    break
            assert(min_txn != -1)
            running_cost = min_cost
            txn_seq.append(min_txn)
            holdout_txns.remove(min_txn)
            remaining_txns.extend(holdout_txns)

            if workload.debug:
                print("min: ", min_txn, remaining_txns, holdout_txns, txn_seq)
        if workload.debug:
            print(txn_seq)
            print(len(set(txn_seq)))
        assert len(set(txn_seq)) == workload.num_txns
        # print(txn_seq)

        overall_cost = workload.get_opt_seq_cost(txn_seq)

        return overall_cost, txn_seq

    return get_greedy_cost_sampled(10, 1.0)

# EVOLVE-BLOCK-END

def get_random_costs():
    workload_size = 100
    workload = Workload(WORKLOAD_1)

    makespan1, schedule1 = get_best_schedule(workload, 10)
    cost1 = workload.get_opt_seq_cost(schedule1)

    workload2 = Workload(WORKLOAD_2)
    makespan2, schedule2 = get_best_schedule(workload2, 10)
    cost2 = workload2.get_opt_seq_cost(schedule2)

    workload3 = Workload(WORKLOAD_3)
    makespan3, schedule3 = get_best_schedule(workload3, 10)
    cost3 = workload3.get_opt_seq_cost(schedule3)
    print(cost1, cost2, cost3)
    return cost1 + cost2 + cost3, [schedule1, schedule2, schedule3]


if __name__ == "__main__":
    makespan, schedule = get_random_costs()
    print(f"Makespan: {makespan}")
