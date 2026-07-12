# Plugin Security Model

> v6.0 T2104 — the threat model and layered defences for plugins.

---

## 1. Threat model

The plugin SDK assumes a hostile plugin author. The threats we defend
against:

| Threat | Example |
|---|---|
| **Code execution escape** | A plugin reads a private key off disk and exfiltrates it. |
| **Network exfiltration** | A plugin opens a socket to an attacker-controlled host. |
| **Resource exhaustion** | A plugin spawns a fork bomb, allocates 32 GB of RAM, or holds the GIL forever. |
| **Privilege escalation** | A plugin declares `db:read` but writes to the DB anyway. |
| **Import-time RCE** | A plugin imports `ctypes` and calls `system()`. |
| **State corruption** | A plugin corrupts the host's module table, breaks the EventBus, or patches stdlib. |

Defence-in-depth applies because no single layer is sufficient.

---

## 2. Layered defences

### Layer 1 — manifest validation

The manifest is parsed and validated **before** any plugin code is
loaded. Bad manifests are rejected with `ManifestError`. The manifest
is the contract; if it lies, the host fails closed.

### Layer 2 — import-time guarding

`safe_import` blocks `os`, `subprocess`, `socket`, `ctypes`,
`importlib`, `pickle`, `multiprocessing`, and friends. The block list
is in `plugins.sdk.sandbox.DEFAULT_BLOCKED_MODULES`.

When `RestrictedPython` is installed, plugins are compiled with
restricted guards (no `__import__`, no `open`, no `getattr` on dunders,
no `compile` / `exec` / `eval`). Without RestrictedPython, the loader
falls back to a stdlib AST audit that catches the same patterns.

### Layer 3 — permission gate

Every privileged call goes through `ctx.require_permission(...)`. The
host's allow-list is enforced at install time. The plugin cannot
declare permissions it isn't allowed to use.

### Layer 4 — resource limits

`ResourceLimiter` puts soft caps on:

* **CPU time** (`RLIMIT_CPU`) — process killed at the cap.
* **Address space** (`RLIMIT_AS`) — process killed at the cap.
* **Open file descriptors** (`RLIMIT_NOFILE`).

The limits are scoped per `install` / `enable` / `run` invocation; the
previous limits are restored on exit.

### Layer 5 — network guard

`NetworkGuard` patches `socket.socket.connect` to refuse hosts outside
the configured allow-list. Patterns:

* Exact host match (`oapi.dingtalk.com`)
* Wildcard subdomain (`*.dingtalk.com`)

When the allow-list is empty, **all** outbound connections are blocked
(fail-closed default).

### Layer 6 — filesystem guard

`FilesystemGuard` patches the builtin `open` to refuse writes outside
the configured sandbox directory. Reads are unrestricted.

### Layer 7 — exception isolation

Every plugin hook (`install`, `enable`, `disable`, `uninstall`,
`run`) runs inside a `try / except`. Exceptions are caught and
surfaced as `PluginRunResult(error_type="crash", error=str(exc))`. The
host never crashes because a plugin did.

### Layer 8 — wall-clock timeout

`install` and `enable` (and `run`, when `run_timeout_s` is set) are
executed under a `concurrent.futures.ThreadPoolExecutor` with a
`future.result(timeout=...)`. A timed-out call is recorded as
`error_type="timeout"`.

### Layer 9 — out-of-process isolation (production)

In production, plugins run inside a separate process / container.
The host only talks to plugins over a tightly-scoped IPC. This is
**required** for untrusted plugins — the in-process guards are
defence-in-depth.

---

## 3. Recommended deployment topology

```
                                 +-----------------+
                                 |   host process  |
                                 | (FastAPI + DB)  |
                                 +--------+--------+
                                          |
                                  IPC (HTTP/grpc)
                                          |
+-------------------+   +-----------------+   +-----------------+
|  plugin worker 1  |   |  plugin worker 2 |   |  plugin worker N |
|  (container)      |   |  (container)     |   |  (container)     |
+-------------------+   +-----------------+   +-----------------+
```

* One plugin per container, scoped to its sandbox directory.
* Outbound network via egress proxy with allow-list.
* Container CPU / memory limits applied by the orchestrator.
* Host monitors plugin health via heartbeats.

---

## 4. Audit + observability

Every plugin lifecycle event is recorded:

* `plugin_runs` — per-invocation record (status, duration, error).
* `plugin_audit` — append-only state-transition log (install, uninstall,
  enable, disable, run, error).
* `metrics:emit` — plugins can emit their own metrics; the host ships
  them to the dashboard.

---

## 5. Operator checklist

Before shipping a plugin:

* [ ] Manifest declares only the permissions the plugin actually needs.
* [ ] Plugin source has been read by a human reviewer.
* [ ] Sandbox config sets explicit `allow_network_hosts`.
* [ ] Resource limits are tuned for the plugin's workload.
* [ ] Out-of-process isolation is enabled in production.
* [ ] `plugin_runs` alerting is configured (flaky / unsafe detection).

---

## 6. What the SDK does NOT defend against

* **Side-channel attacks** (Spectre / Meltdown) — these require
  hardware mitigations.
* **A malicious host** — the SDK assumes the host is honest.
* **A network attacker who controls an allow-listed host** — the host
  operator is responsible for the allow-list.

---

## 7. See also

* [`PLUGIN_SDK.md`](./PLUGIN_SDK.md) — developer guide
* [`EXTENSIBILITY_SPEC.md`](./EXTENSIBILITY_SPEC.md) — v6.0 architecture
* `talent-tool-mvp/backend/plugins/sdk/sandbox.py` — implementation
* `talent-tool-mvp/backend/plugins/sdk/loader.py` — sandboxed loader