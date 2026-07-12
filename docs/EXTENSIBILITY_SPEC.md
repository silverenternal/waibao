# waibao v6.0 Extensibility Spec

> Three load-bearing abstractions that let downstream contributors add
> behaviour without forking the platform:
>
> 1. **Event Bus** — synchronous / asynchronous pub/sub for decoupling agents
> 2. **Plugin SDK** — sandboxed, manifest-driven third-party extensions
> 3. **Agent Composition** — declarative DAG workflows that orchestrate agents, humans, and side-effects

All three follow the same shape: a small ABC + a reference in-memory implementation
+ a thin convenience surface (decorators, registries). The host boot code
swaps in production implementations without touching call sites.

---

## Table of Contents

1. [Event Bus](#1-event-bus)
   * [`backend/eventbus/base.py`](../talent-tool-mvp/backend/eventbus/base.py) — Event / EventBus / InMemory / Redis
   * [`backend/eventbus/decorators.py`](../talent-tool-mvp/backend/eventbus/decorators.py) — `@on_event`, `emit`, `fire`, `listen`, `await_event`
   * [`backend/eventbus/registry.py`](../talent-tool-mvp/backend/eventbus/registry.py) — process-wide singleton
   * [Integration examples](#event-bus--integration-examples)
2. [Plugin SDK](#2-plugin-sdk)
   * [`backend/plugins/sdk/base.py`](../talent-tool-mvp/backend/plugins/sdk/base.py) — Plugin ABC, PluginType, PluginContext, PluginRegistry
   * [`backend/plugins/sdk/manifest.py`](../talent-tool-mvp/backend/plugins/sdk/manifest.py) — `plugin.yaml` parsing & validation
   * [`backend/plugins/sdk/runner.py`](../talent-tool-mvp/backend/plugins/sdk/runner.py) — sandboxed install / enable / disable / uninstall
   * [Integration examples](#plugin-sdk--integration-examples)
3. [Agent Composition](#3-agent-composition)
   * [`backend/services/platform/nodes.py`](../talent-tool-mvp/backend/services/platform/nodes.py) — Trigger / Agent / Condition / Action / Delay / Human
   * [`backend/services/platform/workflow_engine.py`](../talent-tool-mvp/backend/services/platform/workflow_engine.py) — DAG execution + persistence + resume
   * [Integration examples](#agent-composition--integration-examples)
4. [Test Inventory](#4-test-inventory)
5. [Migration Checklist for downstream agents](#5-migration-checklist-for-downstream-agents)

---

## 1. Event Bus

### Goals

* Decouple publishers from subscribers across services, agents, plugins, and workflows.
* Work in dev/test with zero infrastructure (in-memory) and in prod with Redis pub/sub.
* Allow subscribers to be either sync or async without any caller-side branching.

### Public surface (from `eventbus/__init__.py`)

```python
from eventbus import (
    Event, EventBus, InMemoryEventBus, RedisEventBus, Subscription,
    get_event_bus, set_event_bus, reset_event_bus,
    on_event, emit, fire, listen, await_event,
)
```

### Key types

```python
@dataclass
class Event:
    name: str
    payload: Dict[str, Any]
    source: str = "unknown"
    timestamp: float
    event_id: str            # uuid4
    correlation_id: Optional[str]
    metadata: Dict[str, Any]

@dataclass
class Subscription:
    id: str
    event_name: str
    handler: Callable[[Event], Any]
    created_at: float
    is_async: bool

class EventBus(ABC):
    def publish(self, event: Event) -> None: ...
    def subscribe(self, event_name: str, handler: Callable[[Event], Any]) -> Subscription: ...
    def unsubscribe(self, subscription: Subscription) -> None: ...
    def publish_async(self, event: Event) -> Awaitable[None]: ...
    def emit(self, name, payload=None, *, source="app", correlation_id=None) -> Event: ...
```

### Implementations

* **`InMemoryEventBus`** — default; thread-safe (`RLock`); tracks handler errors in `.errors`.
* **`RedisEventBus`** — wraps Redis pub/sub for cross-process fan-out; falls back to a local `InMemoryEventBus` for same-process subscribers so `publish` is never blocking on the network for in-process listeners.

### Decorators & helpers

```python
@on_event("clarifier.completed")
async def on_done(evt: Event) -> None:
    ...

emit("user.created", {"id": 42})
fire("order.paid", order_id="o-1", amount=99.0)
sub = listen("user.created", handler)
evt = await await_event("user.created", timeout=5.0)
```

The decorator auto-detects sync vs async handlers via `inspect.iscoroutinefunction`.

### Production swap

Set the env var before process start:

```bash
export WAIBAO_EVENTBUS=redis
export WAIBAO_REDIS_URL=redis://redis.internal:6379/0
```

`get_event_bus()` will then return a `RedisEventBus` instance. Otherwise it returns `InMemoryEventBus`. Tests should call `set_event_bus(InMemoryEventBus())` for deterministic isolation.

### Event Bus — integration examples

#### A. Subscribing from a service module

```python
# backend/services/matching/notifier.py
from eventbus import on_event, emit

@on_event("candidate.matched")
def notify_partner(evt):
    payload = evt.payload
    send_email(payload["partner_email"], subject="New match", body=...)

# elsewhere:
emit("candidate.matched", {"candidate_id": 1, "partner_email": "x@y"})
```

#### B. Async handler in an agent

```python
# backend/agents/jobseeker/clarifier.py
from eventbus import on_event

@on_event("clarifier.completed")
async def resume_application(evt):
    app_id = evt.payload["application_id"]
    await resume(app_id)
```

#### C. Awaiting an event from a coroutine

```python
# backend/api/webhooks.py
async def handle_interview_completed(req):
    run_id = req.json()["run_id"]
    await resume_workflow(run_id)
    evt = await await_event("interview.scored", timeout=30.0)
    return {"score": evt.payload["score"]}
```

---

## 2. Plugin SDK

### Goals

* Let third parties ship an agent / service / provider / widget bundle
  without touching core code.
* Declare permissions explicitly; the host gates every privileged call.
* Isolate crashes so a misbehaving plugin never takes down the platform.
* Survive slow / hanging installs via wall-clock timeouts.

### Public surface (from `plugins/__init__.py`)

```python
from plugins import (
    Plugin, PluginContext, PluginRegistry, PluginState, PluginType,
    get_plugin_registry,
    ManifestError, PluginManifest,
    load_entry_point, load_manifest_file, parse_manifest,
    PluginLoadError, PluginPermissionError, PluginRunResult, PluginRunner,
)
```

### Manifest contract (`plugin.yaml`)

```yaml
name: okr-advisor
version: 1.0.0
author: Acme Talent
description: OKR review & follow-up coach agent
entry_point: okr_advisor.plugin:OkrAdvisorPlugin
type: agent
permissions:
  - db:read
  - events:emit
  - llm:call
config_schema:
  default_model:
    type: string
    default: gpt-4o-mini
dependencies:
  - name: faiss
    version: ">=1.7"
```

The parser enforces:

* `name` is a non-empty string.
* `version` matches a loose semver regex.
* `entry_point` follows `module.path:Class`.
* `permissions` is a list of whitelisted tokens (`db:read`, `db:write`, `events:emit`, `events:subscribe`, `http:call`, `http:listen`, `files:read`, `files:write`, `llm:call`, `metrics:emit`, `admin`).

Anything else raises `ManifestError` and the runner records it as `error_type="manifest"`.

### Plugin ABC

```python
class Plugin(ABC):
    name: str
    version: str
    author: str
    description: str
    permissions: List[str]
    config_schema: Dict[str, Any]
    state: PluginState  # installed | enabled | disabled | error

    def install(self, ctx: PluginContext) -> None: ...
    def uninstall(self, ctx: PluginContext) -> None: ...
    def enable(self, ctx: PluginContext) -> None: ...
    def disable(self, ctx: PluginContext) -> None: ...

    def get_agent(self) -> Optional[Any]: ...
    def get_service(self) -> Optional[Any]: ...
    def get_provider(self) -> Optional[Any]: ...
    def get_widget(self) -> Optional[Any]: ...
```

A plugin may contribute to multiple surfaces (e.g. an agent + a widget), but at
minimum one `get_*` must return non-None.

### PluginContext

What every plugin receives at runtime:

```python
@dataclass
class PluginContext:
    plugin_name: str
    db: Any                # session / repository handle (None by default)
    event_bus: EventBus    # injected by host
    logger: logging.Logger
    config: Dict[str, Any] # resolved config_schema values
    permissions: List[str]

    def require_permission(self, perm: str) -> None: ...
    def event_bus_emit(self, name, payload=None, correlation_id=None) -> None: ...
```

### PluginRunner

```python
runner = PluginRunner(
    allowed_permissions=["db:read", "events:emit", "llm:call"],
    install_timeout_s=30.0,
    enable_timeout_s=10.0,
    use_restricted_python=False,
)

result = runner.install_from_manifest_path("plugins/okr_advisor/plugin.yaml")
if not result.success:
    log.error("plugin install failed", extra=result.to_dict())

runner.enable(plugin)
runner.disable(plugin)
runner.uninstall(plugin)
```

Isolation guarantees:

* Every install/enable call runs in a worker thread with a wall-clock timeout.
* Exceptions inside `install` / `enable` are caught and surfaced as
  `PluginRunResult(error_type="crash", error=str(exc))` — never propagated.
* Permissions are validated against the host's allow-list at install time;
  any unknown token fails with `error_type="permission"`.

> Production deployments should additionally run the runner in a separate
> process / container — in-process isolation is necessary but not sufficient.

### Plugin SDK — integration examples

#### A. Writing a plugin

```python
# plugins/okr_advisor/plugin.py
from plugins import Plugin, PluginContext

class OkrAdvisorPlugin(Plugin):
    name = "okr-advisor"
    version = "1.0.0"
    author = "Acme Talent"
    description = "OKR review coach"
    permissions = ["db:read", "events:emit", "llm:call"]
    config_schema = {"default_model": {"type": "string", "default": "gpt-4o-mini"}}

    def install(self, ctx: PluginContext) -> None:
        ctx.logger.info("installing okr-advisor")

    def enable(self, ctx: PluginContext) -> None:
        ctx.event_bus_emit("plugin.enabled", {"plugin": self.name})

    def get_agent(self):
        from .agent import OkrAdvisorAgent
        return OkrAdvisorAgent()

    def get_service(self): return None
    def get_provider(self): return None
    def get_widget(self): return None
```

#### B. Loading it at boot

```python
# backend/bootstrap/plugins.py
from plugins import PluginRunner

def load_all(manifest_paths):
    runner = PluginRunner(allowed_permissions=ALLOWED)
    results = [runner.install_from_manifest_path(p) for p in manifest_paths]
    failures = [r for r in results if not r.success]
    if failures:
        log.error("plugin install failures", extra={"items": [r.to_dict() for r in failures]})
    return results
```

#### C. Using `require_permission`

```python
ctx.require_permission("db:write")
session.execute(...)
```

---

## 3. Agent Composition

### Goals

* Let non-engineers declare business flows that mix agents, branches,
  human approvals, delays, and side-effects.
* Persist run state so an interrupted workflow resumes cleanly after a
  deploy or crash.
* Keep the engine small: nodes do work, edges route, the engine drives.

### Public surface (from `services/platform/__init__.py`)

```python
from services.platform import (
    Edge, Node, WorkflowDefinition, WorkflowEngine,
    InMemoryWorkflowStore, WorkflowResult, RunStatus,
    ActionNode, AgentNode, ConditionNode, DelayNode, HumanNode,
    TriggerNode, WorkflowNode, NodeContext,
    get_node, list_node_types,
)
```

### Built-in node types

| Type        | Purpose                                                   | Returns                       |
|-------------|-----------------------------------------------------------|-------------------------------|
| `trigger`   | Acts as the entry point of an event-driven workflow       | `{triggered, payload}`        |
| `agent`     | Invokes an Agent from the registry with input/output maps | Agent output dict             |
| `condition` | Branches via expression or LLM-evaluated prompt           | `{branch: "true"\|"false"\|…}` |
| `action`    | Side-effects (email / ticket / db_write / event emit)     | `{sent, ticket_id, …}`        |
| `delay`     | `await asyncio.sleep(seconds)`                            | `{delayed}`                   |
| `human`     | Pauses the workflow until a human decides                 | `{paused: True, reason}`      |

### WorkflowDefinition

```python
@dataclass
class WorkflowDefinition:
    name: str
    version: str = "1.0"
    nodes: List[Node]
    edges: List[Edge]
    variables: Dict[str, Any]
    start_node: Optional[str]
    description: str = ""

@dataclass
class Node:
    id: str
    type: str            # one of list_node_types()
    config: Dict[str, Any]
    next_nodes: List[str]  # informational; routing is via edges

@dataclass
class Edge:
    from_node: str
    to_node: str
    condition: Optional[str]  # matches the ConditionNode branch value
```

### Engine

```python
engine = WorkflowEngine(InMemoryWorkflowStore())
engine.register(workflow_def)
result = await engine.execute(workflow_def, input={"user_id": 42})
# result.status ∈ {pending, running, paused, completed, failed, cancelled}
# result.nodes_executed, result.variables, result.error, result.paused_at_node

# Resume a paused workflow:
engine.remember(workflow_def)            # so resume() can find the definition
await engine.resume(run_id, decision="approve")

# Cancel:
await engine.cancel(run_id)
```

### Persistence

`InMemoryWorkflowStore` ships as the reference implementation. Production
should swap in a DB-backed `WorkflowStore` (Supabase / Postgres) implementing
the same `save()` / `load()` / `list_runs()` async API.

### Agent Composition — integration examples

#### A. A 3-node "score → notify" flow

```python
from services.platform import (
    Edge, Node, WorkflowDefinition, WorkflowEngine,
    InMemoryWorkflowStore,
)

score_flow = WorkflowDefinition(
    name="score_and_notify",
    start_node="score",
    nodes=[
        Node(id="score", type="agent",
             config={"agent": "resume_scorer",
                      "input": {"resume": "$resume"},
                      "output": {"score": "match_score"}}),
        Node(id="branch", type="condition",
             config={"expression": "match_score >= 0.7"}),
        Node(id="notify", type="action",
             config={"kind": "email",
                      "params": {"to": "$candidate_email",
                                  "subject": "Great match!"}}),
    ],
    edges=[
        Edge(from_node="score", to_node="branch"),
        Edge(from_node="branch", to_node="notify", condition="true"),
    ],
)

engine = WorkflowEngine(InMemoryWorkflowStore())
result = asyncio.run(engine.execute(
    score_flow,
    input={"resume": "...", "candidate_email": "u@example.com"},
))
```

#### B. Human approval mid-flow

```python
approval_flow = WorkflowDefinition(
    name="offer_with_approval",
    start_node="draft",
    nodes=[
        Node(id="draft", type="agent", config={"agent": "offer_drafter"}),
        Node(id="hr_review", type="human", config={"reason": "HR approval"}),
        Node(id="send", type="action", config={"kind": "email", "params": {...}}),
    ],
    edges=[Edge("draft", "hr_review"), Edge("hr_review", "send")],
)

engine.remember(approval_flow)
res = asyncio.run(engine.execute(approval_flow, input={}))
assert res.status == RunStatus.PAUSED
# After the HR click:
res = asyncio.run(engine.resume(res.run_id, decision="approved"))
```

#### C. Triggered by an EventBus event

```python
from eventbus import on_event
from services.platform import WorkflowEngine, WorkflowDefinition

@on_event("candidate.applied")
async def start_screening(evt):
    wf = screening_workflow_for(evt.payload["job_id"])
    await engine.execute(wf, input=evt.payload)
```

---

## 4. Test inventory

All tests run via `cd backend && python -m pytest -v`.

| Module | File | Tests |
|---|---|---|
| EventBus | `eventbus/tests/test_eventbus.py` | 7 |
| Plugin SDK | `plugins/tests/test_plugins.py` | 7 |
| Workflow Engine | `services/platform/tests/test_workflow_engine.py` | 5 |
| **Total** | | **19** |

Run them with:

```bash
cd backend && python -m pytest eventbus/tests/ plugins/tests/ services/platform/tests/test_workflow_engine.py -v
```

---

## 5. Migration Checklist for downstream agents

Every new feature in v6.0 should answer the following:

1. **Event flow.** Does the feature emit any of: `clarifier.completed`, `agent.finished`, `workflow.paused`, `plugin.enabled`, `audit.recorded`? Subscribe via `@on_event`; publish via `emit()`.
2. **Extension points.** Is anything callable by a third-party plugin? If yes, surface it through the plugin SDK (declare a permission, add a host-side API).
3. **Composability.** Is the feature expressible as a DAG node? If yes, add it to `services/platform/nodes.py` and update `list_node_types()` so workflow authors can use it.
4. **Permissions.** Any new side-effect (DB write / external HTTP / event emission / LLM call) needs a token in the manifest allow-list.
5. **Resumability.** Long-running work should expose a `run_id` and accept `resume()`. The engine contract is the easiest way to get this for free.
6. **Tests.** Add at least: one happy-path, one permission-denied, one crash isolation, one resume case.
7. **Telemetry.** Emit `metrics:emit` events so v6.0 dashboards pick them up automatically.

If a feature cannot meet (1)–(3) without bypassing the abstraction, the
abstraction is wrong — file an issue before shipping.

---

_Generated for waibao v6.0. Last revised 2026-07-12._