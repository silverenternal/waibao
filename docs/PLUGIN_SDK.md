# Plugin SDK Developer Guide

> v6.0 T2104 — the complete developer guide for building, packaging, and
> shipping third-party plugins against the waibao platform.

---

## Table of Contents

1. [What is a plugin?](#what-is-a-plugin)
2. [Quick start](#quick-start)
3. [The `plugin.yaml` manifest](#the-pluginyaml-manifest)
4. [The Plugin class](#the-plugin-class)
5. [Permissions](#permissions)
6. [Capability surfaces](#capability-surfaces)
7. [Lifecycle hooks](#lifecycle-hooks)
8. [The plugin context](#the-plugin-context)
9. [Distribution](#distribution)
10. [Reference plugins](#reference-plugins)
11. [Debugging & FAQ](#debugging--faq)

---

## What is a plugin?

A plugin is a self-contained bundle that contributes one (or more) of:

* **Agent** — a callable reasoning module (e.g. resume scorer).
* **Service** — a handler for inbound events (e.g. interview bot).
* **Provider** — an outbound bridge (e.g. DingTalk approval).
* **Widget** — a frontend descriptor (rendered by Mind/Mothership).

Plugins run *in-process* by default, but the host enforces layered
isolation so a misbehaving plugin cannot take down the platform. See
[`PLUGIN_SECURITY.md`](./PLUGIN_SECURITY.md) for the full threat model.

---

## Quick start

### 1. Scaffold the plugin directory

```
plugins/my-plugin/
  plugin.yaml
  main.py
  README.md
```

### 2. Write the manifest

```yaml
name: my-plugin
version: 0.1.0
author: you@example.com
description: One-line summary
entry_point: main:MyPlugin
type: service          # agent | service | provider | widget
permissions:
  - events:emit
config_schema:
  greeting:
    type: string
    default: hello
```

### 3. Implement the plugin

```python
# main.py
from plugins.sdk.base import Plugin, PluginContext, PluginState


class MyService:
    def handle(self, payload):
        return {"reply": "world"}


class MyPlugin(Plugin):
    name = "my-plugin"
    version = "0.1.0"
    author = "you@example.com"
    description = "Demo"
    permissions = ["events:emit"]
    config_schema = {"greeting": "hello"}

    def enable(self, ctx):
        ctx.event_bus_emit("plugin.enabled", {"plugin": self.name})

    def get_service(self):
        return MyService()
```

### 4. Install + enable via admin API

```bash
curl -X POST http://localhost:8000/api/admin/plugins/install \
  -H 'content-type: application/json' \
  -d '{"directory": "/abs/path/to/plugins/my-plugin", "actor": "alice"}'

curl -X POST http://localhost:8000/api/admin/plugins/my-plugin/enable \
  -H 'content-type: application/json' -d '{"actor":"alice"}'
```

### 5. Invoke the plugin

```bash
curl -X POST http://localhost:8000/api/admin/plugins/my-plugin/run \
  -H 'content-type: application/json' \
  -d '{"payload": {"text": "hi"}}'
```

---

## The `plugin.yaml` manifest

The host reads `plugin.yaml` first; everything else is gated on a valid
manifest. Required keys:

| Key | Description |
|---|---|
| `name` | Lowercase, kebab/snake, unique. |
| `version` | Loose semver (`1.2.0`, `2.0.0-rc.1`). |
| `author` | Free-form. |
| `description` | One-line summary. |
| `entry_point` | `module.path:ClassName`. |
| `type` | `agent` (default), `service`, `provider`, or `widget`. |
| `permissions` | List of whitelisted tokens (see [Permissions](#permissions)). |
| `config_schema` | (Optional) defaults for runtime configuration. |
| `dependencies` | (Optional) informational — the host does not auto-install. |

Validation lives in `plugins.sdk.manifest.parse_manifest` — bad inputs
raise `ManifestError` and the runner records it as
`error_type="manifest"`.

---

## The Plugin class

```python
from plugins.sdk.base import Plugin, PluginContext


class MyPlugin(Plugin):
    name: str
    version: str
    author: str
    description: str
    permissions: list[str]
    config_schema: dict
    state: PluginState   # installed | enabled | disabled | error
```

At minimum, override **one** of the four capability getters:

* `get_agent() -> Any | None`
* `get_service() -> Any | None`
* `get_provider() -> Any | None`
* `get_widget() -> Any | None`

The returned object should expose a callable:

| Surface | Method |
|---|---|
| agent | `agent.run(payload) -> Any` |
| service | `service.handle(payload) -> Any` |
| provider | `provider.provide(payload) -> Any` |
| widget | descriptor dict |

---

## Permissions

Every privileged action must be declared in the manifest and gated at
runtime through `ctx.require_permission(...)`. The full allow-list:

| Token | Meaning |
|---|---|
| `db:read` | Read from the host database |
| `db:write` | Write to the host database |
| `events:emit` | Publish on the EventBus |
| `events:subscribe` | Subscribe to EventBus events |
| `http:call` | Outbound HTTP |
| `http:listen` | Bind an HTTP listener (rarely granted) |
| `files:read` | Read files under the sandbox |
| `files:write` | Write files under the sandbox |
| `llm:call` | Call the host LLM gateway |
| `metrics:emit` | Emit custom metrics |
| `admin` | Admin operations (rarely granted) |

The host's allow-list is enforced at install time by
`PluginRunner._check_permissions`. Plugins declaring unknown tokens are
rejected with `error_type="permission"`.

---

## Capability surfaces

### Agent

```python
class MyAgent:
    def run(self, payload: dict) -> dict:
        ...
```

### Service

```python
class MyService:
    def handle(self, payload: dict) -> dict:
        ...
```

### Provider

```python
class MyProvider:
    def provide(self, payload: dict) -> dict:
        ...
```

### Widget

```python
def get_widget(self):
    return {
        "name": "my-widget",
        "entry": "./widget.js",
        "props": {"theme": "dark"},
    }
```

---

## Lifecycle hooks

```python
class MyPlugin(Plugin):
    def install(self, ctx): ...     # provisioning
    def enable(self, ctx): ...      # hot start
    def disable(self, ctx): ...     # hot stop
    def uninstall(self, ctx): ...   # tear down
```

Every hook is wrapped in:

* a wall-clock timeout (`install_timeout_s` / `enable_timeout_s`)
* exception isolation — exceptions are caught and surfaced as
  `PluginRunResult(error_type="crash")`.
* resource limits (CPU / memory / file descriptors).
* network and filesystem guards (configurable).

---

## The plugin context

Every lifecycle hook and every capability invocation receives a
`PluginContext`:

```python
@dataclass
class PluginContext:
    plugin_name: str
    db: Any              # session / repository handle (None by default)
    event_bus: EventBus
    logger: logging.Logger
    config: dict         # resolved config_schema values
    permissions: list[str]

    def require_permission(self, perm: str) -> None: ...
    def event_bus_emit(self, name, payload=None, correlation_id=None) -> None: ...
```

`require_permission` raises `PermissionError` if the token isn't in
`ctx.permissions` — never silently allow.

---

## Distribution

### Local install

The simplest path: point the admin API at a directory on disk.

```bash
curl -X POST .../api/admin/plugins/install \
  -d '{"directory": "/srv/plugins/my-plugin"}'
```

### Tarball install (planned)

Tarballs land in `/srv/plugins/_staging/<name>-<version>.tar.gz`; the
admin endpoint unpacks + validates. Out of scope for the v6.0 milestone.

### Marketplace (planned)

Out of scope — left as a v6.1+ task.

---

## Reference plugins

Three reference plugins ship under `talent-tool-mvp/plugins/`:

* `waibao-plugin-resume-scorer/` — weighted resume scoring agent
* `waibao-plugin-interview-bot/` — conversational interview service
* `waibao-plugin-dingtalk-approval/` — DingTalk approval provider

Each ships with `plugin.yaml`, `main.py`, and `README.md`.

---

## Debugging & FAQ

### My install fails with `error_type="manifest"`

Run `parse_manifest(yaml.safe_load(open('plugin.yaml').read()))` in a
Python REPL — the error message will name the failing key.

### My install fails with `error_type="sandbox"`

Your plugin tried to `import os` / `subprocess` / etc. Remove the import
and use the plugin context instead. If you genuinely need that
capability, ask the host operator to add it to the allow-list.

### My plugin times out

The default `install_timeout_s` is 30s and `enable_timeout_s` is 10s.
If your plugin does heavy startup work, ask the host operator to bump
the limit (and add the runtime to a sidecar container).

### Where do run results go?

The host logs `plugin_runs` rows (Supabase / in-memory). The admin API
exposes them at `GET /api/admin/plugins/{name}/runs` and
`GET /api/admin/plugins/runs`.

---

_See also: [`PLUGIN_SECURITY.md`](./PLUGIN_SECURITY.md),
[`EXTENSIBILITY_SPEC.md`](./EXTENSIBILITY_SPEC.md)._