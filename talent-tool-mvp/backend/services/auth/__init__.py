"""T2901 — SSO/SAML (Authlib + NextAuth + Keycloak).

Exposes the public surface of the auth package:

* :mod:`services.auth.sso` — SAML 2.0 SP + OIDC RP + JIT provisioning
* :mod:`services.auth.session` — short-lived JWT (15 min) + refresh token (30 d)
* :mod:`services.auth.providers` — registry of 6 IdPs
* :mod:`services.auth.jit` — Just-In-Time account provisioning
"""

from services.auth.sso import (  # noqa: F401
    SSOService,
    SSOProvider,
    SSOProtocol,
    get_sso_service,
)
from services.auth.session import (  # noqa: F401
    SessionManager,
    SSOSession,
    get_session_manager,
)
from services.auth.providers import (  # noqa: F401
    PROVIDER_REGISTRY,
    get_provider_config,
    list_enabled_providers,
)
from services.auth.jit import (  # noqa: F401
    JITProvisioner,
    get_jit_provisioner,
)
