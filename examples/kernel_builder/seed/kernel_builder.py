"""
Baseline KernelBuilder for kernel optimization.

This is the naive scalar implementation that serves as the starting point
for optimization. It processes one element at a time without exploiting
VLIW parallelism or SIMD vectorization.

Key optimization opportunities:
1. VLIW: Pack multiple operations per cycle (up to 12 ALU, 6 VALU, 2 load, 2 store)
2. SIMD: Use vector operations (VLEN=8) to process 8 elements at once
3. Loop unrolling: Reduce loop overhead
4. Memory access patterns: Use vload/vstore for contiguous access
5. Instruction scheduling: Avoid dependencies, maximize ILP

Performance:
- Baseline: ~147,734 cycles
- Best known: ~1,363 cycles (108x speedup)

This file is self-contained and can be executed via exec() for grading.
"""

from dataclasses import dataclass

# Constants for the VLIW SIMD machine
SCRATCH_SIZE = 1536

# Hash function stages: (op1, val1, op2, op3, val3)
# Each stage computes: val = op2(op1(val, val1), op3(val, val3))
HASH_STAGES = [
    ("+", 0x7ED55D16, "+", "<<", 12),
    ("^", 0xC761C23C, "^", ">>", 19),
    ("+", 0x165667B1, "+", "<<", 5),
    ("+", 0xD3A2646C, "^", "<<", 9),
    ("+", 0xFD7046C5, "+", "<<", 3),
    ("^", 0xB55A4F09, "^", ">>", 16),
]


@dataclass
class DebugInfo:
    """Debug information for the simulator."""

    scratch_map: dict[int, tuple[str, int]]


class KernelBuilder:
    """
    Kernel builder for the VLIW SIMD machine.

    This class builds a program (list of instructions) that implements
    the tree traversal algorithm. Each instruction is a dict mapping
    engine names to lists of operations.

    Engines and slot limits per cycle:
    - alu: 12 scalar operations
    - valu: 6 vector operations (each on VLEN=8 elements)
    - load: 2 memory reads
    - store: 2 memory writes
    - flow: 1 control flow operation
    """

    def __init__(self):
        self.instrs = []
        self.scratch = {}
        self.scratch_debug = {}
        self.scratch_ptr = 0
        self.const_map = {}
        # pending slots collected during kernel construction; these will be
        # packed together with the main body to produce efficient VLIW
        # instructions. Using a pending list avoids emitting many single-slot
        # instructions via self.add() which prevented global packing.
        self.pending_slots = []

    def debug_info(self):
        """Return debug info for the simulator."""
        return DebugInfo(scratch_map=self.scratch_debug)

    def build(self, slots, vliw=False):
        """
        Pack a list of (engine, operation) tuples into VLIW instructions.

        This greedy packer tries to fill available engine slots per cycle
        while preserving correctness: it forbids packing two operations
        into the same instruction when one reads a scratch location that
        another operation in the same instruction writes. It also forbids
        multiple writes to the same scratch location in one instruction.

        This significantly reduces cycle count by emitting fewer
        instructions (one instruction can contain multiple slots).
        """
        instrs = []
        # Slot limits per engine
        limits = {"alu": 12, "valu": 6, "load": 2, "store": 2, "flow": 1}

        def rw_for_slot(engine: str, slot: tuple):
            """Return (reads:set, writes:set) scratch indices for the slot."""
            reads = set()
            writes = set()
            # slot may be like ("+", dst, a, b) for alu, or for load engine the slot
            # itself encodes op name such as ("load", dst, addr) or ("const", dst, val)
            if engine == "alu":
                _, dst, a, b = slot
                reads.update([a, b])
                writes.add(dst)
            elif engine == "load":
                op = slot[0]
                if op == "load":
                    _, dst, addr = slot
                    reads.add(addr)
                    writes.add(dst)
                elif op == "load_offset":
                    _, dst, addr, offset = slot
                    reads.add(addr + offset)
                    writes.add(dst + offset)
                elif op == "vload":
                    _, dst, addr = slot
                    reads.add(addr)
                    writes.update(range(dst, dst + 8))
                elif op == "const":
                    _, dst, _ = slot
                    writes.add(dst)
                else:
                    # conservative default
                    try:
                        _, dst, addr = slot
                        reads.add(addr)
                        writes.add(dst)
                    except Exception:
                        pass
            elif engine == "store":
                op = slot[0]
                if op == "store":
                    _, addr, src = slot
                    reads.update([addr, src])
                elif op == "vstore":
                    _, addr, src = slot
                    reads.add(addr)
                    reads.update(range(src, src + 8))
                else:
                    try:
                        _, addr, src = slot
                        reads.update([addr, src])
                    except Exception:
                        pass
            elif engine == "flow":
                op = slot[0]
                if op == "select":
                    _, dst, cond, a, b = slot
                    reads.update([cond, a, b])
                    writes.add(dst)
                elif op == "vselect":
                    _, dst, cond, a, b = slot
                    reads.update(range(cond, cond + 8))
                    reads.update(range(a, a + 8))
                    reads.update(range(b, b + 8))
                    writes.update(range(dst, dst + 8))
                elif op == "add_imm":
                    _, dst, a, _ = slot
                    reads.add(a)
                    writes.add(dst)
                elif op == "trace_write":
                    _, val = slot
                    reads.add(val)
                elif op in ("cond_jump", "cond_jump_rel"):
                    _, cond, _ = slot
                    reads.add(cond)
                elif op == "jump_indirect":
                    _, addr = slot
                    reads.add(addr)
                elif op == "coreid":
                    _, dst = slot
                    writes.add(dst)
                else:
                    # ops like pause/halt/jump have no scratch effects
                    pass
            elif engine == "valu":
                # valu ops operate on vectors; they read/write contiguous ranges
                op = slot[0]
                if op == "vbroadcast":
                    _, dst, src = slot
                    reads.add(src)
                    writes.update(range(dst, dst + 8))
                elif op == "multiply_add":
                    _, dst, a, b, c = slot
                    reads.update(range(a, a + 8))
                    reads.update(range(b, b + 8))
                    reads.update(range(c, c + 8))
                    writes.update(range(dst, dst + 8))
                else:
                    # generic binary op: (op, dst, a, b)
                    try:
                        _, dst, a, b = slot
                        reads.update(range(a, a + 8))
                        reads.update(range(b, b + 8))
                        writes.update(range(dst, dst + 8))
                    except Exception:
                        pass
            else:
                # conservative: no info
                pass
            return reads, writes

        i = 0
        n = len(slots)
        while i < n:
            instr = {}
            used = {"alu": 0, "valu": 0, "load": 0, "store": 0, "flow": 0}
            curr_reads = set()
            curr_writes = set()
            # try to pack as many following slots as possible
            j = i
            while j < n:
                engine, slot = slots[j]
                if used.get(engine, 0) >= limits.get(engine, 0):
                    break
                reads, writes = rw_for_slot(engine, slot)
                # forbid if this slot reads something written earlier in this instr
                if reads & curr_writes:
                    break
                # forbid if this slot writes something already written in this instr
                if writes & curr_writes:
                    break
                # all good; add
                instr.setdefault(engine, []).append(slot)
                used[engine] = used.get(engine, 0) + 1
                curr_reads |= reads
                curr_writes |= writes
                j += 1
            # if we couldn't pack even a single slot (shouldn't happen), force one
            if i == j:
                engine, slot = slots[i]
                instr.setdefault(engine, []).append(slot)
                i += 1
            else:
                i = j
            instrs.append(instr)
        return instrs

    def add(self, engine, slot):
        """Add a single-slot instruction into pending slots for later packing.

        Storing slots in pending_slots instead of emitting immediate single-slot
        instructions allows the global packer (build) to consider constants,
        broadcasts and header loads together with the main body and pack them
        into full VLIW words. This reduces instruction count and improves
        utilization across engines.
        """
        self.pending_slots.append((engine, slot))

    def alloc_scratch(self, name=None, length=1):
        """Allocate scratch space (like registers)."""
        addr = self.scratch_ptr
        if name is not None:
            self.scratch[name] = addr
            self.scratch_debug[addr] = (name, length)
        self.scratch_ptr += length
        assert self.scratch_ptr <= SCRATCH_SIZE, "Out of scratch space"
        return addr

    def scratch_const(self, val, name=None):
        """Load a constant into scratch space, reusing if already loaded."""
        if val not in self.const_map:
            addr = self.alloc_scratch(name)
            self.add("load", ("const", addr, val))
            self.const_map[val] = addr
        return self.const_map[val]

    def build_hash(self, val_hash_addr, tmp1, tmp2, round, i):
        """
        Build instructions for the hash function.

        The hash function has 6 stages, each with:
        - First ALU op: tmp1 = val op1 const
        - Second ALU op: tmp2 = val op3 const
        - Third ALU op: val = tmp1 op2 tmp2
        """
        slots = []
        for hi, (op1, val1, op2, op3, val3) in enumerate(HASH_STAGES):
            slots.append(("alu", (op1, tmp1, val_hash_addr, self.scratch_const(val1))))
            slots.append(("alu", (op3, tmp2, val_hash_addr, self.scratch_const(val3))))
            slots.append(("alu", (op2, val_hash_addr, tmp1, tmp2)))
        return slots

    def scratch_const_vector(self, val, name=None):
        """Create or return a vectorized broadcast of an immediate constant.

        This allocates an 8-word scratch and emits a vbroadcast valu slot that
        fills it with the scalar constant. The scalar constant itself is
        allocated via scratch_const and will be reused.
        """
        if not hasattr(self, "const_vec_map"):
            self.const_vec_map = {}
        if val not in self.const_vec_map:
            scalar = self.scratch_const(val)
            vec = self.alloc_scratch(name, length=8)
            # Emit a vbroadcast to fill vector scratch
            self.add("valu", ("vbroadcast", vec, scalar))
            self.const_vec_map[val] = vec
        return self.const_vec_map[val]

    def build_hash_vector(self, val_vec_addr, tmp1_vec, tmp2_vec):
        """Build vectorized hash stages operating on 8 lanes.

        Uses valu operations and vbroadcasted constant vectors.
        """
        slots = []
        for op1, val1, op2, op3, val3 in HASH_STAGES:
            c1 = self.scratch_const_vector(val1)
            c3 = self.scratch_const_vector(val3)
            slots.append(("valu", (op1, tmp1_vec, val_vec_addr, c1)))
            slots.append(("valu", (op3, tmp2_vec, val_vec_addr, c3)))
            slots.append(("valu", (op2, val_vec_addr, tmp1_vec, tmp2_vec)))
        return slots

    def build_kernel(self, forest_height, n_nodes, batch_size, rounds):
        """
        Build the main kernel with SIMD (VLEN=8) vectorization for the batch
        dimension. This version processes 8 elements at a time using valu
        operations and vload/vstore where possible. Remaining tail elements
        (batch_size % 8) are handled with the scalar fallback.
        """
        # Scalars used for occasional scalar ops
        tmp_addr = self.alloc_scratch("tmp_addr")
        tmp_addr2 = self.alloc_scratch("tmp_addr2")

        # Load initial values from memory header into reserved scratches
        init_vars = [
            "rounds",
            "n_nodes",
            "batch_size",
            "forest_height",
            "forest_values_p",
            "inp_indices_p",
            "inp_values_p",
        ]
        for v in init_vars:
            self.alloc_scratch(v, 1)
        # use a temp scalar to load the header
        header_tmp = self.alloc_scratch("header_tmp")
        for i, v in enumerate(init_vars):
            self.add("load", ("const", header_tmp, i))
            self.add("load", ("load", self.scratch[v], header_tmp))

        # Vector temporaries (each length=8)
        idx_vec = self.alloc_scratch("idx_vec", length=8)
        val_vec = self.alloc_scratch("val_vec", length=8)
        node_addr_vec = self.alloc_scratch("node_addr_vec", length=8)
        node_val_vec = self.alloc_scratch("node_val_vec", length=8)
        hash_tmp1_vec = self.alloc_scratch("hash_tmp1_vec", length=8)
        hash_tmp2_vec = self.alloc_scratch("hash_tmp2_vec", length=8)
        mod_vec = self.alloc_scratch("mod_vec", length=8)
        add1_vec = self.alloc_scratch("add1_vec", length=8)
        mask_vec = self.alloc_scratch("mask_vec", length=8)

        # Broadcasted vector constants
        one_vec = self.scratch_const_vector(1, name="one_vec")
        self.scratch_const_vector(2, name="two_vec")

        # Broadcast scalar header values into vector registers for comparisons/adds
        n_nodes_vec = self.alloc_scratch("n_nodes_vec", length=8)
        self.add("valu", ("vbroadcast", n_nodes_vec, self.scratch["n_nodes"]))
        forest_base_vec = self.alloc_scratch("forest_base_vec", length=8)
        self.add("valu", ("vbroadcast", forest_base_vec, self.scratch["forest_values_p"]))

        # Pre-create a zero vector constant for vselect operations to avoid
        # re-emitting the vbroadcast inside the inner rounds loop.
        zero_vec = self.scratch_const_vector(0)

        body = []

        # Vectorized main loop: process 8 elements per iteration
        vec_step = 8
        vec_iters = batch_size // vec_step
        tail = batch_size % vec_step

        # Pre-allocate scalar temporaries used by tail handling to avoid
        # repeated allocations inside the inner loop which bloated the
        # instruction stream and exhausted scratch space.
        tmp_idx_tail = self.alloc_scratch("tmp_idx_tail")
        tmp_val_tail = self.alloc_scratch("tmp_val_tail")
        tmp_node_val_tail = self.alloc_scratch("tmp_node_val_tail")
        h_tmp1 = self.alloc_scratch("h_tmp1")
        h_tmp2 = self.alloc_scratch("h_tmp2")
        tmp3_tail = self.alloc_scratch("tmp3_tail")
        one_const = self.scratch_const(1)
        two_const = self.scratch_const(2)

        for vi in range(vec_iters):
            i = vi * vec_step
            i_const = self.scratch_const(i)

            # Load 8 indices and 8 values (contiguous) using vload
            body.append(("alu", ("+", tmp_addr, self.scratch["inp_indices_p"], i_const)))
            body.append(("load", ("vload", idx_vec, tmp_addr)))

            body.append(("alu", ("+", tmp_addr2, self.scratch["inp_values_p"], i_const)))
            body.append(("load", ("vload", val_vec, tmp_addr2)))

            # Process all rounds in registers to reduce vload/vstore overhead
            for r in range(rounds):
                # Compute addresses of node values: node_addr_vec = forest_base + idx_vec
                body.append(("valu", ("+", node_addr_vec, idx_vec, forest_base_vec)))

                # Gather node values: use 8 load_offset slots (one per lane)
                for lane in range(8):
                    body.append(("load", ("load_offset", node_val_vec, node_addr_vec, lane)))

                # XOR value with node_val and compute hash (vectorized)
                body.append(("valu", ("^", val_vec, val_vec, node_val_vec)))
                body.extend(self.build_hash_vector(val_vec, hash_tmp1_vec, hash_tmp2_vec))

                # Compute parity-based child: add1 = 1 + (val & 1) -> 1 if even, 2 if odd
                body.append(("valu", ("&", mod_vec, val_vec, one_vec)))
                body.append(("valu", ("+", add1_vec, mod_vec, one_vec)))

                # idx = 2*idx + add1_vec (use shift left to compute *2)
                body.append(("valu", ("<<", idx_vec, idx_vec, one_vec)))
                body.append(("valu", ("+", idx_vec, idx_vec, add1_vec)))

                # idx = idx if idx < n_nodes else 0 -> use vselect to avoid extra multiply valu
                body.append(("valu", ("<", mask_vec, idx_vec, n_nodes_vec)))
                body.append(("flow", ("vselect", idx_vec, mask_vec, idx_vec, zero_vec)))

            # Store updated indices and values back (contiguous) using vstore
            body.append(("alu", ("+", tmp_addr, self.scratch["inp_indices_p"], i_const)))
            body.append(("store", ("vstore", tmp_addr, idx_vec)))

            body.append(("alu", ("+", tmp_addr2, self.scratch["inp_values_p"], i_const)))
            body.append(("store", ("vstore", tmp_addr2, val_vec)))

            # Tail scalar fallback for remaining elements
            if tail:
                start = vec_iters * vec_step
                for i in range(start, start + tail):
                    i_const = self.scratch_const(i)
                    # idx = mem[inp_indices_p + i]
                    body.append(("alu", ("+", tmp_addr, self.scratch["inp_indices_p"], i_const)))
                    body.append(("load", ("load", tmp_idx_tail, tmp_addr)))

                    # val = mem[inp_values_p + i]
                    body.append(("alu", ("+", tmp_addr2, self.scratch["inp_values_p"], i_const)))
                    body.append(("load", ("load", tmp_val_tail, tmp_addr2)))

                    # Process rounds in scalar registers
                    for r in range(rounds):
                        # node_val = mem[forest_values_p + idx]
                        body.append(
                            ("alu", ("+", tmp_addr, self.scratch["forest_values_p"], tmp_idx_tail))
                        )
                        body.append(("load", ("load", tmp_node_val_tail, tmp_addr)))

                        # val = myhash(val ^ node_val)
                        body.append(("alu", ("^", tmp_val_tail, tmp_val_tail, tmp_node_val_tail)))
                        body.extend(self.build_hash(tmp_val_tail, h_tmp1, h_tmp2, r, i))

                        # idx = 2*idx + (1 if val % 2 == 0 else 2)
                        body.append(("alu", ("%", tmp_idx_tail, tmp_val_tail, two_const)))
                        body.append(("alu", ("+", tmp3_tail, tmp_idx_tail, one_const)))
                        body.append(("alu", ("*", tmp_idx_tail, tmp_idx_tail, two_const)))
                        body.append(("alu", ("+", tmp_idx_tail, tmp_idx_tail, tmp3_tail)))

                        # idx = 0 if idx >= n_nodes else idx
                        body.append(
                            ("alu", ("<", tmp_idx_tail, tmp_idx_tail, self.scratch["n_nodes"]))
                        )
                        body.append(("alu", ("*", tmp_idx_tail, tmp_idx_tail, tmp_idx_tail)))

                    # mem[inp_indices_p + i] = idx
                    body.append(("alu", ("+", tmp_addr, self.scratch["inp_indices_p"], i_const)))
                    body.append(("store", ("store", tmp_addr, tmp_idx_tail)))

                    # mem[inp_values_p + i] = val
                    body.append(("alu", ("+", tmp_addr2, self.scratch["inp_values_p"], i_const)))
                    body.append(("store", ("store", tmp_addr2, tmp_val_tail)))

        # Pack into VLIW instructions
        # Include any pending slots (constants, broadcasts, header loads) so
        # they can be packed together with the main body. This reduces
        # instruction count and improves slot utilization.
        all_slots = self.pending_slots + body
        body_instrs = self.build(all_slots)
        self.instrs.extend(body_instrs)

        # Clear pending slots now that they've been emitted
        self.pending_slots = []

        # Final pause
        self.instrs.append({"flow": [("pause",)]})
