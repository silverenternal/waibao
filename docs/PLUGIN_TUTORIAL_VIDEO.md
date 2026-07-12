# Build your first waibao plugin — Video Tutorial Script

> v6.0 T2104 — companion video script for [`PLUGIN_SDK.md`](./PLUGIN_SDK.md).
> Target runtime: ~10 minutes. Pacing assumes the viewer has Python
> fluency but no prior waibao exposure.

---

## Cold open (0:00–0:30)

> _"Plugins let you ship a new agent, service, or provider without
> forking waibao. In ten minutes, we'll build one end-to-end — a
> tiny resume scorer that lives behind a sandbox, talks to the host's
> event bus, and exposes an admin API."_

B-roll: terminal typing, the admin plugin page, the example plugin
directories.

---

## Act 1 — Why plugins (0:30–2:00)

Three use cases shown on screen:

1. **Acme Talent** ships an OKR advisor agent that uses its own prompt
   library.
2. **BluePine** integrates DingTalk approvals without forking the
   core.
3. **Pilot partner** runs a custom scoring rubric for executive search.

> _"All three are 'plugins' in our world. They share one shape: a
> `plugin.yaml` manifest, a Python `Plugin` subclass, and a fixed
> set of permissions the host enforces. That's it."_

---

## Act 2 — Scaffold (2:00–4:00)

Live coding. The narrator types:

```bash
mkdir -p plugins/waibao-plugin-hello
cd plugins/waibao-plugin-hello
touch plugin.yaml main.py README.md
```

Then opens `plugin.yaml`:

```yaml
name: hello
version: 0.1.0
author: you@example.com
description: Greets whoever runs me
entry_point: main:HelloPlugin
type: service
permissions:
  - events:emit
config_schema:
  greeting:
    type: string
    default: hello
```

> _"Notice the `entry_point` — `module.path:ClassName`. That tells the
> loader exactly where to find your plugin class. The host refuses
> anything else."_

---

## Act 3 — Implement (4:00–6:30)

```python
# main.py
from plugins.sdk.base import Plugin, PluginContext, PluginState


class HelloService:
    def handle(self, payload):
        return {"reply": f"hi, {payload.get('name', 'world')}!"}


class HelloPlugin(Plugin):
    name = "hello"
    version = "0.1.0"
    author = "you@example.com"
    description = "Greets whoever runs me"
    permissions = ["events:emit"]
    config_schema = {"greeting": "hello"}

    def install(self, ctx):
        ctx.logger.info("hello installing")

    def enable(self, ctx):
        ctx.require_permission("events:emit")
        ctx.event_bus_emit("plugin.enabled", {"plugin": self.name})
        self.state = PluginState.ENABLED

    def get_service(self):
        return HelloService()
```

Walk through the lifecycle hooks — `install`, `enable`, `disable`.
Show that `require_permission` is what enforces the manifest's
permission list.

---

## Act 4 — Install + run (6:30–8:30)

```bash
# Install
curl -X POST http://localhost:8000/api/admin/plugins/install \
  -H 'content-type: application/json' \
  -d '{"directory": "/abs/path/to/plugins/waibao-plugin-hello", "actor": "alice"}'

# Enable
curl -X POST http://localhost:8000/api/admin/plugins/hello/enable \
  -H 'content-type: application/json' -d '{"actor":"alice"}'

# Invoke
curl -X POST http://localhost:8000/api/admin/plugins/hello/run \
  -H 'content-type: application/json' \
  -d '{"payload": {"name": "team"}}'
```

The response:

```json
{ "success": true, "output": {"reply": "hi, team!"}, "duration_ms": 1.4 }
```

> _"That's the whole loop. Install, enable, run. The host handled
> the sandbox, the import guards, the permission gate — your plugin
> never touched anything it shouldn't."_

---

## Act 5 — Sandbox tour (8:30–9:30)

Switch to the terminal and show:

```bash
# What happens if the plugin tries os.system?
cat > /tmp/bad.py <<'EOF'
import os
class BadPlugin(Plugin):
    name = "bad"
    permissions = []
    def install(self, ctx): os.system("echo pwned > /tmp/x")
EOF

curl -X POST .../api/admin/plugins/install \
  -d '{"directory": "/tmp/bad"}'
```

Response: `{"error_type": "sandbox", "error": "plugin imports blocked module 'os'"}`.

> _"The host caught the import at compile time. No file was written,
> no process was spawned. The plugin author learns fast."_

---

## Wrap (9:30–10:00)

> _"That's it. Three files, four lines of config, and you're in
> production. Read [`PLUGIN_SDK.md`](./PLUGIN_SDK.md) for the full
> reference and [`PLUGIN_SECURITY.md`](./PLUGIN_SECURITY.md) for the
> threat model. Ship something."_

End card: link to the docs, link to the reference plugins
(`waibao-plugin-resume-scorer`, `waibao-plugin-interview-bot`,
`waibao-plugin-dingtalk-approval`).

---

## Cut list / b-roll

* 0:00 — terminal typing
* 2:30 — admin plugin page (empty state)
* 4:30 — code editor (syntax highlighting plugin)
* 6:45 — terminal response (success)
* 8:45 — terminal response (sandbox rejection)
* 9:30 — end card with docs links