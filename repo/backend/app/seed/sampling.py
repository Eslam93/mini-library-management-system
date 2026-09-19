"""Seeded randomness. Every draw goes through a random.Random made from the seed and a stream
name, so the same seed gives the same library, and extra draws in one stream do not shift the
others.
"""

import math
import random
import uuid
from collections.abc import Mapping, Sequence


def stream(seed: int, name: str) -> random.Random:
    # A string seed is hashed with SHA-512, so it does not depend on PYTHONHASHSEED. Demo data
    # needs reproducible draws, not secrets.
    return random.Random(f"{seed}/{name}")  # noqa: S311


def new_id(rng: random.Random) -> uuid.UUID:
    """A reproducible id with the layout of a random (version 4) UUID."""
    return uuid.UUID(int=rng.getrandbits(128), version=4)


def pick[T](rng: random.Random, weights: Mapping[T, float]) -> T:
    """One key, drawn in proportion to its weight."""
    keys = list(weights)
    return rng.choices(keys, weights=[weights[key] for key in keys])[0]


def split_count(total: int, shares: Sequence[float]) -> list[int]:
    """Whole numbers in proportion to shares that add up to total. The rounding goes to the
    largest remainders, so 10 split by (1, 1, 1) is (4, 3, 3).
    """
    scale = total / sum(shares)
    exact = [share * scale for share in shares]
    counts = [math.floor(value) for value in exact]
    by_remainder = sorted(range(len(shares)), key=lambda i: (counts[i] - exact[i], i))
    for i in by_remainder[: total - sum(counts)]:
        counts[i] += 1
    return counts


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
