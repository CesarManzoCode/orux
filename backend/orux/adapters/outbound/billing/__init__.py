"""Adapters de billing: Stripe (único proveedor hoy)."""

from .stripe import StripeBillingAdapter

__all__ = ["StripeBillingAdapter"]
