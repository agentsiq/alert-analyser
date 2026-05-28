# Changelog

All notable changes to Alert Analyser are documented here.

## [1.1.0] — 2026-05-28

### Added

- **Noise threshold tuning via Settings UI** — repeat count and auto-close seconds are now configurable fields on the Settings page; saved to DB and applied at runtime without a restart. DB values take priority over `NOISE_THRESHOLD_REPEAT` / `NOISE_THRESHOLD_CLOSE_SECS` env vars.
- **Sync interval configurable via Settings UI** — dropdown on the Settings page (Disabled / 15 min / 30 min / 1 h / 6 h / 24 h); persisted to DB; background task picks up changes immediately via `asyncio.Event` — no restart required.
- **Config persists to DB across restarts** — all settings (source type, OpsGenie credentials, noise thresholds, sync interval) are stored in the `agent_config` table and restored on startup.
- **`agent_slug` scoping** — every `agent_config` row is keyed by `(agent_slug, key)` instead of `(key)` alone, making it safe to share a PostgreSQL instance with other agents without config rows colliding.
- **Encryption fix** — secrets stored without an encryption key (or with a previous key) are automatically re-encrypted with the current `ENCRYPTION_KEY` on startup; eliminates `InvalidToken` log warnings after key rotation.

## [1.0.0] — 2026-05-28

Initial release.

### Features

- Conversational OpsGenie/JSM alert analysis via the standard `/invoke` endpoint
- Rule-based noise classifier: scores every alert on repeat frequency, auto-close rate, acknowledgement, and priority; classifies as `noise` or `genuine`
- Live OpsGenie/JSM sync via Atlassian JSM Ops API (`POST /settings/sync`); auto-syncs on startup when credentials are stored
- JSON alert upload (`POST /reports/upload`) and synthetic sample generation (`POST /reports/generate-sample`)
- Full dashboard aggregation (`GET /dashboard`): noise ratio, MTTR, daily trend, repeat offenders, team breakdown, hourly distribution
- Suppression recommendations via `get_suppression_recommendations` tool — ranked by confidence and auto-resolve rate
- Anthropic API key storage via `POST /settings` — encrypted at rest with Fernet
- OpsGenie credentials (cloud_id, email, api_token) encrypted at rest
- Standalone Docker Compose stack (agent + PostgreSQL)
- Kubernetes manifests with HorizontalPodAutoscaler (min 1, max 5 replicas, 70% CPU threshold)
- `k8s/deploy.sh` for one-command cluster deployment
- Configurable noise thresholds via `NOISE_THRESHOLD_REPEAT` and `NOISE_THRESHOLD_CLOSE_SECS` env vars
