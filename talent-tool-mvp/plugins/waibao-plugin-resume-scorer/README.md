# waibao-plugin-resume-scorer

Reference plugin — custom resume scoring.

## What it does

Implements a weighted resume scorer agent. Inputs are passed as:

```json
{
  "resume": {
    "skills": ["python", "fastapi", "postgresql"],
    "experience_years": 6,
    "education_level": "master"
  }
}
```

Output:

```json
{
  "score": 0.78,
  "components": {"skill": 0.3, "experience": 0.6, "education": 0.85},
  "weights": {"skill": 0.5, "experience": 0.3, "education": 0.2}
}
```

## Permissions

| Token | Used for |
|---|---|
| `db:read` | Load candidate history |
| `llm:call` | Optional LLM tie-breaker for near-tied candidates |
| `events:emit` | Publish `resume.scored` |
| `metrics:emit` | Emit usage metrics |

## Install

```bash
curl -X POST http://localhost:8000/api/admin/plugins/install \
  -H 'content-type: application/json' \
  -d '{"directory": "/path/to/plugins/waibao-plugin-resume-scorer", "actor": "alice"}'
```

## Enable + run

```bash
curl -X POST http://localhost:8000/api/admin/plugins/resume-scorer/enable \
  -H 'content-type: application/json' -d '{"actor":"alice"}'

curl -X POST http://localhost:8000/api/admin/plugins/resume-scorer/run \
  -H 'content-type: application/json' \
  -d '{"payload": {"resume": {"skills": ["python"], "experience_years": 4, "education_level": "bachelor"}}}'
```