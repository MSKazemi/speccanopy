"""Transparent, configurable starting heuristic for design-attention priority.

These values are not proofs of architectural importance. The fixture author
supplies the estimates and the engine keeps mandatory requirements regardless
of scores.
"""

from __future__ import annotations

from pydantic import Field

from .models import SchemaModel


class PriorityFactors(SchemaModel):
    value: float = Field(default=0, ge=0, le=10)
    risk: float = Field(default=0, ge=0, le=10)
    dependency: float = Field(default=0, ge=0, le=10)
    quality_impact: float = Field(default=0, ge=0, le=10)
    uncertainty: float = Field(default=0, ge=0, le=10)


def score_priority(factors: PriorityFactors | None) -> float:
    """Score 0-10. No supplied estimates means neutral 0, not a guess."""
    if factors is None:
        return 0.0
    return round(
        0.30 * factors.value
        + 0.25 * factors.risk
        + 0.20 * factors.dependency
        + 0.15 * factors.quality_impact
        + 0.10 * factors.uncertainty,
        4,
    )
