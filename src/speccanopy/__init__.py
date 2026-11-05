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

from .ai import (
    AIChildrenResponse, AIComponentProposer, AIProposalBundle, AIProposalError,
    AIProposalEvent, ApprovalReceipt, OpenAIResponsesClient, ScriptedProposalClient,
    StructuredProposalClient, approve_proposal_bundle, draft_architecture,
)
from .ai_exporters import export_ai_draft, export_approved, review_packet

__all__ += [
    "AIChildrenResponse", "AIComponentProposer", "AIProposalBundle", "AIProposalError",
    "AIProposalEvent", "ApprovalReceipt", "OpenAIResponsesClient", "ScriptedProposalClient",
    "StructuredProposalClient", "approve_proposal_bundle", "draft_architecture",
    "export_ai_draft", "export_approved", "review_packet",
]

from .refinement import (
    RefinementPatch, RefinementEdits, RefinementPlan, RefinementRound,
    RefinementReceipt, plan_refinement, apply_refinement, simulate_refinement,
)
from .benchmark import (
    ReferenceCriterion, ReferenceRubric, BenchmarkAssessment, BenchmarkComparison,
    evaluate_reference, compare_reference,
)
__all__ += [
    "RefinementPatch", "RefinementEdits", "RefinementPlan", "RefinementRound",
    "RefinementReceipt", "plan_refinement", "apply_refinement", "simulate_refinement",
    "ReferenceCriterion", "ReferenceRubric", "BenchmarkAssessment", "BenchmarkComparison",
    "evaluate_reference", "compare_reference",
]
