"""Bounded reproducible statistics; missing observations are never successes."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import Any


def wilson(successes: int, n: int) -> tuple[float | None, float | None]:
    if type(successes) is not int or type(n) is not int or not 0 <= successes <= n:
        raise ValueError("Invalid proportion counts")
    if n == 0:
        return None, None
    z = 1.959963984540054
    proportion = successes / n
    denominator = 1 + z * z / n
    center = (proportion + z * z / (2 * n)) / denominator
    half = z * math.sqrt(proportion * (1 - proportion) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def proportion(metric: str, successes: int, n: int, **metadata: Any) -> dict[str, Any]:
    low, high = wilson(successes, n)
    return {
        "metric": metric,
        "value": successes / n if n else None,
        "ciLow": low,
        "ciHigh": high,
        "n": n,
        "successes": successes,
        "ciMethod": "wilson95" if n else None,
        "status": "measured" if n else "not_measured",
        **metadata,
    }


def f1(counts: Sequence[int]) -> float:
    tp, fp, fn = counts
    denominator = 2 * tp + fp + fn
    return 2 * tp / denominator if denominator else 0.0


def bootstrap_f1(
    clusters: Sequence[Sequence[int]], *, samples: int = 1000, seed: int = 20261018
) -> dict[str, Any]:
    if not clusters:
        return {
            "metric": "entity_f1",
            "value": None,
            "ciLow": None,
            "ciHigh": None,
            "n": 0,
            "nCases": 0,
            "status": "not_measured",
            "ciMethod": None,
        }
    if not 100 <= samples <= 10000 or any(any(value < 0 for value in row) for row in clusters):
        raise ValueError("Invalid bootstrap configuration")
    totals = tuple(sum(row[index] for row in clusters) for index in range(3))
    rng = random.Random(seed)
    values = []
    for _ in range(samples):
        draw = rng.choices(clusters, k=len(clusters))
        values.append(f1(tuple(sum(row[index] for row in draw) for index in range(3))))
    values.sort()
    return {
        "metric": "entity_f1",
        "value": f1(totals),
        "ciLow": values[int(samples * 0.025)],
        "ciHigh": values[min(samples - 1, math.ceil(samples * 0.975) - 1)],
        "n": sum(totals),
        "nCases": len(clusters),
        "truePositive": totals[0],
        "falsePositive": totals[1],
        "falseNegative": totals[2],
        "status": "measured",
        "ciMethod": "case_cluster_percentile_bootstrap95",
        "bootstrapSamples": samples,
        "bootstrapSeed": seed,
    }


def distribution(
    values: Sequence[float], *, metric: str, unknown: int = 0, seed: int = 20261018
) -> dict[str, Any]:
    if any(not math.isfinite(value) or value < 0 for value in values) or unknown < 0:
        raise ValueError("Invalid latency or usage measurements")
    if not values:
        return {
            "metric": metric,
            "status": "not_measured",
            "value": None,
            "ciLow": None,
            "ciHigh": None,
            "n": 0,
            "unknown": unknown,
            "p50": None,
            "p95": None,
        }
    ordered = sorted(values)
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(1000))
    return {
        "metric": metric,
        "status": "measured",
        "value": sum(values) / len(values),
        "ciLow": means[25],
        "ciHigh": means[974],
        "n": len(values),
        "unknown": unknown,
        "ciMethod": "observation_percentile_bootstrap_mean95",
        "p50": ordered[math.ceil(len(values) * 0.5) - 1],
        "p95": ordered[math.ceil(len(values) * 0.95) - 1],
    }
