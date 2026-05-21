"""Integración con Git: el workspace ES un repo git real.

El workspace se vuelve un repo git real (`git clone` basta, sin formato
propietario) y se expone su estado: rama, archivos sin commitear, últimos
commits. Capa 8 (solo lectura) + capa 9 (commit desde la app) + capa 10
(clone destructivo + push con credenciales efímeras) + capa 21 (push a
rama de publicación + force-with-lease). No reimplementa git: invoca el
binario y endurece su entorno (allowlist de URLs, `core.hooksPath` cerrado,
env filtrado contra exfiltración por hooks maliciosos del remoto).
Ver `repo.py`.
"""

from .repo import EstadoGit, GitRepo

__all__ = ["EstadoGit", "GitRepo"]
