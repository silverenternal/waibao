"""T2901 — SSO provider registry.

Each supported IdP is described by a :class:`ProviderConfig` record that
captures the wire protocol (SAML 2.0 or OIDC), the issuer URL, the client
credentials, the SCIM / JIT mapping, and the display metadata used by the
frontend.

The registry is intentionally data-driven so the rest of the system can
iterate over ``PROVIDER_REGISTRY`` without hard-coding provider names.

Phase 1 (T2901) ships 6 IdPs:

* **Okta** — SAML 2.0 (enterprise standard)
* **Azure AD** — OIDC (Microsoft Entra ID)
* **Google Workspace** — OIDC
* **DingTalk** — OIDC (custom non-standard endpoints)
* **Feishu** — OIDC (custom non-standard endpoints)
* **WeCom** — OIDC (custom non-standard endpoints)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SSOProtocol(str, Enum):
    """Wire protocol the SP uses to talk to the IdP."""

    SAML2 = "saml2"
    OIDC = "oidc"


class ProviderCategory(str, Enum):
    """Coarse classification used for the login UI grouping."""

    ENTERPRISE = "enterprise"  # Okta / Azure AD / Google Workspace
    CN = "cn"  # DingTalk / Feishu / WeCom


@dataclass(frozen=True)
class ProviderConfig:
    """Static + runtime configuration for a single IdP."""

    # Identity (must be URL-safe)
    slug: str
    display_name: str
    category: ProviderCategory
    protocol: SSOProtocol

    # OIDC specific
    issuer: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    userinfo_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None
    scopes: List[str] = field(default_factory=lambda: ["openid", "email", "profile"])

    # SAML specific
    sso_url: Optional[str] = None  # IdP SSO endpoint
    entity_id: Optional[str] = None  # IdP entity ID
    slo_url: Optional[str] = None  # Single Logout
    x509_cert: Optional[str] = None  # IdP signing certificate (PEM, no headers)

    # Behaviour flags
    enabled: bool = True
    jit_provisioning: bool = True
    default_org_role: str = "member"
    email_domain_whitelist: Optional[List[str]] = None  # None = no restriction
    email_domain_blacklist: Optional[List[str]] = None

    # Display
    icon: str = "shield"  # lucide-react icon name
    color: str = "default"
    description: str = ""

    # Lookup keys the IdP uses for the canonical user identity
    id_claim: str = "sub"  # OIDC: `sub`; SAML: NameID
    email_claim: str = "email"
    name_claim: str = "name"
    given_name_claim: str = "given_name"
    family_name_claim: str = "family_name"
    picture_claim: str = "picture"
    groups_claim: str = "groups"

    def public_dict(self) -> Dict[str, Any]:
        """Return the data shape exposed to the frontend (no secrets)."""
        return {
            "slug": self.slug,
            "display_name": self.display_name,
            "category": self.category.value,
            "protocol": self.protocol.value,
            "enabled": self.enabled,
            "icon": self.icon,
            "color": self.color,
            "description": self.description,
            "scopes": self.scopes,
        }

    def validate_email_domain(self, email: str) -> bool:
        """Apply whitelist/blacklist; ``True`` means the email is allowed."""
        if not email or "@" not in email:
            return False
        domain = email.split("@", 1)[1].lower()
        if self.email_domain_whitelist:
            if domain not in {d.lower() for d in self.email_domain_whitelist}:
                return False
        if self.email_domain_blacklist:
            if domain in {d.lower() for d in self.email_domain_blacklist}:
                return False
        return True


# ---------------------------------------------------------------------------
# Provider constructors
# ---------------------------------------------------------------------------

def _okta() -> ProviderConfig:
    return ProviderConfig(
        slug="okta",
        display_name="Okta",
        category=ProviderCategory.ENTERPRISE,
        protocol=SSOProtocol.SAML2,
        sso_url=os.getenv("OKTA_SSO_URL", "https://example.okta.com/app/recruittech/sso/saml"),
        entity_id=os.getenv("OKTA_ENTITY_ID", "http://www.okta.com/exk_example"),
        slo_url=os.getenv("OKTA_SLO_URL"),
        x509_cert=os.getenv("OKTA_X509_CERT"),
        icon="shield-check",
        color="blue",
        description="Enterprise SAML 2.0 SSO via Okta",
        email_domain_whitelist=os.getenv("OKTA_EMAIL_WHITELIST", "").split(",")
        if os.getenv("OKTA_EMAIL_WHITELIST")
        else None,
    )


def _azure_ad() -> ProviderConfig:
    tenant = os.getenv("AZURE_TENANT_ID", "common")
    base = f"https://login.microsoftonline.com/{tenant}"
    return ProviderConfig(
        slug="azure_ad",
        display_name="Microsoft Entra ID",
        category=ProviderCategory.ENTERPRISE,
        protocol=SSOProtocol.OIDC,
        issuer=os.getenv("AZURE_ISSUER", f"{base}/v2.0"),
        authorization_endpoint=os.getenv(
            "AZURE_AUTHZ_ENDPOINT", f"{base}/oauth2/v2.0/authorize"
        ),
        token_endpoint=os.getenv("AZURE_TOKEN_ENDPOINT", f"{base}/oauth2/v2.0/token"),
        userinfo_endpoint=os.getenv("AZURE_USERINFO_ENDPOINT", f"{base}/openid/userinfo"),
        jwks_uri=os.getenv("AZURE_JWKS_URI", f"{base}/discovery/v2.0/keys"),
        scopes=["openid", "email", "profile", "offline_access"],
        icon="microsoft",
        color="indigo",
        description="Microsoft Entra ID (Azure AD) OIDC",
    )


def _google() -> ProviderConfig:
    base = "https://accounts.google.com"
    return ProviderConfig(
        slug="google",
        display_name="Google Workspace",
        category=ProviderCategory.ENTERPRISE,
        protocol=SSOProtocol.OIDC,
        issuer=os.getenv("GOOGLE_ISSUER", base),
        authorization_endpoint=os.getenv("GOOGLE_AUTHZ_ENDPOINT", f"{base}/o/oauth2/v2/auth"),
        token_endpoint=os.getenv("GOOGLE_TOKEN_ENDPOINT", f"{base}/o/oauth2/token"),
        userinfo_endpoint=os.getenv("GOOGLE_USERINFO_ENDPOINT", f"{base}/oauth2/v3/userinfo"),
        jwks_uri=os.getenv("GOOGLE_JWKS_URI", f"{base}/oauth2/v3/certs"),
        scopes=["openid", "email", "profile"],
        icon="google",
        color="red",
        description="Google Workspace OIDC",
    )


def _dingtalk() -> ProviderConfig:
    base = "https://api.dingtalk.com/v1.0"
    return ProviderConfig(
        slug="dingtalk",
        display_name="DingTalk (钉钉)",
        category=ProviderCategory.CN,
        protocol=SSOProtocol.OIDC,
        issuer=os.getenv("DINGTALK_ISSUER", "https://api.dingtalk.com"),
        authorization_endpoint=os.getenv(
            "DINGTALK_AUTHZ_ENDPOINT", f"{base}/oauth/authorize"
        ),
        token_endpoint=os.getenv("DINGTALK_TOKEN_ENDPOINT", f"{base}/oauth/userAccessToken"),
        userinfo_endpoint=os.getenv(
            "DINGTALK_USERINFO_ENDPOINT", f"{base}/contact/users/me"
        ),
        jwks_uri=os.getenv("DINGTALK_JWKS_URI"),
        scopes=["openid", "email", "profile"],
        icon="message-circle",
        color="blue",
        description="DingTalk enterprise OIDC",
    )


def _feishu() -> ProviderConfig:
    base = "https://open.feishu.cn/open-apis"
    return ProviderConfig(
        slug="feishu",
        display_name="Feishu (飞书)",
        category=ProviderCategory.CN,
        protocol=SSOProtocol.OIDC,
        issuer=os.getenv("FEISHU_ISSUER", "https://open.feishu.cn"),
        authorization_endpoint=os.getenv(
            "FEISHU_AUTHZ_ENDPOINT", f"{base}/authen/v2/index"
        ),
        token_endpoint=os.getenv(
            "FEISHU_TOKEN_ENDPOINT", f"{base}/authen/v2/access_token"
        ),
        userinfo_endpoint=os.getenv(
            "FEISHU_USERINFO_ENDPOINT", f"{base}/authen/v2/user_info"
        ),
        jwks_uri=os.getenv("FEISHU_JWKS_URI", f"{base}/jssdk2/open-api/jssdk/public_key"),
        scopes=["openid", "email", "profile", "contact:user.id:readonly"],
        icon="send",
        color="cyan",
        description="Feishu (Lark) OIDC",
    )


def _wecom() -> ProviderConfig:
    corp_id = os.getenv("WECOM_CORP_ID", "ww-example")
    return ProviderConfig(
        slug="wecom",
        display_name="WeCom (企业微信)",
        category=ProviderCategory.CN,
        protocol=SSOProtocol.OIDC,
        issuer=os.getenv("WECOM_ISSUER", f"https://login.work.weixin.qq.com/{corp_id}"),
        authorization_endpoint=os.getenv(
            "WECOM_AUTHZ_ENDPOINT",
            f"https://login.work.weixin.qq.com/wwlogin/sso/oauth2/authorize",
        ),
        token_endpoint=os.getenv(
            "WECOM_TOKEN_ENDPOINT", "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo"
        ),
        userinfo_endpoint=os.getenv(
            "WECOM_USERINFO_ENDPOINT", "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserdetail"
        ),
        jwks_uri=os.getenv("WECOM_JWKS_URI"),
        scopes=["openid", "email", "profile", "snsapi_privateinfo"],
        icon="users",
        color="green",
        description="WeCom (企业微信) OIDC",
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PROVIDER_REGISTRY: Dict[str, ProviderConfig] = {
    cfg.slug: cfg
    for cfg in (
        _okta(),
        _azure_ad(),
        _google(),
        _dingtalk(),
        _feishu(),
        _wecom(),
    )
}


def get_provider_config(slug: str) -> ProviderConfig:
    """Return the config for a provider, raising :class:`KeyError` if missing."""
    if slug not in PROVIDER_REGISTRY:
        raise KeyError(f"Unknown SSO provider: {slug!r}")
    return PROVIDER_REGISTRY[slug]


def list_enabled_providers() -> List[ProviderConfig]:
    """Return providers the deployment is willing to serve."""
    return [c for c in PROVIDER_REGISTRY.values() if c.enabled]


__all__ = [
    "ProviderConfig",
    "ProviderCategory",
    "SSOProtocol",
    "PROVIDER_REGISTRY",
    "get_provider_config",
    "list_enabled_providers",
]
