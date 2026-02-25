from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.auth.router import router as auth_router
from src.common.database import engine, Base

app = FastAPI(title="HireBuddha Platform", version="0.2.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://34.100.230.121:3000",
        "https://dev.hirebuddha.com",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://gateway.hirebuddha.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.common.middleware import CompanySuspensionMiddleware
app.add_middleware(CompanySuspensionMiddleware)



app.include_router(auth_router, prefix="/api/v1")
from src.auth.company_router import router as company_router
app.include_router(company_router, prefix="/api/v1")
from src.auth.profile_router import router as profile_router
app.include_router(profile_router, prefix="/api/v1")
from src.auth.user_router import router as user_router
app.include_router(user_router, prefix="/api/v1")

from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Ensure reports and artifact directories exist
reports_dir = Path("/tmp/research_reports")
reports_dir.mkdir(parents=True, exist_ok=True)
artifact_dir = Path("/home/rahul/workspace/dev-hb-codebase/hb-proto-3/backend/artifact")
artifact_dir.mkdir(parents=True, exist_ok=True)

# Ensure assets directory exists (hierarchical: assets/{tenant_id}/{campaign_id}/{asset_type}/{date})
assets_dir = Path("/home/rahul/workspace/dev-hb-codebase/hb-proto-3/backend/assets")
assets_dir.mkdir(parents=True, exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/reports", StaticFiles(directory=str(reports_dir)), name="reports")
app.mount("/artifact", StaticFiles(directory=str(artifact_dir)), name="artifact")
app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

from src.config.router import router as config_router
app.include_router(config_router, prefix="/api/v1")
from src.ai.router import router as ai_router
app.include_router(ai_router, prefix="/api/v1")
from src.ai.campaign_router import router as campaign_router
app.include_router(campaign_router, prefix="/api/v1")

# Asset management
from src.ai.asset_router import router as asset_router
app.include_router(asset_router)

# Billing, reports, credits, and cron jobs
try:
    from src.billing.billing_router import router as billing_router
    app.include_router(billing_router)
    from src.billing.credits_router import router as credits_router
    app.include_router(credits_router)
    from src.billing.cron_router import router as cron_router
    app.include_router(cron_router)
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"Could not import billing routers: {e}")

# Email connection management
try:
    from src.ai.email_router import router as email_router
    app.include_router(email_router, prefix="/api/v1")
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"Could not import email router: {e}")

# Voice and WhatsApp streaming webhooks
try:
    from src.streaming.webhook_router import router as webhook_router
    app.include_router(webhook_router)  # No prefix - webhooks are at /webhooks/voice/*
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"Could not import streaming webhook router: {e}")

try:
    from src.streaming.phone_number_router import router as phone_number_router
    app.include_router(phone_number_router)
    from src.streaming.sessions_router import router as sessions_router
    app.include_router(sessions_router)
    from src.streaming.messaging_router import router as messaging_router
    app.include_router(messaging_router)
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"Could not import streaming routers: {e}")



@app.get("/")
async def root():
    return {"message": "Welcome to HireBuddha Platform v2.0"}

from src.common.telemetry import setup_telemetry
setup_telemetry(app)
