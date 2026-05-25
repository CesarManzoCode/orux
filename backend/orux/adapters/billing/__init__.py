"""Re-export desde la nueva ubicación tras el refactor hex (2026-05-24).

El adapter Stripe vive ahora en `orux.adapters.outbound.billing`.
"""

from ..outbound.billing import StripeBillingAdapter

__all__ = ["StripeBillingAdapter"]
