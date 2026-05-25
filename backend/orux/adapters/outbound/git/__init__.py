"""Adapter Git: envoltura sobre el binario `git`. Cumple `GitPort`."""

from .binary import GitRepo as GitBinaryAdapter
from .binary import GitRepo  # alias para retrocompat

__all__ = ["GitBinaryAdapter", "GitRepo"]
