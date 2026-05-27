import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header
from pydantic import BaseModel, Field

from agent import AgentRunner
from config import settings
from routes_dashboard import router as dashboard_router
from routes_reports import router as reports_router
from routes_settings import _config as _agent_config
from routes_settings import _run_opsgenie_sync, load_config_from_db, router as settings_router
from tools.dashboard_builder import DashboardBuilderTool
from tools.noise_detector import NoiseDetectorTool
from tools.source import FileSource
from tools.suppression_advisor import SuppressionAdvisorTool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Alert cache ───────────────────────────────────────────────────────────────
_alert_cache: dict[str, list[dict]] = {}

# ── Agent setup ───────────────────────────────────────────────────────────────
_runner = AgentRunner(
    tools=[
        NoiseDetectorTool(_alert_cache),
        DashboardBuilderTool(_alert_cache),
        SuppressionAdvisorTool(_alert_cache),
    ]
)

# ── Schemas ───────────────────────────────────────────────────────────────────


class InvokeRequest(BaseModel):
    session_id: str
    user_message: str
    context: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)


class InvokeResponse(BaseModel):
    session_id: str
    response: str
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── App ───────────────────────────────────────────────────────────────────────


async def _init_config() -> None:
    from database import engine
    from models import Base

    if engine is None:
        logger.warning("_init_config: DATABASE_URL not configured — skipping DB config load")
        return

    logger.info("_init_config: connecting to %s", str(engine.url))

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("_init_config: agent_config table ensured")

    db_cfg = await load_config_from_db()
    if not db_cfg:
        logger.info("_init_config: no saved config found — waiting for user setup")
        return

    logger.info("_init_config: config loaded from DB — source_type: %s", db_cfg.get("source_type", "file"))

    if (
        db_cfg.get("source_type") == "opsgenie"
        and db_cfg.get("cloud_id")
        and db_cfg.get("email")
        and db_cfg.get("api_token")
    ):
        logger.info("Config loaded from DB — OpsGenie auto-sync running")
        try:
            result = await _run_opsgenie_sync()
            logger.info("OpsGenie auto-sync complete — %d alerts loaded", result["alert_count"])
        except Exception:
            logger.exception("OpsGenie auto-sync failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await _init_config()
    except Exception:
        logger.exception("Config initialisation raised an unexpected exception (agent will still start)")
    yield


app = FastAPI(title=settings.agent_name, version="1.0.0", lifespan=lifespan)
app.include_router(dashboard_router)
app.include_router(reports_router)
app.include_router(settings_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "agent": settings.agent_slug}


@app.post("/invoke", response_model=InvokeResponse)
async def invoke(
    body: InvokeRequest,
    x_anthropic_key: str | None = Header(default=None),
) -> InvokeResponse:
    ctx = body.context

    if "raw_data" in ctx:
        source = FileSource(ctx["raw_data"], ctx.get("format", "json"))
        _alert_cache[body.session_id] = await source.load_alerts()
    elif "alerts" in ctx:
        _alert_cache[body.session_id] = ctx["alerts"]

    has_data = bool(_alert_cache.get(body.session_id))
    alert_count = len(_alert_cache.get(body.session_id, []))

    # Key resolution: request header > DB-stored key > ANTHROPIC_API_KEY env var
    db_api_key = _agent_config.get("api_key") or None
    resolved_key = x_anthropic_key or db_api_key

    response_text, tokens = await _runner.run(
        user_message=body.user_message,
        context={"session_id": body.session_id, "has_data": has_data, "alert_count": alert_count},
        history=body.history,
        api_key=resolved_key,
    )

    chart_data = None
    if "```chart" in response_text:
        try:
            start = response_text.index("```chart") + 8
            end = response_text.index("```", start)
            chart_data = json.loads(response_text[start:end].strip())
            response_text = response_text[: response_text.index("```chart")].strip()
        except Exception:
            pass

    metadata: dict[str, Any] = {"tokens_used": tokens}
    if chart_data is not None:
        metadata["chart"] = chart_data

    return InvokeResponse(
        session_id=body.session_id,
        response=response_text,
        metadata=metadata,
    )
