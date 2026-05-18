"""Integración con Git (capa 8, la final del README). Solo lectura.

El workspace se vuelve un repo git real (`git clone` basta, sin formato
propietario) y se expone su estado. No reimplementa git ni commitea: el dev
commitea/pushea desde su terminal. Ver `repo.py`.
"""

from .repo import EstadoGit, GitRepo

__all__ = ["EstadoGit", "GitRepo"]
