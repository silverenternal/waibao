"""T2903 — Third-party Application Marketplace.

Sub-modules:

* :mod:`catalog`    — listings & releases (publish / approve / search)
* :mod:`install`    — install/uninstall delegating to v6.0 Plugin SDK
* :mod:`reviews`    — user reviews & ratings
* :mod:`billing`    — Stripe / WeChat Pay purchase ledger
* :mod:`service`    — unified facade for the API layer

The Strapi admin UI is the *primary* moderator surface for the
marketplace; this Python module is the *system of record* and the
hot-path integration glue. Strapi can be enabled / disabled via
the ``MARKETPLACE_STRAPI_URL`` env var. When unset the local Supabase
tables are the source of truth and audit/notify still work.
"""
from .service import (
    MarketplaceService,
    get_marketplace_service,
    reset_marketplace_service,
    MarketplaceError,
    PluginNotFoundError,
    PluginNotApprovedError,
    PluginVersionMismatchError,
    PublishValidationError,
    ReviewValidationError,
)
from .reviews import ReviewNotFoundError

__all__ = [
    "MarketplaceService",
    "get_marketplace_service",
    "reset_marketplace_service",
    "MarketplaceError",
    "PluginNotFoundError",
    "PluginNotApprovedError",
    "PluginVersionMismatchError",
    "PublishValidationError",
    "ReviewValidationError",
    "ReviewNotFoundError",
]
