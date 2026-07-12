"""Example plugin — DingTalk approval integration.

Demonstrates the provider surface. The plugin pushes an offer / hire
approval record into DingTalk's approval workflow API and returns the
resulting instance id. The actual HTTP call is implemented behind the
``http:call`` permission — production deployments inject a sandboxed
HTTP client at install time.

This reference implementation stubs the HTTP call and returns a
deterministic shape so it works end-to-end without external dependencies.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Dict

from plugins.sdk.base import Plugin, PluginContext, PluginState


class _DingTalkProvider:
    def __init__(self, plugin: "DingTalkApprovalPlugin", ctx: PluginContext) -> None:
        self.plugin = plugin
        self.ctx = ctx

    def provide(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        approval_type = payload.get("approval_type", "offer")
        subject = payload.get("subject", "")
        applicant = payload.get("applicant", "")
        form_components = payload.get("form_components") or []

        # Gate the outbound HTTP call.
        self.ctx.require_permission("http:call")

        # Stub the upstream call. A real implementation would:
        #   1. POST /oauth/getToken          (gated by app_key/app_secret)
        #   2. POST /topapi/processinstance/create
        # Here we just emit an event and return a deterministic id.
        process_id = _stub_create_process(approval_type, subject, applicant,
                                          form_components)
        self.ctx.require_permission("events:emit")
        self.ctx.event_bus_emit("dingtalk.approval.created", {
            "process_id": process_id,
            "approval_type": approval_type,
            "applicant": applicant,
        })
        return {
            "process_id": process_id,
            "approval_type": approval_type,
            "subject": subject,
            "url": f"https://example.dingtalk.com/approval/{process_id}",
        }


def _stub_create_process(approval_type: str, subject: str,
                         applicant: str, form_components: list) -> str:
    seed = f"{approval_type}|{subject}|{applicant}|{time.time()}"
    return "PROC-" + hashlib.sha1(seed.encode()).hexdigest()[:16]


class DingTalkApprovalPlugin(Plugin):
    name = "dingtalk-approval"
    version = "0.9.0"
    author = "waibao-labs"
    description = "Bridge offer / hire approvals into DingTalk"
    permissions = ["http:call", "events:emit", "metrics:emit"]
    config_schema = {
        "app_key": "",
        "app_secret": "",
        "approval_code": "",
        "default_approver_userid": "",
    }
    state = PluginState.INSTALLED

    def install(self, ctx: PluginContext) -> None:
        ctx.logger.info("dingtalk-approval installing")
        self.state = PluginState.INSTALLED

    def enable(self, ctx: PluginContext) -> None:
        ctx.require_permission("events:emit")
        ctx.event_bus_emit("plugin.enabled", {"plugin": self.name})
        self.state = PluginState.ENABLED

    def disable(self, ctx: PluginContext) -> None:
        self.state = PluginState.DISABLED

    def get_provider(self) -> Any:
        return _ProviderAdapter(self)

    def get_agent(self): return None
    def get_service(self): return None
    def get_widget(self): return None


class _ProviderAdapter:
    def __init__(self, plugin: DingTalkApprovalPlugin) -> None:
        self.plugin = plugin

    def provide(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ctx = PluginContext(
            plugin_name=self.plugin.name,
            db=None,
            event_bus=None,
            logger=_NullLogger(),
            config=self.plugin.config_schema,
            permissions=self.plugin.permissions,
        )
        return _DingTalkProvider(self.plugin, ctx).provide(payload)


class _NullLogger:
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass
    def exception(self, *args, **kwargs): pass
    def debug(self, *args, **kwargs): pass