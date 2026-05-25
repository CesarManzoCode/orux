"""Adapters de identidad: tokens HMAC + OAuth GitHub."""

from .github_oauth import GithubOAuthAdapter
from .hmac_session import HmacSessionTokenAdapter

__all__ = ["GithubOAuthAdapter", "HmacSessionTokenAdapter"]
