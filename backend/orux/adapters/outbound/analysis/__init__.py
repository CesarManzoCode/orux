"""Adapters de análisis semántico (motor y factory LSP)."""

from .lsp_factory import LspFactoryAdapter
from .semantic import SemanticAnalysisAdapter

__all__ = ["LspFactoryAdapter", "SemanticAnalysisAdapter"]
