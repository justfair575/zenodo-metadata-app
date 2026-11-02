import base64
import binascii
import csv
import io
import os
import re

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

# Limite específico para inspeção de CSV/TSV.
MAX_INSPECTION_FILE_BYTES = 1_000_000

MAX_SAMPLE_ROWS = 5
MAX_TYPE_INFERENCE_ROWS = 1000

METADATA_NAMES = {
    "readme",
    "readme.md",
    "readme.rst",
    "readme.txt",
    "citation.cff",
    "codemeta.json",
    "license",
    "license.md",
    "license.txt",
    "licence",
    "licence.md",
    "licence.txt",
    "authors",
    "authors.md",
    "contributors.md",
    "zenodo.json",
    "datacite.json",
    "pyproject.toml",
    "package.json",
    "dataset-metadata.json",
    "dataset_info.json",
    "dataset_infos.json",
    "metadata.json",
    "datacard.md",
    "dataset_card.md",
}

DATA_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".parquet",
    ".arrow",
    ".feather",
    ".xlsx",
    ".xls",
    ".xml",
    ".ttl",
    ".rdf",
    ".nt",
    ".nq",
    ".zip",
    ".tar",
    ".gz",
    ".h5",
    ".hdf5",
    ".nc",
    ".netcdf",
    ".tif",
    ".tiff",
    ".png",
    ".jpg",
    ".jpeg",
    ".wav",
    ".mp3",
    ".txt",
}

MISSING_VALUES = {
    "",
    "na",
    "n/a",
    "nan",
    "null",
    "none",
}


class AnalyzeRequest(BaseModel):

    url: str = Field(
        ...,
        min_length=1,
        max_length=500,
    )

    ref: str | None = Field(
        default=None,
        max_length=200,
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:

        value = value.strip()
        parsed = urlparse(value)

        if (
                parsed.scheme != "https"
                or parsed.hostname != "github.com"
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in (None, 443)
                or parsed.query
                or parsed.fragment
        ):
            raise ValueError(
                "Introduz um URL HTTPS válido do GitHub."
            )

        parts = [
            part
            for part in parsed.path.strip("/").split("/")
            if part
        ]

        if len(parts) != 2:
            raise ValueError(
                "Usa o formato https://github.com/owner/repo"
            )

        owner, repo = parts
        repo = repo.removesuffix(".git")

        if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner):
            raise ValueError("Proprietário inválido.")

        if not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
            raise ValueError("Repositório inválido.")

        return f"https://github.com/{owner}/{repo}"


class InspectDatasetRequest(AnalyzeRequest):

    dataset_path: str = Field(
        ...,
        min_length=1,
        max_length=500,
    )

    @field_validator("dataset_path")
    @classmethod
    def validate_dataset_path(cls, value: str) -> str:

        value = value.strip()

        if (
                value.startswith("/")
                or "\\" in value
                or any(part in {".", "..", ""} for part in value.split("/"))
        ):
            raise ValueError("Caminho de ficheiro inválido.")

        return value


def github_headers() -> dict:

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    token = os.getenv("GITHUB_TOKEN")

    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers


async def github_get(
        client: httpx.AsyncClient,
        path: str,
        params: dict | None = None,
):

    try:
        response = await client.get(
            f"{GITHUB_API}{path}",
            params=params,
            headers=github_headers(),
        )

    except httpx.TimeoutException as exc:
        raise HTTPException(
            504,
            "O GitHub demorou demasiado tempo.",
        ) from exc

    except httpx.RequestError as exc:
        raise HTTPException(
            502,
            "Não foi possível contactar o GitHub.",
        ) from exc

    if response.status_code == 404:
        raise HTTPException(
            404,
            "Repositório, referência ou ficheiro não encontrado.",
        )

    if response.status_code in (403, 429):
        raise HTTPException(
            429,
            "Limite da API GitHub atingido ou acesso recusado.",
        )

    if response.status_code >= 400:
        raise HTTPException(
            502,
            f"Erro da API GitHub: HTTP {response.status_code}.",
        )

    try:
        return response.json()

    except ValueError as exc:
        raise HTTPException(
            502,
            "Resposta inválida da API GitHub.",
        ) from exc


def get_repository_parts(url: str) -> tuple[str, str]:

    parsed = urlparse(url)
    owner, repo = parsed.path.strip("/").split("/")[:2]

    return owner, repo.removesuffix(".git")


async def analyze_github_repository(
        request: AnalyzeRequest,
) -> dict:

    owner, repo = get_repository_parts(request.url)

    owner_path = quote(owner, safe="")
    repo_path = quote(repo, safe="")

    async with httpx.AsyncClient(
            timeout=httpx.Timeout(30, connect=5),
            follow_redirects=False,
    ) as client:

        repository = await github_get(
            client,
            f"/repos/{owner_path}/{repo_path}",
        )

        if repository.get("private"):
            raise HTTPException(
                403,
                "Só são suportados repositórios públicos.",
            )

        selected_ref = (
                request.ref or repository.get("default_branch")
        )

        if not selected_ref:
            raise HTTPException(
                422,
                "Não foi encontrada uma branch predefinida.",
            )

        commit = await github_get(
            client,
            f"/repos/{owner_path}/{repo_path}/commits/"
            f"{quote(selected_ref, safe='')}",
        )

        commit_sha = commit.get("sha")

        tree_sha = (
            commit.get("commit", {})
            .get("tree", {})
            .get("sha")
        )

        if not commit_sha or not tree_sha:
            raise HTTPException(
                502,
                "Resposta do GitHub sem SHA válido.",
            )

        tree_response = await github_get(
            client,
            f"/repos/{owner_path}/{repo_path}/git/trees/"
            f"{quote(tree_sha, safe='')}",
            params={"recursive": "1"},
        )

        files = [
            item
            for item in tree_response.get("tree", [])
            if item.get("type") == "blob"
        ]

        warnings = []

        if tree_response.get("truncated"):
            warnings.append(
                "A árvore foi truncada pelo GitHub."
            )

        metadata_candidates = [
            item
            for item in files
            if item["path"].split("/")[-1].lower()
               in METADATA_NAMES
        ][:MAX_METADATA_FILES]

        all_dataset_candidates = [
            item
            for item in files
            if os.path.splitext(item["path"])[1].lower()
               in DATA_EXTENSIONS
        ]

        dataset_candidates = [
            {
                "path": item["path"],
                "size": item.get("size", 0),
                "extension": os.path.splitext(
                    item["path"]
                )[1].lower(),
                "sha": item.get("sha"),
                "confidence": (
                    "high"
                    if os.path.splitext(item["path"])[1].lower()
                       in {".csv", ".tsv", ".parquet", ".feather"}
                    else "medium"
                ),
            }
            for item in all_dataset_candidates
            if item.get("size", 0) <= MAX_DATASET_FILE_BYTES
        ][:MAX_DATASET_CANDIDATES]

        if len(all_dataset_candidates) > MAX_DATASET_CANDIDATES:
            warnings.append(
                "O número de candidatos ultrapassa o limite "
                "de apresentação."
            )

        metadata_files = []
        total_bytes = 0

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
                warnings.append(
                    "Limite total de leitura de metadados atingido."
                )
                break

            content = await github_get(
                client,
                f"/repos/{owner_path}/{repo_path}/contents/"
                f"{quote(path, safe='/')}",
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
                encoded = "".join(
                    content.get("content", "").split()
                )

                raw = base64.b64decode(
                    encoded,
                    validate=True,
                )

                text_content = raw.decode("utf-8-sig")

            except (
                    KeyError,
                    ValueError,
                    binascii.Error,
                    UnicodeDecodeError,
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

        readme = next(
            (
                item["content"]
                for item in metadata_files
                if item["path"].split("/")[-1].lower()
                   in {
                       "readme",
                       "readme.md",
                       "readme.rst",
                       "readme.txt",
                   }
                   and item["status"] == "read"
            ),
            None,
        )

        if not readme:
            warnings.append("README não encontrado.")

        license_info = repository.get("license")

        return {
            "repository": {
                "full_name": repository.get("full_name"),
                "url": repository.get("html_url"),
                "description": repository.get("description"),
                "default_branch": repository.get("default_branch"),
                "selected_ref": selected_ref,
                "commit_sha": commit_sha,
                "license": (
                    license_info.get("spdx_id")
                    if license_info
                    else None
                ),
            },
            "inventory": {
                "total_files": len(files),
                "metadata_files_found": len(metadata_candidates),
                "metadata_files_read": sum(
                    item["status"] == "read"
                    for item in metadata_files
                ),
                "dataset_candidates_found": len(
                    all_dataset_candidates
                ),
                "dataset_candidates_returned": len(
                    dataset_candidates
                ),
            },
            "metadata_files": metadata_files,
            "dataset_candidates": dataset_candidates,
            "warnings": warnings,
        }


def is_missing(value: str | None) -> bool:

    if value is None:
        return True

    return value.strip().lower() in MISSING_VALUES


def infer_column_type(values: list[str]) -> str:

    values = [
        value.strip()
        for value in values
        if not is_missing(value)
    ]

    if not values:
        return "unknown"

    if all(
            value.lower() in {"true", "false"}
            for value in values
    ):
        return "boolean"

    try:
        for value in values:
            int(value)

        return "integer"

    except ValueError:
        pass

    try:
        for value in values:
            float(value)

        return "number"

    except ValueError:
        pass

    return "string"


async def inspect_dataset_in_repository(
        repository_data: dict,
        request: InspectDatasetRequest,
) -> dict:

    candidates = {
        item["path"]: item
        for item in repository_data["dataset_candidates"]
    }

    dataset = candidates.get(request.dataset_path)

    if not dataset:
        raise HTTPException(
            404,
            "O ficheiro selecionado não foi encontrado "
            "na lista de datasets do repositório.",
        )

    extension = dataset["extension"]

    if extension not in {".csv", ".tsv"}:
        raise HTTPException(
            422,
            "Nesta versão só são suportados ficheiros CSV e TSV.",
        )

    if dataset["size"] > MAX_INSPECTION_FILE_BYTES:
        raise HTTPException(
            413,
            "O ficheiro ultrapassa o limite de 1 MB "
            "para inspeção nesta versão.",
        )

    owner, repo = get_repository_parts(request.url)

    owner_path = quote(owner, safe="")
    repo_path = quote(repo, safe="")

    commit_sha = repository_data["repository"]["commit_sha"]

    async with httpx.AsyncClient(
            timeout=httpx.Timeout(30, connect=5),
            follow_redirects=False,
    ) as client:

        content = await github_get(
            client,
            f"/repos/{owner_path}/{repo_path}/contents/"
            f"{quote(request.dataset_path, safe='/')}",
            params={"ref": commit_sha},
        )

    if content.get("encoding") != "base64":
        raise HTTPException(
            422,
            "O GitHub não disponibilizou o ficheiro "
            "num formato de texto suportado.",
        )

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
            422,
            "Não foi possível descodificar o ficheiro.",
        ) from exc

    if len(raw) > MAX_INSPECTION_FILE_BYTES:
        raise HTTPException(
            413,
            "O ficheiro ultrapassa o limite de inspeção.",
        )

    try:
        text_content = raw.decode("utf-8-sig")
        encoding = "utf-8"

    except UnicodeDecodeError:
        try:
            text_content = raw.decode("latin-1")
            encoding = "latin-1"
        except UnicodeDecodeError as exc:
            raise HTTPException(
                422,
                "Não foi possível descodificar o ficheiro.",
            ) from exc

    delimiter = "\t" if extension == ".tsv" else ","

    try:
        try:
            dialect = csv.Sniffer().sniff(
                text_content[:10000],
                delimiters=",;\t|",
            )
            delimiter = dialect.delimiter
        except csv.Error:
            pass

        reader = csv.DictReader(
            io.StringIO(text_content),
            delimiter=delimiter,
        )

        if not reader.fieldnames:
            raise HTTPException(
                422,
                "O ficheiro não contém cabeçalhos CSV válidos.",
            )

        reader.fieldnames = [
            column.strip() if column else ""
            for column in reader.fieldnames
        ]

        columns = reader.fieldnames

        if any(not column for column in columns):
            raise HTTPException(
                422,
                "O ficheiro contém nomes de colunas vazios.",
            )

        if len(set(columns)) != len(columns):
            raise HTTPException(
                422,
                "O ficheiro contém nomes de colunas duplicados.",
            )

        row_count = 0
        sample_rows = []

        column_values = {
            column: []
            for column in columns
        }

        missing_counts = {
            column: 0
            for column in columns
        }

        for row in reader:

            row_count += 1
            clean_row = {}

            for column in columns:

                value = row.get(column)

                if value is None:
                    value = ""

                value = str(value).strip()
                clean_row[column] = value

                if is_missing(value):
                    missing_counts[column] += 1

                elif (
                        len(column_values[column])
                        < MAX_TYPE_INFERENCE_ROWS
                ):
                    column_values[column].append(value)

            if len(sample_rows) < MAX_SAMPLE_ROWS:
                sample_rows.append(clean_row)

    except csv.Error as exc:
        raise HTTPException(
            422,
            "Erro ao interpretar o conteúdo CSV.",
        ) from exc

    column_info = [
        {
            "name": column,
            "inferred_type": infer_column_type(
                column_values[column]
            ),
            "missing_values": missing_counts[column],
        }
        for column in columns
    ]

    return {
        "repository": repository_data["repository"],
        "dataset": {
            "path": request.dataset_path,
            "size": len(raw),
            "format": extension,
            "encoding": encoding,
            "delimiter": delimiter,
            "number_of_records": row_count,
            "number_of_columns": len(columns),
            "columns": column_info,
            "sample_rows": sample_rows,
        },
    }


async def inspect_github_dataset(
        request: InspectDatasetRequest,
) -> dict:

    repository_data = await analyze_github_repository(
        AnalyzeRequest(
            url=request.url,
            ref=request.ref,
        )
    )

    return await inspect_dataset_in_repository(
        repository_data,
        request,
    )