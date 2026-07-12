# waibao-plugin-dingtalk-approval

Reference plugin — DingTalk approval integration.

## What it does

When the host needs to push a recruitment approval (offer / hire /
background-check result) into DingTalk, this plugin translates the
internal payload into DingTalk's approval API format and returns a
process instance id.

## Permissions

| Token | Used for |
|---|---|
| `http:call` | Outbound HTTP to `oapi.dingtalk.com` |
| `events:emit` | Publish `dingtalk.approval.created` |
| `metrics:emit` | Emit usage metrics |

## Sandbox notes

`http:call` is gated by the host's network guard. The default sandbox
allow-list is empty, so the plugin must be installed with an explicit
allow-list entry:

```python
sandbox = SandboxConfig(allow_network_hosts=["oapi.dingtalk.com"])
registry = InstalledPluginRegistry(sandbox=sandbox)
```

## Example

```bash
curl -X POST http://localhost:8000/api/admin/plugins/dingtalk-approval/run \
  -H 'content-type: application/json' \
  -d '{
    "payload": {
      "approval_type": "offer",
      "subject": "Offer for Jane Doe",
      "applicant": "hr_manager_001",
      "form_components": [
        {"name": "candidate", "value": "Jane Doe"},
        {"name": "salary", "value": "180000"}
      ]
    }
  }'
```

Returns:

```json
{
  "process_id": "PROC-7a4c9d2b1e8f0a32",
  "approval_type": "offer",
  "subject": "Offer for Jane Doe",
  "url": "https://example.dingtalk.com/approval/PROC-7a4c9d2b1e8f0a32"
}
```