import collections
import json
import numpy as np


class Workload:
    """
    Constructor for taking in transactions and representing them as (read/write, key, position, txn_len)
    """
    def __init__(self, workload_json, debug=False, verify=False):
        self.workload = list(json.loads(workload_json).values())
        self.num_txns = len(self.workload)
        self.debug = debug
        self.verify = verify
        self.txns = []  # list of txns (list of ops)
        self.only_hot_keys = False  # True#
        self.hot_keys_thres = 100
        self.hot_keys = set()
        self.hot_keys_map = {}
        self.sorted_len = None
        self.median_len = 0
        self.conflict_blocks = []
        self.conflict_blocks_map = {}
        self.m = 0

        self.get_txns()

        # get transactions from json and represent hot keys as (r/w, key, position, txn_len)

    def get_txns(self):
        """
        Loads transactions from json and represents them as (read/write, key, position, txn_len)
        """
        key_freqs = {}
        len_map = {}
        lens = []
        for txn in self.workload:  # .values()
            txn_ops = []
            ops = txn.split(" ")
            txn_len = len(ops)
            skip_txn = False
            count = 0
            tmp1 = None
            tmp2 = None
            tmp3 = None
            # ops_map = {}
            # all_ops = []
            for i in range(len(ops)):
                op = ops[i]
                if op != "*":
                    vals = op.split("-")
                    if len(vals) != 2:
                        print(op, vals)
                    assert len(vals) == 2
                    # if i == 0 and int(vals[1]) > 500:
                    #     skip_txn = True
                    #     break
                    if self.only_hot_keys and int(vals[1]) > self.hot_keys_thres:
                        tmp1 = vals[0]
                        tmp2 = vals[1]
                        tmp3 = i + 1
                        continue
                    else:
                        count += 1
                    # sorted reads
                    # if vals[0] == 'r' and vals[1] not in ops_map:
                    #     ops_map[vals[1]] = (vals[0], vals[1], i+1, len(ops))
                    # else:
                    #     all_ops.append((vals[0], vals[1], i+1, len(ops)))
                    txn_ops.append((vals[0], vals[1], i + 1, len(ops)))
                    if vals[1] not in key_freqs:
                        key_freqs[vals[1]] = 1
                    else:
                        key_freqs[vals[1]] += 1
                    if len(ops) not in len_map:
                        len_map[len(ops)] = 1
                    else:
                        len_map[len(ops)] += 1
                    lens.append(len(ops))
            # sorted_keys = collections.OrderedDict(sorted(ops_map.items()))
            # txn_ops = list(sorted_keys.values()) + all_ops
            # assert len(txn_ops) == len(ops)
            # print(sorted_keys, txn_ops)
            if count == 0 and self.only_hot_keys:
                txn_ops.append((tmp1, tmp2, tmp3, len(ops)))
            # if skip_txn:
            #     continue
            self.txns.append(txn_ops)
        if self.debug:
            print(self.txns)
        self.num_txns = len(self.txns)

    # make sure key_map is roughly in order per key
    def insert_key_map(self, key, key_map, op_type, key_start, key_end, txn_id):
        index = len(key_map[key]) - 1
        for op in key_map[key]:
            (_, s, e, _) = key_map[key][index]
            if e <= key_end:
                if s <= key_start:  # e <= key_start or
                    index += 1
                    break
            elif s <= key_start:
                index += 1
                break
            index -= 1
        if index == -1:
            (_, s, e, _) = key_map[key][0]
            if key_end < e and key_start < s:
                key_map[key].insert(0, (op_type, key_start, key_end, txn_id))
            else:
                key_map[key].append((op_type, key_start, key_end, txn_id))
        else:
            key_map[key].insert(index, (op_type, key_start, key_end, txn_id))
        if self.debug:
            print("insert: ", index, key, key_start, key_end, key_map[key])

    # get the index of the first in a consecutive seq. of reads
    def find_earliest_read(self, key, key_map, txn_id):
        # must use latest read if part of same txn
        if key_map[key][-1][3] == txn_id:  # as we're adding to key_map
            print("TXN_ID")
            return key_map[key][-1][1]
        else:
            if self.debug:
                print(key, key_map[key], txn_id)
            index = len(key_map[key]) - 1
            while key_map[key][index][0] == "r":
                if index == -1:
                    break
                index -= 1
        if self.debug:
            print("index: ", index)
        if index == -1:  # can be first read
            index = 0
        else:
            index = key_map[key][index][2] + 1  # after first write found
        return index

    def get_opt_seq_cost(self, txn_seq):
        """
        Gets the makespan of a given sequence of transactions

        Returns
            Value representing the makespan (time to execute given schedule)
        """
        if self.debug:
            print("seq: ", txn_seq)
        key_map = {}  # <key, [(r/w, lock_start, lock_end, txn_id)]>
        prev_txn = txn_seq[0]
        total_cost = 0
        txn_id = 0
        cost_map = {}
        for i in range(len(txn_seq)):
            time = i
            txn = self.txns[txn_seq[i]]
            txn_start = 1
            txn_total_len = 0
            max_release = 0
            cost = 0
            for j in range(len(txn)):
                (op_type, key, pos, txn_len) = txn[j]
                if key in key_map:
                    key_start = 0
                    if key_map[key][-1][0] == "w" or op_type == "w":
                        key_start = (
                            key_map[key][-1][2] + 1
                        )  # get end time of latest lock end
                    else:
                        key_start = self.find_earliest_read(key, key_map, txn_id)
                        # key_start = key_map[key][-1][1] #pos # read locks shared
                    txn_start = max(
                        txn_start, key_start - pos + 1
                    )  # place txn start behind conflicting locks
                    if self.debug:
                        print(key, key_start, pos, txn_start)
                    max_release = max(
                        max_release, key_start - 1
                    )  # latest release of all locks
                txn_total_len = txn_len
            txn_end = txn_start + txn_total_len - 1
            cost = txn_end - total_cost  # max_release
            # if max_release == 0:
            if (
                txn_end <= total_cost
            ):  # in some cases, later txn in seq can finish first
                cost = 0
            # else:
            #     cost = txn_end - total_cost
            if cost in cost_map:
                cost_map[cost] += 1
            else:
                cost_map[cost] = 1
            total_cost += cost
            if self.debug:
                print(txn, txn_start, txn_end, max_release, cost, total_cost)

            curr_txn = txn_seq[i]
            prev_txn = curr_txn
            if self.debug:
                print(txn_start, txn_end, max_release, cost)

            for j in range(len(txn)):
                (op_type, key, pos, txn_len) = txn[j]
                key_start = txn_start + pos - 1
                if key in key_map:
                    if key_map[key][-1][0] == "w" or op_type == "w":
                        self.insert_key_map(
                            key, key_map, op_type, key_start, key_start, txn_id
                        )
                        # key_map[key].append((op_type, key_start, key_start, txn_id))
                    else:
                        self.insert_key_map(
                            key, key_map, op_type, key_start, key_start, txn_id
                        )
                        # key_map[key].append((op_type, key_start, key_start, txn_id))
                else:
                    key_map[key] = [(op_type, key_start, key_start, txn_id)]
            if self.debug:
                print(key_map)
            txn_id += 1
        if self.debug:
            print(total_cost)

        # print(key_map)
        od = collections.OrderedDict(sorted(cost_map.items()))
        # print(od.keys())
        # print(od.values())
        return total_cost

