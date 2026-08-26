"""Investment Council — multi-persona strategy research module."""

from .engine import CouncilEngine, UnderlyingAssessment
from .personas import PERSONAS, DEFAULT_WEIGHTS, PersonaVerdict
from .report import generate_report

__all__ = ["CouncilEngine", "UnderlyingAssessment", "PersonaVerdict",
           "PERSONAS", "DEFAULT_WEIGHTS", "generate_report"]
