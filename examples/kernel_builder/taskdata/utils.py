"""
Self-contained utilities for kernel builder baseline.

This module contains a complete copy of the VLIW SIMD simulator and
run_kernel_test function, making the artifact fully self-contained
without dependencies on other coral modules.
"""

from __future__ import annotations

import random
from copy import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

# =============================================================================
# SIMULATOR CODE (copied from grader/builtin/kernel_builder/simulator.py)
# =============================================================================

Engine = Literal["alu", "load", "store", "flow"]
Instruction = dict[Engine, list[tuple]]


class CoreState(Enum):
    RUNNING = 1
    PAUSED = 2
    STOPPED = 3


@dataclass
class Core:
    id: int
    scratch: list[int]
    trace_buf: list[int]
    pc: int = 0
    state: CoreState = CoreState.RUNNING


@dataclass
class DebugInfo:
    scratch_map: dict[int, tuple[str, int]]


def cdiv(a: int, b: int) -> int:
    return (a + b - 1) // b


SLOT_LIMITS = {
    "alu": 12,
    "valu": 6,
    "load": 2,
    "store": 2,
    "flow": 1,
    "debug": 64,
}

VLEN = 8
N_CORES = 1
SCRATCH_SIZE = 1536
BASE_ADDR_TID = 100000


class Machine:
    """VLIW SIMD simulator."""

    def __init__(
        self,
        mem_dump: list[int],
        program: list[Instruction],
        debug_info: DebugInfo,
        n_cores: int = 1,
        scratch_size: int = SCRATCH_SIZE,
        trace: bool = False,
        value_trace: dict[Any, int] | None = None,
    ):
        if value_trace is None:
            value_trace = {}
        self.cores = [Core(id=i, scratch=[0] * scratch_size, trace_buf=[]) for i in range(n_cores)]
        self.mem = copy(mem_dump)
        self.program = program
        self.debug_info = debug_info
        self.value_trace = value_trace
        self.prints = False
        self.cycle = 0
        self.enable_pause = True
        self.enable_debug = True
        self.trace = None

    def alu(self, core: Core, op: str, dest: int, a1: int, a2: int) -> None:
        a1_val = core.scratch[a1]
        a2_val = core.scratch[a2]
        match op:
            case "+":
                res = a1_val + a2_val
            case "-":
                res = a1_val - a2_val
            case "*":
                res = a1_val * a2_val
            case "//":
                res = a1_val // a2_val
            case "cdiv":
                res = cdiv(a1_val, a2_val)
            case "^":
                res = a1_val ^ a2_val
            case "&":
                res = a1_val & a2_val
            case "|":
                res = a1_val | a2_val
            case "<<":
                res = a1_val << a2_val
            case ">>":
                res = a1_val >> a2_val
            case "%":
                res = a1_val % a2_val
            case "<":
                res = int(a1_val < a2_val)
            case "==":
                res = int(a1_val == a2_val)
            case _:
                raise NotImplementedError(f"Unknown alu op {op}")
        res = res % (2**32)
        self.scratch_write[dest] = res

    def valu(self, core: Core, *slot: Any) -> None:
        match slot:
            case ("vbroadcast", dest, src):
                for i in range(VLEN):
                    self.scratch_write[dest + i] = core.scratch[src]
            case ("multiply_add", dest, a, b, c):
                for i in range(VLEN):
                    mul = (core.scratch[a + i] * core.scratch[b + i]) % (2**32)
                    self.scratch_write[dest + i] = (mul + core.scratch[c + i]) % (2**32)
            case (op, dest, a1, a2):
                for i in range(VLEN):
                    self.alu(core, op, dest + i, a1 + i, a2 + i)
            case _:
                raise NotImplementedError(f"Unknown valu op {slot}")

    def load(self, core: Core, *slot: Any) -> None:
        match slot:
            case ("load", dest, addr):
                self.scratch_write[dest] = self.mem[core.scratch[addr]]
            case ("load_offset", dest, addr, offset):
                self.scratch_write[dest + offset] = self.mem[core.scratch[addr + offset]]
            case ("vload", dest, addr):
                addr_val = core.scratch[addr]
                for vi in range(VLEN):
                    self.scratch_write[dest + vi] = self.mem[addr_val + vi]
            case ("const", dest, val):
                self.scratch_write[dest] = val % (2**32)
            case _:
                raise NotImplementedError(f"Unknown load op {slot}")

    def store(self, core: Core, *slot: Any) -> None:
        match slot:
            case ("store", addr, src):
                addr_val = core.scratch[addr]
                self.mem_write[addr_val] = core.scratch[src]
            case ("vstore", addr, src):
                addr_val = core.scratch[addr]
                for vi in range(VLEN):
                    self.mem_write[addr_val + vi] = core.scratch[src + vi]
            case _:
                raise NotImplementedError(f"Unknown store op {slot}")

    def flow(self, core: Core, *slot: Any) -> None:
        match slot:
            case ("select", dest, cond, a, b):
                self.scratch_write[dest] = (
                    core.scratch[a] if core.scratch[cond] != 0 else core.scratch[b]
                )
            case ("add_imm", dest, a, imm):
                self.scratch_write[dest] = (core.scratch[a] + imm) % (2**32)
            case ("vselect", dest, cond, a, b):
                for vi in range(VLEN):
                    self.scratch_write[dest + vi] = (
                        core.scratch[a + vi]
                        if core.scratch[cond + vi] != 0
                        else core.scratch[b + vi]
                    )
            case ("halt",):
                core.state = CoreState.STOPPED
            case ("pause",):
                if self.enable_pause:
                    core.state = CoreState.PAUSED
            case ("trace_write", val):
                core.trace_buf.append(core.scratch[val])
            case ("cond_jump", cond, addr):
                if core.scratch[cond] != 0:
                    core.pc = addr
            case ("cond_jump_rel", cond, offset):
                if core.scratch[cond] != 0:
                    core.pc += offset
            case ("jump", addr):
                core.pc = addr
            case ("jump_indirect", addr):
                core.pc = core.scratch[addr]
            case ("coreid", dest):
                self.scratch_write[dest] = core.id
            case _:
                raise NotImplementedError(f"Unknown flow op {slot}")

    def step(self, instr: Instruction, core: Core) -> None:
        engine_fns = {
            "alu": self.alu,
            "valu": self.valu,
            "load": self.load,
            "store": self.store,
            "flow": self.flow,
        }
        self.scratch_write: dict[int, int] = {}
        self.mem_write: dict[int, int] = {}
        for name, slots in instr.items():
            if name == "debug":
                continue
            assert len(slots) <= SLOT_LIMITS[name]
            for slot in slots:
                engine_fns[name](core, *slot)
        for addr, val in self.scratch_write.items():
            core.scratch[addr] = val
        for addr, val in self.mem_write.items():
            self.mem[addr] = val


@dataclass
class Tree:
    height: int
    values: list[int]

    @staticmethod
    def generate(height: int) -> Tree:
        n_nodes = 2 ** (height + 1) - 1
        values = [random.randint(0, 2**30 - 1) for _ in range(n_nodes)]
        return Tree(height, values)


@dataclass
class Input:
    indices: list[int]
    values: list[int]
    rounds: int

    @staticmethod
    def generate(forest: Tree, batch_size: int, rounds: int) -> Input:
        indices = [0 for _ in range(batch_size)]
        values = [random.randint(0, 2**30 - 1) for _ in range(batch_size)]
        return Input(indices, values, rounds)


HASH_STAGES = [
    ("+", 0x7ED55D16, "+", "<<", 12),
    ("^", 0xC761C23C, "^", ">>", 19),
    ("+", 0x165667B1, "+", "<<", 5),
    ("+", 0xD3A2646C, "^", "<<", 9),
    ("+", 0xFD7046C5, "+", "<<", 3),
    ("^", 0xB55A4F09, "^", ">>", 16),
]


def myhash(a: int) -> int:
    """A simple 32-bit hash function."""
    fns = {
        "+": lambda x, y: x + y,
        "^": lambda x, y: x ^ y,
        "<<": lambda x, y: x << y,
        ">>": lambda x, y: x >> y,
    }

    def r(x: int) -> int:
        return x % (2**32)

    for op1, val1, op2, op3, val3 in HASH_STAGES:
        a = r(fns[op2](r(fns[op1](a, val1)), r(fns[op3](a, val3))))

    return a


def build_mem_image(t: Tree, inp: Input) -> list[int]:
    """Build a flat memory image of the problem."""
    header = 7
    extra_room = len(t.values) + len(inp.indices) * 2 + VLEN * 2 + 32
    mem = [0] * (header + len(t.values) + len(inp.indices) + len(inp.values) + extra_room)
    forest_values_p = header
    inp_indices_p = forest_values_p + len(t.values)
    inp_values_p = inp_indices_p + len(inp.values)
    extra_room_p = inp_values_p + len(inp.values)

    mem[0] = inp.rounds
    mem[1] = len(t.values)
    mem[2] = len(inp.indices)
    mem[3] = t.height
    mem[4] = forest_values_p
    mem[5] = inp_indices_p
    mem[6] = inp_values_p
    mem[7] = extra_room_p

    mem[header:inp_indices_p] = t.values
    mem[inp_indices_p:inp_values_p] = inp.indices
    mem[inp_values_p : inp_values_p + len(inp.values)] = inp.values
    return mem


def reference_kernel2(mem: list[int], trace: dict[Any, int] | None = None):
    """Reference implementation of the kernel on a flat memory."""
    if trace is None:
        trace = {}
    rounds = mem[0]
    n_nodes = mem[1]
    batch_size = mem[2]
    forest_values_p = mem[4]
    inp_indices_p = mem[5]
    inp_values_p = mem[6]
    yield mem
    for h in range(rounds):
        for i in range(batch_size):
            idx = mem[inp_indices_p + i]
            val = mem[inp_values_p + i]
            node_val = mem[forest_values_p + idx]
            val = myhash(val ^ node_val)
            idx = 2 * idx + (1 if val % 2 == 0 else 2)
            idx = 0 if idx >= n_nodes else idx
            mem[inp_values_p + i] = val
            mem[inp_indices_p + i] = idx
    yield mem


# =============================================================================
# RUN KERNEL TEST (self-contained)
# =============================================================================

# Performance thresholds
BASELINE_CYCLES = 147734


def run_kernel_test(
    kernel_builder_class: type,
    forest_height: int = 10,
    rounds: int = 16,
    batch_size: int = 256,
    seed: int | None = None,
    max_cycles: int = 200000,
) -> tuple[int, bool, str]:
    """
    Run the kernel test and return (cycles, is_correct, error_message).

    This is a self-contained function that includes all simulator logic.

    Args:
        kernel_builder_class: The KernelBuilder class to test
        forest_height: Height of the binary tree
        rounds: Number of traversal rounds
        batch_size: Batch size for parallel traversal
        seed: Random seed (None for random)
        max_cycles: Maximum cycles before aborting

    Returns:
        Tuple of (cycles, is_correct, error_message)
    """
    try:
        # Set random seed if provided
        if seed is not None:
            random.seed(seed)

        # Generate test data
        forest = Tree.generate(forest_height)
        inp = Input.generate(forest, batch_size, rounds)
        mem = build_mem_image(forest, inp)

        # Build kernel
        kb = kernel_builder_class()
        kb.build_kernel(forest.height, len(forest.values), len(inp.indices), rounds)

        # Run simulation with cycle limit
        machine = Machine(mem, kb.instrs, kb.debug_info(), n_cores=N_CORES)
        machine.enable_pause = False
        machine.enable_debug = False

        # Run with cycle limit to prevent infinite loops
        for core in machine.cores:
            if core.state == CoreState.PAUSED:
                core.state = CoreState.RUNNING
        while any(c.state == CoreState.RUNNING for c in machine.cores):
            if machine.cycle >= max_cycles:
                return max_cycles, False, f"Exceeded max cycles ({max_cycles})"
            has_non_debug = False
            for core in machine.cores:
                if core.state != CoreState.RUNNING:
                    continue
                if core.pc >= len(machine.program):
                    core.state = CoreState.STOPPED
                    continue
                instr = machine.program[core.pc]
                core.pc += 1
                machine.step(instr, core)
                if any(name != "debug" for name in instr.keys()):
                    has_non_debug = True
            if has_non_debug:
                machine.cycle += 1

        # Get reference output
        ref_mem = None
        for ref_mem in reference_kernel2(mem):
            pass

        if ref_mem is None:
            return machine.cycle, False, "Reference kernel produced no output"

        # Check correctness
        inp_values_p = ref_mem[6]
        actual = machine.mem[inp_values_p : inp_values_p + len(inp.values)]
        expected = ref_mem[inp_values_p : inp_values_p + len(inp.values)]

        if actual != expected:
            return machine.cycle, False, "Incorrect output values"

        return machine.cycle, True, ""

    except Exception as e:
        return BASELINE_CYCLES * 2, False, str(e)
