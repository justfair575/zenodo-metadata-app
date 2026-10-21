
import base64
import binascii
import os
from urllib.parse import quote, urlparse

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator

GITHUB_API = "https://api.github.com"

MAX_METADATA_FILES = 20
MAX_METADATA_FILE_BYTES = 200_000
MAX_TOTAL_METADATA_BYTES = 1_000_000
MAX_DATASET_CANDIDATES = 100
MAX_DATASET_FILE_BYTES = 100_000_000

METADATA_NAMES = {
    "readme", "readme.md", "readme.rst", "readme.txt",
    "citation.cff", "codemeta.json",
    "license", "license.md", "license.txt",
    "licence", "licence.md", "licence.txt",
    "authors", "authors.md", "contributors.md",
    "zenodo.json", "datacite.json",
    "pyproject.toml", "package.json",
    "dataset-metadata.json",
}

DATA_EXTENSIONS = {
    ".csv", ".tsv", ".json", ".jsonl", ".parquet",
    ".arrow", ".feather", ".xlsx", ".xls", ".xml",
    ".ttl", ".rdf", ".nt", ".nq", ".zip", ".tar", ".gz",
    ".h5", ".hdf5", ".nc", ".netcdf", ".tif", ".tiff",
    ".png", ".jpg", ".jpeg", ".wav", ".mp3", ".txt",
}


class AnalyzeRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=500)
    ref: str | None = Field(default=None, max_length=200)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlparse(value.strip())

        if (
                parsed.scheme != "https"
                or parsed.hostname != "github.com"
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in (None, 443)
                or parsed.query
                or parsed.fragment
        ):
            raise ValueError("Introduz um URL HTTPS válido do GitHub.")

        parts = parsed.path.strip("/").split("/")

        if len(parts) not in (2, 3) or not all(parts[:2]):
            raise ValueError("Usa o formato https://github.com/owner/repo.")

        if len(parts) == 3 and parts[2].lower() != ".git":
            raise ValueError("O URL deve apontar para a raiz do repositório.")

        owner, repo = parts[:2]

        if owner.startswith(".") or repo.startswith("."):
            raise ValueError("Nome de proprietário ou repositório inválido.")

        repo = repo.removesuffix(".git")
        return f"https://github.com/{owner}/{repo}"


def github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def github_get(client: httpx.AsyncClient, path: str, params=None):
    try:
        response = await client.get(
            f"{GITHUB_API}{path}",
            params=params,
            headers=github_headers(),
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "O GitHub demorou demasiado tempo.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, "Não foi possível contactar o GitHub.") from exc

    if response.status_code == 404:
        raise HTTPException(404, "Repositório, referência ou ficheiro não encontrado.")

    if response.status_code in (403, 429):
        raise HTTPException(429, "Limite da API GitHub atingido ou acesso recusado.")

    if response.status_code >= 400:
        raise HTTPException(502, f"Erro da API GitHub: HTTP {response.status_code}.")

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(502, "Resposta inválida da API GitHub.") from exc


async def analyze_github_repository(request: AnalyzeRequest) -> dict:
    parsed = urlparse(request.url)
    owner, repo = parsed.path.strip("/").split("/")[:2]
    repo = repo.removesuffix(".git")

    owner_path = quote(owner, safe="")
    repo_path = quote(repo, safe="")

    async with httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=5.0),
            follow_redirects=False,
    ) as client:
        repository = await github_get(
            client, f"/repos/{owner_path}/{repo_path}"
        )

        if repository.get("private"):
            raise HTTPException(403, "Só são suportados repositórios públicos.")

        selected_ref = request.ref or repository.get("default_branch")
        if not selected_ref:
            raise HTTPException(422, "Não foi encontrada uma branch predefinida.")

        commit = await github_get(
            client,
            f"/repos/{owner_path}/{repo_path}/commits/"
            f"{quote(selected_ref, safe='')}",
        )

        commit_sha = commit.get("sha")
        tree_sha = (commit.get("commit") or {}).get("tree", {}).get("sha")

        if not commit_sha or not tree_sha:
            raise HTTPException(502, "Resposta do GitHub sem SHA válido.")

        tree_response = await github_get(
            client,
            f"/repos/{owner_path}/{repo_path}/git/trees/"
            f"{quote(tree_sha, safe='')}",
            params={"recursive": "1"},
        )

        files = [
            item for item in tree_response.get("tree", [])
            if item.get("type") == "blob"
        ]

        metadata_candidates = [
            item for item in files
            if item["path"].split("/")[-1].lower() in METADATA_NAMES
        ][:MAX_METADATA_FILES]

        dataset_candidates = [
            {
                "path": item["path"],
                "size": item.get("size", 0),
                "extension": os.path.splitext(item["path"])[1].lower(),
                "sha": item.get("sha"),
            }
            for item in files
            if os.path.splitext(item["path"])[1].lower() in DATA_EXTENSIONS
               and item.get("size", 0) <= MAX_DATASET_FILE_BYTES
        ][:MAX_DATASET_CANDIDATES]

        metadata_files = []
        total_bytes = 0
        warnings = []

        if tree_response.get("truncated"):
            warnings.append(
                "A árvore foi truncada pelo GitHub; o inventário pode estar incompleto."
            )

        for item in metadata_candidates:
            path = item["path"]
            size = item.get("size", 0)

            if size > MAX_METADATA_FILE_BYTES:
                metadata_files.append({
                    "path": path,
                    "size": size,
                    "status": "skipped_too_large",
                })
                continue

            if total_bytes + size > MAX_TOTAL_METADATA_BYTES:
                warnings.append("Limite total de leitura atingido.")
                break

            content = await github_get(
                client,
                f"/repos/{owner_path}/{repo_path}/contents/{quote(path, safe='/')}",
                params={"ref": commit_sha},
            )

            if content.get("encoding") != "base64":
                metadata_files.append({
                    "path": path,
                    "size": size,
                    "status": "unsupported_encoding",
                })
                continue

            try:
                raw = base64.b64decode(content.get("content", ""), validate=True)
                text_content = raw.decode("utf-8")
            except (
                    KeyError, ValueError, binascii.Error, UnicodeDecodeError
            ):
                metadata_files.append({
                    "path": path,
                    "size": size,
                    "status": "decode_error",
                })
                continue

            total_bytes += len(raw)
            metadata_files.append({
                "path": path,
                "size": len(raw),
                "sha": item.get("sha"),
                "status": "read",
                "content": text_content,
            })

        return {
            "repository": {
                "full_name": repository.get("full_name"),
                "url": repository.get("html_url"),
                "description": repository.get("description"),
                "default_branch": repository.get("default_branch"),
                "selected_ref": selected_ref,
                "commit_sha": commit_sha,
                "license": (
                    repository["license"].get("spdx_id")
                    if repository.get("license")
                    else None
                ),
            },
            "inventory": {
                "total_files": len(files),
                "metadata_files_found": len(metadata_candidates),
                "metadata_files_read": sum(
                    item["status"] == "read" for item in metadata_files
                ),
                "dataset_candidates_found": len(dataset_candidates),
            },
            "metadata_files": metadata_files,
            "dataset_candidates": dataset_candidates,
            "warnings": warnings,
        }
