
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.github_service import AnalyzeRequest, analyze_github_repository

app = FastAPI(
    title="Zenodo Metadata Assistant",
    version="0.1.0",
    description="GitHub ingestion for dataset metadata curation.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/analyze")
async def analyze_repository(request: AnalyzeRequest):
    return await analyze_github_repository(request)
