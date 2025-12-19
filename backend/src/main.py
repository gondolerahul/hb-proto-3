from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.auth.router import router as auth_router
from src.common.database import engine, Base

app = FastAPI(title="HireBuddha Platform", version="0.1.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
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
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
from src.config.router import router as config_router
app.include_router(config_router, prefix="/api/v1")
from src.ai.router import router as ai_router
app.include_router(ai_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "Welcome to HireBuddha Platform v2.0"}

from src.common.telemetry import setup_telemetry
setup_telemetry(app)
