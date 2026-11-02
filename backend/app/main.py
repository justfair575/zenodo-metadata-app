
import httpx

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.github_service import (
    AnalyzeRequest,
    InspectDatasetRequest,
    analyze_github_repository,
    inspect_dataset_in_repository,
)

from app.metadata_extractor import (
    extract_repository_metadata,
)

from app.ollama_service import (
    OLLAMA_URL,
    OLLAMA_MODEL,
)

from app.metadata_schema import (
    ConfirmMetadataRequest,
    ConfirmedMetadataResponse,
)

from app.metadata_review import apply_metadata_reviews


app = FastAPI(
    title="Zenodo Metadata Assistant",
    version="0.4.0",
    description=(
        "GitHub dataset analysis and AI metadata extraction."
    ),
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

    return {
        "status": "ok",
    }


@app.get("/api/v1/ollama-status")
async def ollama_status():

    try:

        async with httpx.AsyncClient(
                timeout=5,
        ) as client:

            response = await client.get(
                f"{OLLAMA_URL}/api/tags"
            )

            response.raise_for_status()

            data = response.json()

            models = [
                item["name"]
                for item in data.get("models", [])
            ]

            configured_base = OLLAMA_MODEL.split(":")[0]

            model_installed = any(
                name == OLLAMA_MODEL
                or name.split(":")[0] == configured_base
                for name in models
            )

            return {
                "available": True,
                "configured_model": OLLAMA_MODEL,
                "model_installed": model_installed,
                "installed_models": models,
            }

    except Exception:

        return {
            "available": False,
            "configured_model": OLLAMA_MODEL,
            "model_installed": False,
            "installed_models": [],
        }


@app.post("/api/v1/analyze")
async def analyze_repository(
        request: AnalyzeRequest,
):

    return await analyze_github_repository(request)


@app.post("/api/v1/extract")
async def extract_metadata(
        request: AnalyzeRequest,
):

    repository_data = await analyze_github_repository(
        request
    )

    metadata = await extract_repository_metadata(
        repository_data
    )

    return {
        "repository": repository_data["repository"],
        "inventory": repository_data["inventory"],
        "metadata": metadata.model_dump(),
        "dataset_candidates": repository_data[
            "dataset_candidates"
        ],
        "warnings": repository_data["warnings"],
    }


@app.post("/api/v1/inspect-dataset")
async def inspect_dataset(
        request: InspectDatasetRequest,
):

    repository_data = await analyze_github_repository(
        AnalyzeRequest(
            url=request.url,
            ref=request.ref,
        )
    )

    inspection = await inspect_dataset_in_repository(
        repository_data,
        request,
    )

    return inspection


@app.post("/api/v1/extract-dataset")
async def extract_dataset_metadata(
        request: InspectDatasetRequest,
):

    # 1. Analisar o repositório.
    repository_data = await analyze_github_repository(
        AnalyzeRequest(
            url=request.url,
            ref=request.ref,
        )
    )

    # 2. Inspecionar o dataset selecionado.
    inspection = await inspect_dataset_in_repository(
        repository_data,
        request,
    )

    # 3. Extrair sugestões de metadados usando o Ollama.
    metadata = await extract_repository_metadata(
        repository_data,
        dataset_inspection=inspection["dataset"],
    )

    # 4. Devolver os resultados.
    return {
        "repository": repository_data["repository"],
        "inventory": repository_data["inventory"],
        "selected_dataset": inspection["dataset"],
        "metadata": metadata.model_dump(),
        "dataset_candidates": repository_data[
            "dataset_candidates"
        ],
        "warnings": repository_data["warnings"],
    }


@app.post(
    "/api/v1/metadata/confirm",
    response_model=ConfirmedMetadataResponse,
)
async def confirm_metadata(
        request: ConfirmMetadataRequest,
):

    return apply_metadata_reviews(request)
