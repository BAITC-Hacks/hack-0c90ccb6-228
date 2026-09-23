"""Smart Contractor: one Python service for the API and frontend."""
import json
import os
import time
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from llm_explainer import Explainer
from matcher import load_catalog, match
from models import DATE_MAX, DATE_MIN, MatchRequest

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.catalog = load_catalog(Path(os.getenv("DATASET_PATH", ROOT / "hackathon-dataset-anonymized.jsonl")))
    app.state.explainer = Explainer(api_key=os.getenv("OPENAI_API_KEY", ""),
                                   model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                                   timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "6.5")))
    app.state.requests = OrderedDict()
    yield
    await app.state.explainer.close()


app = FastAPI(title="Smart Contractor", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.url.path == "/api/match":
        try:
            content_length = int(request.headers.get("content-length", "0") or "0")
        except ValueError:
            return JSONResponse({"detail": "Некорректный Content-Length"}, status_code=400)
        if content_length > 8192:
            return JSONResponse({"detail": "Слишком большой запрос"}, status_code=413)
        # Trust forwarded IPs only through a configured reverse proxy/Uvicorn.
        ip = request.client.host if request.client else "unknown"
        buckets = request.app.state.requests
        now = time.monotonic()
        bucket = buckets.setdefault(ip, deque())
        buckets.move_to_end(ip)
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= int(os.getenv("RATE_LIMIT_PER_MINUTE", "30")):
            return JSONResponse({"detail": "Слишком много запросов. Попробуйте через минуту."},
                                status_code=429, headers={"Retry-After": "60"})
        bucket.append(now)
        if len(buckets) > 10000:
            buckets.popitem(last=False)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(status_code=422, content={"detail": "Проверьте параметры запроса.",
        "errors": [{"field": ".".join(str(x) for x in error["loc"][1:]), "message": error["msg"]}
                   for error in exc.errors()]})


@app.get("/healthz")
async def health():
    return {"status": "ok", "profiles": len(app.state.catalog),
            "llm_configured": bool(app.state.explainer.client)}


@app.get("/api/meta")
async def metadata():
    profiles = app.state.catalog
    return {"cities": ["Алматы", "Астана", "Зарубежье"],
            "categories": sorted({c for p in profiles for c in p.categories}),
            "event_formats": sorted({f for p in profiles for f in p.event_formats}),
            "languages": sorted({l for p in profiles for l in p.languages}),
            "date_min": DATE_MIN, "date_max": DATE_MAX,
            "profile_count": len(profiles), "synthetic_count": sum(p.synthetic for p in profiles),
            # Only matching fields are needed by the date matrix, never names or descriptions.
            "availability_profiles": [p.model_dump(mode="json", include={
                "categories", "city", "price_from_kzt", "event_formats", "languages",
                "max_hours", "busy_dates"}) for p in profiles],
            "llm_configured": bool(app.state.explainer.client),
            "demos": json.loads((ROOT / "demo-queries.json").read_text(encoding="utf-8"))}


@app.post("/api/match")
async def match_api(request: MatchRequest):
    start = time.perf_counter()
    result = match(app.state.catalog, request)
    profiles = result.pop("selected")
    explanations = await app.state.explainer.explain_many(profiles, request)
    cards = []
    for index, (profile, explanation) in enumerate(zip(profiles, explanations), start=1):
        cards.append({"id": profile.id, "name": f"Кандидат #{index}" if request.blind_mode else profile.anon_name,
                      "category": request.category, "city": profile.city, "price_from_kzt": profile.price_from_kzt,
                      "languages": profile.languages, "max_hours": profile.max_hours,
                      "synthetic": profile.synthetic, "city_imputed": profile.city_imputed,
                      "price_imputed": profile.price_imputed, "explanation": explanation.text,
                      "evidence": explanation.evidence, "explanation_source": explanation.source,
                      "available_on": request.event_date.isoformat()})
    fallback = any(e.source == "catalog" for e in explanations)
    result.update({"candidates": cards, "request": request.model_dump(mode="json"),
                   "explanation_mode": "catalog" if fallback else "openai" if cards else "none",
                   "elapsed_ms": round((time.perf_counter() - start) * 1000),
                   "notice": "Объяснения составлены из фактов каталога; AI-отбор фактов сейчас недоступен." if fallback else None})
    return result


@app.get("/")
async def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
