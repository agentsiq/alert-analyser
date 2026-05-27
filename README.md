# Alert Analyser

A conversational AI agent for OpsGenie and Jira Service Management (JSM) alert analysis. Connects to your alerting platform, classifies signal from noise, and gives your team actionable suppression recommendations.

## What it does

- **Analyses OpsGenie/JSM alert data** — connects via API or accepts a JSON export; processes up to 100 alerts per sync with full metadata (priority, status, teams, close time)
- **Separates genuine incidents from automated noise** — applies a rule-based scoring model (repeat firings, auto-close rate, acknowledgement status, priority) and classifies every alert as `noise` or `genuine`
- **Identifies repeat offenders** — surfaces the aliases and sources generating the most noise, ranked by frequency and auto-resolve rate
- **Provides suppression recommendations** — generates ranked, copy-paste-ready OpsGenie suppression rules targeting high-confidence noise patterns, so your team can reduce alert fatigue without silencing real incidents

---

## Prerequisites

- Docker and Docker Compose
- An [Anthropic API key](https://console.anthropic.com/)
- A Fernet encryption key (one-liner below)
- For OpsGenie/JSM live sync: your Atlassian Cloud ID, email, and an API token

---

## Quick start — local (5 minutes)

### 1. Clone and configure

```bash
cp .env.example .env
```

Generate an encryption key and add it to `.env`:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Your `.env` should look like:

```
DATABASE_URL=postgresql+asyncpg://alert:alert@postgres:5432/alert
ENCRYPTION_KEY=<your-generated-key>
```

### 2. Start the stack

```bash
docker compose up --build -d
```

The agent is ready when `GET http://localhost:8080/health` returns `{"status": "ok"}`.

### 3. Configure your data source

The agent supports three data sources, all configured via `POST /settings`:

**Option A — OpsGenie / JSM API (live sync)**

```bash
curl -s -X POST http://localhost:8080/settings \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "opsgenie",
    "cloud_id": "<your-atlassian-cloud-id>",
    "email": "you@example.com",
    "api_token": "<your-atlassian-api-token>"
  }'
```

Then trigger a sync:

```bash
curl -s -X POST http://localhost:8080/settings/sync | jq .
```

Alerts are automatically re-synced on every container restart when credentials are stored.

**Option B — file upload (JSON export)**

```bash
curl -s -X POST http://localhost:8080/reports/upload \
  -F "file=@/path/to/opsgenie-export.json" | jq .
```

The file must be a JSON array of OpsGenie alert objects. Export from OpsGenie → Reports → Alerts.

**Option C — synthetic sample data** (no OpsGenie account needed)

```bash
curl -s -X POST http://localhost:8080/reports/generate-sample | jq .
```

Generates 200 synthetic alerts with realistic noise patterns across common aliases and sources.

### 4. Configure your Anthropic API key

```bash
curl -s -X POST http://localhost:8080/settings \
  -H "Content-Type: application/json" \
  -d '{"api_key": "sk-ant-..."}'
```

The key is encrypted at rest using your `ENCRYPTION_KEY`. Alternatively, set `ANTHROPIC_API_KEY` in `.env` before starting.

### 5. Ask your first question

```bash
curl -s -X POST http://localhost:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-1",
    "user_message": "What is my noise rate?",
    "context": {},
    "history": []
  }' | jq .response
```

Other questions to try:

```bash
# Suppression recommendations
"Which alerts should I suppress first?"

# Team breakdown
"Which team has the most noise?"

# Trend analysis
"Show me the daily alert trend for the past week"

# Repeat offenders
"What are my top 5 repeat offenders?"
```

---

## Production deployment — Kubernetes

```bash
bash k8s/deploy.sh \
  --image ghcr.io/your-org/alert-analyser:v1.0.0 \
  --db-url "postgresql+asyncpg://user:password@your-db-host:5432/alert" \
  --encryption-key "<fernet-key>" \
  --namespace ai-agents
```

The script creates the namespace and secret, applies all manifests, and waits for the rollout. See [k8s/deploy.sh](k8s/deploy.sh) for full usage.

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check — returns `{"status": "ok"}` |
| `POST` | `/invoke` | Send a message and receive an AI response |
| `GET` | `/dashboard` | Aggregated noise stats for the most recently loaded report |
| `POST` | `/reports/generate-sample` | Generate 200 synthetic OpsGenie alerts |
| `POST` | `/reports/upload` | Upload a JSON export from OpsGenie |
| `GET` | `/reports` | List all loaded reports |
| `GET` | `/reports/{id}/data` | Return classified alert list for a specific report |
| `GET` | `/settings` | Get current agent configuration |
| `POST` | `/settings` | Update configuration (source, credentials, API key) |
| `POST` | `/settings/sync` | Trigger a live OpsGenie/JSM alert pull |

Interactive API docs are available at `http://localhost:8080/docs` when running locally.

---

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `ENCRYPTION_KEY` | Yes | — | Fernet key for encrypting stored secrets |
| `ANTHROPIC_API_KEY` | No | — | Can be set via `POST /settings` after startup instead |
| `MODEL` | No | `claude-sonnet-4-6` | Claude model to use for inference |
| `PORT` | No | `8080` | HTTP port the server binds to |
| `NOISE_THRESHOLD_REPEAT` | No | `3` | Aliases firing more than this many times in 1 hour are flagged as noise |
| `NOISE_THRESHOLD_CLOSE_SECS` | No | `300` | Alerts that auto-close in fewer than this many seconds are flagged as noise |

---

## OpsGenie / JSM connection guide

The agent connects to the **Atlassian JSM Ops API** (`api.atlassian.com/jsm/ops/api`), which is the current API for both OpsGenie Cloud and JSM Ops. You need three values:

### Cloud ID

1. Go to [admin.atlassian.com](https://admin.atlassian.com)
2. Select your organisation
3. Navigate to **Settings → Products**
4. Your Cloud ID is displayed under each site (e.g. `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)

Alternatively, call `https://api.atlassian.com/oauth/token/accessible-resources` with your API token to list Cloud IDs programmatically.

### API token

1. Go to [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token**
3. Give it a label (e.g. `alert-analyser`) and copy the value immediately — it is not shown again

The token is used with HTTP Basic Auth: `email:token`. The agent handles encoding internally.

### Required permissions

The Atlassian account used for the API token must have **read access to JSM Ops alerts** (typically `Service Desk Agent` role or higher on the relevant project).

---

## Integrating with your platform

The agent follows a standard invoke contract. Any orchestrator that can make HTTP calls can use it.

**Request** — `POST /invoke`:

```json
{
  "session_id": "string",
  "user_message": "string",
  "context": {
    "alerts": [<optional — pre-loaded alert objects for this session>],
    "format": "json"
  },
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

Pass the Anthropic API key per-request via the `X-Anthropic-Key` header if your platform manages keys centrally:

```
X-Anthropic-Key: sk-ant-...
```

**Response**:

```json
{
  "session_id": "string",
  "response": "string",
  "metadata": {
    "tokens_used": 1234,
    "chart": { "type": "bar", "labels": [...], "datasets": [...] }
  }
}
```

The `metadata.chart` field is present only when the agent includes a visualisation in its response.

**Context fields accepted**:

| Field | Type | Description |
|-------|------|-------------|
| `alerts` | array | Pre-loaded alert objects — loaded into the session cache |
| `raw_data` | string | JSON or CSV string of alerts |
| `format` | string | `"json"` (default) or `"csv"` — format for `raw_data` |

---

## Support

Built by [Karthikeyan G](mailto:gkarthikin.g@gmail.com). Report issues and feature requests via GitHub Issues.
