"""ATS Provider package — T1806.

公开入口:
    GreenhouseProvider — Harvest API (Basic Auth + On-Behalf-Of)
    LeverProvider      — Lever ATS API (Basic Auth)
    OAuth2 utilities   — 为后续 Bullhorn/Workable/iCIMS 准备
"""
from __future__ import annotations

from .base import ATSProvider
from .greenhouse import GreenhouseProvider
from .lever import LeverProvider
from .mock import MockATSProvider
from .oauth2 import (
    HttpxOAuth2Client,
    InMemoryOAuth2TokenStore,
    OAuth2Error,
    OAuth2Token,
    OAuth2TokenManager,
    OAuth2TokenStore,
)
from .registry import build, list_providers, register
from .types import Candidate, CandidateStatus, ExternalId, Job

__all__ = [
    "ATSProvider",
    "GreenhouseProvider",
    "LeverProvider",
    "MockATSProvider",
    "Candidate",
    "CandidateStatus",
    "ExternalId",
    "Job",
    "build",
    "list_providers",
    "register",
    "OAuth2Token",
    "OAuth2TokenManager",
    "OAuth2TokenStore",
    "InMemoryOAuth2TokenStore",
    "HttpxOAuth2Client",
    "OAuth2Error",
]