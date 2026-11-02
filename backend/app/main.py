
import base64
import binascii
import httpx
import tempfile

from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.github_service import (
    AnalyzeRequest,
    InspectDatasetRequest,
    analyze_github_repository,
    inspect_dataset_in_repository,
    github_get,
    get_repository_parts,
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
    ExtractedMetadata,
)

from app.metadata_review import apply_metadata_reviews
from app.metadata_validation import validate_metadata_field

from app.croissant_generator import build_croissant


# ============================================================
# REQUEST MODELS
# ============================================================

class CroissantGenerateRequest(InspectDatasetRequest):
    metadata: ExtractedMetadata


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Zenodo Metadata Assistant",
    version="0.5.0",
    description=(
        "GitHub dataset analysis, AI metadata extraction "
        "and MLCommons Croissant generation."
    ),
)


# ============================================================
# CORS
# ============================================================

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


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():

    return {
        "status": "ok",
    }


# ============================================================
# OLLAMA STATUS
# ============================================================

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


# ============================================================
# ANALYZE GITHUB REPOSITORY
# ============================================================

@app.post("/api/v1/analyze")
async def analyze_repository(
        request: AnalyzeRequest,
):

    return await analyze_github_repository(request)


# ============================================================
# EXTRACT REPOSITORY METADATA
# ============================================================

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


# ============================================================
# INSPECT SELECTED DATASET
# ============================================================

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


# ============================================================
# EXTRACT METADATA FROM SELECTED DATASET
# ============================================================

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


# ============================================================
# CONFIRM METADATA
# ============================================================

@app.post(
    "/api/v1/metadata/confirm",
    response_model=ConfirmedMetadataResponse,
)
async def confirm_metadata(
        request: ConfirmMetadataRequest,
):

    return apply_metadata_reviews(request)


# ============================================================
# GENERATE CROISSANT
# ============================================================

@app.post("/api/v1/croissant/generate")
async def generate_croissant_endpoint(
        request: CroissantGenerateRequest,
):

    # 1. Verificar os sete campos obrigatórios antes de
    #    descarregar o ficheiro do GitHub.

    required_fields = [
        "title",
        "description",
        "creators",
        "license",
        "date_published",
        "dataset_type",
        "data_modality",
    ]

    pending_fields = []
    field_errors = {}

    for field_name in required_fields:

        field = getattr(request.metadata, field_name)

        is_empty_value = (
                field.value is None
                or (
                        isinstance(field.value, str)
                        and not field.value.strip()
                )
                or (
                        isinstance(field.value, (list, dict))
                        and len(field.value) == 0
                )
        )

        if field.status != "confirmed" or is_empty_value:
            pending_fields.append(field_name)
            continue

        # Validar novamente no endpoint de geração.
        # Assim, um pedido direto à API não consegue contornar
        # as regras aplicadas durante a revisão dos metadados.
        errors = validate_metadata_field(
            field_name,
            field.value,
        )

        if errors:
            field_errors[field_name] = errors

    if pending_fields or field_errors:
        detail = {
            "message": (
                "Não é possível gerar o Croissant. "
                "Existem campos por confirmar ou valores inválidos."
            ),
        }

        if pending_fields:
            detail["pending_fields"] = pending_fields

        if field_errors:
            detail["field_errors"] = field_errors

        raise HTTPException(
            status_code=422,
            detail=detail,
        )

    # 2. Analisar novamente o repositório.

    repository_data = await analyze_github_repository(
        AnalyzeRequest(
            url=request.url,
            ref=request.ref,
        )
    )

    # 3. Inspecionar novamente o dataset selecionado.

    inspection = await inspect_dataset_in_repository(
        repository_data,
        request,
    )

    dataset_info = inspection["dataset"]

    # 4. Obter a identificação do repositório e do commit.

    commit_sha = repository_data["repository"]["commit_sha"]

    owner, repo = get_repository_parts(request.url)

    owner_path = quote(owner, safe="")
    repo_path = quote(repo, safe="")

    dataset_path = quote(
        request.dataset_path,
        safe="/",
    )

    # 5. Descarregar o ficheiro através da GitHub API.

    async with httpx.AsyncClient(
            timeout=httpx.Timeout(30, connect=5),
            follow_redirects=False,
    ) as client:

        content = await github_get(
            client=client,
            path=(
                f"/repos/{owner_path}/{repo_path}/contents/"
                f"{dataset_path}"
            ),
            params={
                "ref": commit_sha,
            },
        )

    # 6. Confirmar o formato da resposta.

    if content.get("encoding") != "base64":

        raise HTTPException(
            status_code=422,
            detail=(
                "O GitHub não disponibilizou o dataset "
                "num formato Base64 suportado."
            ),
        )

    # 7. Descodificar o conteúdo.

    try:

        encoded = "".join(
            content.get("content", "").split()
        )

        raw = base64.b64decode(
            encoded,
            validate=True,
        )

    except (
            ValueError,
            binascii.Error,
    ) as exc:

        raise HTTPException(
            status_code=422,
            detail=(
                "Não foi possível descodificar "
                "o ficheiro do GitHub."
            ),
        ) from exc

    # 8. Confirmar o limite de inspeção.

    if len(raw) > 1_000_000:

        raise HTTPException(
            status_code=413,
            detail=(
                "O dataset ultrapassa o limite de "
                "1 MB para esta versão."
            ),
        )

    # 9. Construir o URL do ficheiro na versão exata
    #    do repositório analisado.

    source_content_url = (
        "https://raw.githubusercontent.com/"
        f"{owner_path}/"
        f"{repo_path}/"
        f"{quote(commit_sha, safe='')}/"
        f"{dataset_path}"
    )

    # 10. Preparar e validar o caminho relativo.

    relative_path = Path(request.dataset_path)

    if (
            relative_path.is_absolute()
            or relative_path.drive
            or ".." in relative_path.parts
            or "\\" in request.dataset_path
    ):
        raise HTTPException(
            status_code=422,
            detail="Caminho do dataset inválido.",
        )

    # 11. Criar uma pasta temporária.
    #     É eliminada automaticamente no final do pedido.

    with tempfile.TemporaryDirectory(
            prefix="gg_ads_croissant_",
    ) as temp_dir:

        dataset_directory = Path(temp_dir).resolve()

        local_dataset = (
                dataset_directory / relative_path
        ).resolve()

        try:

            local_dataset.relative_to(
                dataset_directory
            )

        except ValueError as exc:

            raise HTTPException(
                status_code=422,
                detail="Caminho do dataset fora da pasta temporária.",
            ) from exc

        # 12. Criar a estrutura de diretórios necessária.

        local_dataset.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # 13. Guardar temporariamente o dataset.

        local_dataset.write_bytes(raw)

        output_path = (
                dataset_directory / "croissant.json"
        )

        # 14. Gerar e validar o documento Croissant.

        croissant = build_croissant(
            dataset_directory=dataset_directory,
            dataset_relative_path=relative_path.as_posix(),
            output_path=output_path,
            source_content_url=source_content_url,
            repository_url=repository_data["repository"]["url"],
            metadata=request.metadata,
            inspection=inspection,
        )

        # 15. Devolver o resultado.
        #     O JSON é carregado em memória antes da eliminação
        #     da pasta temporária.

        return {
            "filename": "croissant.json",
            "format": "JSON-LD",
            "validated": True,
            "repository": repository_data["repository"]["full_name"],
            "commit_sha": commit_sha,
            "selected_dataset": dataset_info["path"],
            "croissant": croissant,
        }
