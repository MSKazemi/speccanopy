"""Architecture modeling and deterministic decomposition for Speccanopy."""

from .decomposer import GenerationEvent, GenerationResult, generate_architecture
from .fixtures import FixtureDesign
from .models import (
    ArchitectureDecision,
    ArchitectureSpec,
    Component,
    CoverageReport,
    DesignConstraints,
    FunctionalRequirement,
    InterfaceContract,
    QualityRequirement,
    Relationship,
    SystemBrief,
    ValidationFinding,
    VerificationCase,
)
from .proposer import ComponentProposal, ComponentProposer, FixtureComponentProposer
from .scoring import PriorityFactors, score_priority

__all__ = [
    "ArchitectureDecision",
    "ArchitectureSpec",
    "Component",
    "ComponentProposal",
    "ComponentProposer",
    "CoverageReport",
    "DesignConstraints",
    "FixtureComponentProposer",
    "FixtureDesign",
    "FunctionalRequirement",
    "GenerationEvent",
    "GenerationResult",
    "InterfaceContract",
    "PriorityFactors",
    "QualityRequirement",
    "Relationship",
    "SystemBrief",
    "ValidationFinding",
    "VerificationCase",
    "generate_architecture",
    "score_priority",
]

from .review import (
    ArchitectureReview,
    ExpectedInteraction,
    QualityReview,
    QualityScenario,
    ReviewConfig,
    ReviewFinding,
    ScenarioAssessment,
    StyleComparison,
    StyleDriver,
    assess_architecture,
    compare_styles,
    review_quality,
)
from .review_exporters import export_review, review_markdown

__all__ += [
    "ArchitectureReview", "ExpectedInteraction", "QualityReview", "QualityScenario",
    "ReviewConfig", "ReviewFinding", "ScenarioAssessment", "StyleComparison",
    "StyleDriver", "assess_architecture", "compare_styles", "review_quality",
    "export_review", "review_markdown",
]
