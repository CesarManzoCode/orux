"""Análisis semántico de impacto (capa 6). Por ahora solo Python.

Un solo módulo `python` a propósito: el README marca como riesgo #2 querer
multi-lenguaje antes de tiempo. No hay capa de abstracción de lenguajes
todavía porque no hay un segundo lenguaje — se introducirá cuando exista,
no antes.
"""

from .python import definiciones_top, impacto, referencias, simbolos_cambiados

__all__ = [
    "definiciones_top",
    "impacto",
    "referencias",
    "simbolos_cambiados",
]
