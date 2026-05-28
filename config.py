from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Anthropic — set via ANTHROPIC_API_KEY env var or POST /settings {"api_key": "..."}
    # Can also be passed per-request via X-Anthropic-Key header.
    anthropic_api_key: str = ""
    model: str = "claude-sonnet-4-6"

    # Agent identity
    agent_slug: str = "alert-analyser"
    agent_name: str = "Alert Analyser"

    # Database — required for persistent settings (API key storage, OpsGenie credentials)
    database_url: str = ""

    # Noise classification thresholds (overridden by DB values at runtime if saved via Settings UI)
    noise_threshold_repeat: int = 3      # aliases firing >N times in 1 hour are noise
    noise_threshold_close_secs: int = 300  # auto-close in <N seconds is noise

    # Auto-sync interval; 0 disables the background task
    sync_interval_minutes: int = 0

    # Server
    port: int = 8080

    @property
    def agent_system_prompt(self) -> str:
        return (
            "You are an alert intelligence agent specialising in OpsGenie data analysis.\n\n"
            "When alert data is available for the session, use your tools:\n"
            "  • classify_alerts       — classify alerts as noise or genuine (call this first)\n"
            "  • build_dashboard       — compute overview stats, MTTR, trend data, team breakdown\n"
            "  • get_suppression_recommendations — generate ranked suppression rules from noise patterns\n\n"
            "Always ground answers in tool output. Use specific counts, percentages, and alias names.\n\n"
            "Noise classification rules applied:\n"
            f"  +2  fires >{3}× within 1 hour\n"
            "  +2  auto-closes in <5 min without acknowledgement\n"
            "  +1  never acknowledged\n"
            "  -3  priority is P1 or P2\n"
            "  -2  open >30 minutes\n"
            "  → classified as noise if net score > 0\n\n"
            "When including charts, embed them as a JSON block at the end of your response:\n"
            "```chart\n"
            '{\"type\": \"bar\", \"labels\": [...], \"datasets\": [{\"label\": \"...\", \"data\": [...]}]}\n'
            "```\n\n"
            "If no alert data is loaded, ask the user to upload a JSON or CSV export from OpsGenie, "
            "configure an OpsGenie/JSM connection via POST /settings, or generate sample data."
        )


settings = Settings()
