"""Baseline solution for the DNA Enhancer Design task.

Generates 200bp DNA sequences optimized for HepG2 enhancer activity.
Uses simple random generation with GC content filtering as a starting point.

Must define run() -> list[str] returning DNA sequences of length 200.
"""

import random

BASES = "ATGC"
SEQ_LENGTH = 200
NUM_SEQUENCES = 100
NUM_GENERATIONS = 5
POPULATION_SIZE = 100
MUTATION_RATE = 0.05


def random_sequence(length: int = SEQ_LENGTH) -> str:
    """Generate a random DNA sequence with balanced GC content."""
    # Bias toward ~50% GC content for stability
    weights = [0.25, 0.25, 0.25, 0.25]  # A, T, G, C
    return "".join(random.choices(BASES, weights=weights, k=length))


def gc_content(seq: str) -> float:
    """Calculate GC content of a sequence."""
    gc = sum(1 for b in seq if b in "GC")
    return gc / len(seq)


def mutate(seq: str, rate: float = MUTATION_RATE) -> str:
    """Apply random point mutations to a sequence."""
    seq_list = list(seq)
    for i in range(len(seq_list)):
        if random.random() < rate:
            seq_list[i] = random.choice(BASES)
    return "".join(seq_list)


def crossover(seq1: str, seq2: str) -> str:
    """Single-point crossover between two sequences."""
    point = random.randint(1, len(seq1) - 1)
    return seq1[:point] + seq2[point:]


def run() -> list[str]:
    """Generate optimized DNA enhancer sequences.

    Returns:
        List of DNA sequences, each exactly 200 bases long.
    """
    # Generate initial population with GC content filtering
    population = []
    while len(population) < POPULATION_SIZE:
        seq = random_sequence()
        gc = gc_content(seq)
        if 0.35 <= gc <= 0.65:
            population.append(seq)

    # Simple evolutionary optimization (no scorer — just diversity + GC heuristics)
    for gen in range(NUM_GENERATIONS):
        # Score by GC content proximity to 0.5 and sequence diversity
        scored = []
        for seq in population:
            gc = gc_content(seq)
            gc_score = 1.0 - abs(gc - 0.5) * 4  # peaks at GC=0.5
            scored.append((gc_score, seq))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Select top half
        survivors = [seq for _, seq in scored[: POPULATION_SIZE // 2]]

        # Generate offspring
        offspring = []
        while len(offspring) < POPULATION_SIZE // 2:
            p1, p2 = random.sample(survivors, 2)
            child = crossover(p1, p2)
            child = mutate(child)
            offspring.append(child)

        population = survivors + offspring

    # Return top sequences by GC content quality
    scored = [(1.0 - abs(gc_content(s) - 0.5) * 4, s) for s in population]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [seq for _, seq in scored[:NUM_SEQUENCES]]
