"""FastAPI app: loads the model and database once at startup, adds CORS, rate limiting and safe error handling.

Run from the project root:  uvicorn backend.app.main:app --reload
API docs: http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app import config
from backend.app.api.routes import router
from backend.app.database import session
from backend.app.ml.predictor import Predictor
from backend.app.services.traffic import register_model
from backend.app.utils.rate_limit import RateLimitMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("nids")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if session.engine is None:  # tests set up their own database first
        session.init_engine(config.DATABASE_URL)
    app.state.predictor = Predictor(config.MODEL_PATH, config.METRICS_PATH)
    with session.SessionLocal() as db:
        app.state.model_id = register_model(db, app.state.predictor).id
    log.info("model %s loaded (id %s)", app.state.predictor.model_name, app.state.model_id)
    yield


app = FastAPI(title="AI Network Intrusion Detection API", version="1.0.0", lifespan=lifespan)
app.add_middleware(RateLimitMiddleware, per_minute=config.RATE_LIMIT_PER_MINUTE)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"])


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    # Full details go to the server log only; the client never sees stack traces or SQL.
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


app.include_router(router)
