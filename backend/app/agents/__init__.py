"""The four connected agents. Each one consumes the previous agent's output."""
from .analysis import EvidenceAnalysisAgent
from .base import AgentError
from .citation import CitationVerificationAgent
from .education import HealthEducationAgent
from .research import ResearchAgent, ResearchOutcome

__all__ = [
    "AgentError",
    "CitationVerificationAgent",
    "EvidenceAnalysisAgent",
    "HealthEducationAgent",
    "ResearchAgent",
    "ResearchOutcome",
]
