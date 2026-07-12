# waibao-plugin-interview-bot

Reference plugin — conversational interview bot.

## Actions

The service surface accepts an `action` payload:

| Action | Description |
|---|---|
| `start` | Initialise a new session, returns the first question |
| `next_question` | Continue, returns the next not-yet-asked question |
| `complete` | Mark session done; emits `interview.session_completed` |

## Permissions

| Token | Used for |
|---|---|
| `llm:call` | Generate follow-up clarifications |
| `events:emit` | Publish `interview.question_asked`, `interview.session_completed` |
| `metrics:emit` | Emit usage metrics |

## Example

```bash
# Start session
curl -X POST http://localhost:8000/api/admin/plugins/interview-bot/run \
  -H 'content-type: application/json' \
  -d '{"payload": {"action":"start","session_id":"s-1"}}'

# Continue
curl -X POST http://localhost:8000/api/admin/plugins/interview-bot/run \
  -H 'content-type: application/json' \
  -d '{"payload": {"action":"next_question","session_id":"s-1","asked":["tell_me_about_yourself"]}}'

# Complete
curl -X POST http://localhost:8000/api/admin/plugins/interview-bot/run \
  -H 'content-type: application/json' \
  -d '{"payload": {"action":"complete","session_id":"s-1","asked":["a","b"],"duration_s":900}}'
```