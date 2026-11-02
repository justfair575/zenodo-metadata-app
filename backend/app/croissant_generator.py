
import json
from pathlib import Path
from typing import Any

import mlcroissant as mlc

from fastapi import HTTPException

from croissant_baker.metadata_generator import MetadataGenerator

from app.metadata_schema import ExtractedMetadata, MetadataField


REQUIRED_FIELDS = [
    "title",
    "description",
    "creators",
    "license",
    "date_published",
    "dataset_type",
    "data_modality",
]


def is_empty(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    if isinstance(value, (list, dict)):
        return len(value) == 0

    return False


def get_confirmed_value(
        metadata: ExtractedMetadata,
        field_name: str,
) -> Any:

    field = getattr(metadata, field_name)

    if not isinstance(field, MetadataField):
        raise HTTPException(
            status_code=422,
            detail=f"Formato inválido no campo '{field_name}'.",
        )

    if field.status != "confirmed" or is_empty(field.value):
        raise HTTPException(
            status_code=422,
            detail=(
                f"O campo '{field_name}' tem de estar confirmado "
                "e conter um valor."
            ),
        )

    return field.value


def get_optional_confirmed_value(
        metadata: ExtractedMetadata,
        field_name: str,
) -> Any | None:

    field = getattr(metadata, field_name)

    if (
            isinstance(field, MetadataField)
            and field.status == "confirmed"
            and not is_empty(field.value)
    ):
        return field.value

    return None


def normalize_creators(value: Any) -> list[dict[str, str]]:

    if isinstance(value, str):
        value = [value]

    if not isinstance(value, list) or not value:
        raise HTTPException(
            status_code=422,
            detail="É necessário indicar pelo menos um criador.",
        )

    creators = []

    for creator in value:

        if isinstance(creator, str):
            creator_data = {
                "name": creator.strip(),
            }

        elif isinstance(creator, dict):
            creator_data = {
                str(key): str(item).strip()
                for key, item in creator.items()
                if item is not None and str(item).strip()
            }

        else:
            creator_data = {}

        if not creator_data.get("name"):
            raise HTTPException(
                status_code=422,
                detail="Cada criador tem de possuir um nome.",
            )

        creators.append(creator_data)

    return creators


def normalize_string_list(value: Any) -> list[str]:

    if isinstance(value, str):
        value = [value]

    if not isinstance(value, list):
        raise HTTPException(
            status_code=422,
            detail="O valor tem de ser texto ou uma lista de textos.",
        )

    return [
        str(item).strip()
        for item in value
        if str(item).strip()
    ]


def add_property(
        metadata: dict,
        name: str,
        value: Any,
) -> None:

    if is_empty(value):
        return

    properties = metadata.setdefault("additionalProperty", [])

    properties.append({
        "@type": "PropertyValue",
        "name": name,
        "value": value,
    })


def build_croissant(
        dataset_directory: str | Path,
        dataset_relative_path: str,
        output_path: str | Path,
        source_content_url: str,
        repository_url: str,
        metadata: ExtractedMetadata,
        inspection: dict,
) -> dict:
    """
    Gera Croissant com Croissant Baker e valida o documento final.

    dataset_directory:
        Diretório local temporário que contém o dataset.

    dataset_relative_path:
        Caminho do ficheiro relativamente ao diretório temporário.

    output_path:
        Caminho onde será guardado o croissant.json.

    source_content_url:
        URL do ficheiro no commit específico do GitHub.

    repository_url:
        URL do repositório GitHub.

    metadata:
        Metadados do GG ADS, com estados de confirmação.

    inspection:
        Resultado de inspect_dataset_in_repository().
    """

    # 1. Validar os sete campos obrigatórios.

    values = {
        field_name: get_confirmed_value(metadata, field_name)
        for field_name in REQUIRED_FIELDS
    }

    # 2. Validar o ficheiro local.

    dataset_directory = Path(dataset_directory).resolve()
    output_path = Path(output_path).resolve()

    relative_path = Path(dataset_relative_path)

    if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or "\\" in dataset_relative_path
    ):
        raise HTTPException(
            status_code=422,
            detail="Caminho local do dataset inválido.",
        )

    local_dataset = (dataset_directory / relative_path).resolve()

    try:
        local_dataset.relative_to(dataset_directory)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="O dataset tem de estar dentro do diretório temporário.",
        ) from exc

    if not local_dataset.is_file():
        raise HTTPException(
            status_code=404,
            detail="O ficheiro local do dataset não foi encontrado.",
        )

    # 3. Obter informação técnica da inspeção.

    dataset_info = inspection.get("dataset", {})

    dataset_format = dataset_info.get("format")

    if dataset_format not in {".csv", ".tsv"}:
        raise HTTPException(
            status_code=422,
            detail="Nesta versão só são suportados CSV e TSV.",
        )

    if dataset_info.get("path") is None:
        raise HTTPException(
            status_code=422,
            detail="A inspeção não identifica o caminho do dataset.",
        )

    # 4. Preparar os dados confirmados para o Baker.

    creators = normalize_creators(values["creators"])

    keywords = get_optional_confirmed_value(
        metadata,
        "keywords",
    )

    language = get_optional_confirmed_value(
        metadata,
        "language",
    )

    date_published = str(values["date_published"]).strip()

    # 5. Criar o MetadataGenerator.

    generator = MetadataGenerator(
        dataset_path=str(dataset_directory),
        name=str(values["title"]),
        description=str(values["description"]),
        url=repository_url,
        license=str(values["license"]),
        date_published=date_published,
        creators=creators,
        keywords=(
            normalize_string_list(keywords)
            if keywords
            else None
        ),
        in_language=(
            normalize_string_list(language)
            if language
            else None
        ),
        count_csv_rows=True,
        includes=[relative_path.as_posix()],
    )

    # 6. Gerar e guardar o documento inicial.
    # A validação será feita depois de integrar os campos do GG ADS.

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        generator.save_metadata(
            str(output_path),
            validate=False,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"O Croissant Baker não conseguiu gerar os metadados: {exc}",
        ) from exc

    if not output_path.is_file():
        raise HTTPException(
            status_code=500,
            detail="O Croissant Baker não criou o ficheiro de saída.",
        )

    # 7. Ler o JSON-LD gerado pelo Baker.

    try:
        with output_path.open("r", encoding="utf-8") as file:
            croissant = json.load(file)

    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Não foi possível ler o JSON-LD gerado.",
        ) from exc

    # 8. Substituir o contentUrl local pelo URL do commit GitHub.
    # O SHA-256 calculado pelo Baker é preservado.

    distributions = croissant.get("distribution", [])

    if not distributions:
        raise HTTPException(
            status_code=422,
            detail="O Croissant Baker não criou uma distribuição.",
        )

    for distribution in distributions:
        distribution["contentUrl"] = source_content_url

    # 9. Garantir os valores confirmados do GG ADS no documento final.

    croissant["name"] = values["title"]
    croissant["description"] = values["description"]
    croissant["url"] = repository_url
    croissant["datePublished"] = date_published

    croissant["creator"] = [
        {
            "@type": "sc:Person",
            **creator,
        }
        for creator in creators
    ]

    # 10. Acrescentar os campos específicos da aplicação.

    add_property(
        croissant,
        "Dataset type",
        values["dataset_type"],
    )

    add_property(
        croissant,
        "Data modality",
        values["data_modality"],
    )

    add_property(
        croissant,
        "Number of records",
        dataset_info.get("number_of_records"),
    )

    add_property(
        croissant,
        "Number of columns",
        dataset_info.get("number_of_columns"),
    )

    add_property(
        croissant,
        "File format",
        dataset_format.lstrip(".").upper(),
    )

    add_property(
        croissant,
        "File encoding",
        dataset_info.get("encoding"),
    )

    add_property(
        croissant,
        "Delimiter",
        dataset_info.get("delimiter"),
    )

    machine_learning_task = get_optional_confirmed_value(
        metadata,
        "machine_learning_task",
    )

    if machine_learning_task:
        add_property(
            croissant,
            "Machine learning task",
            machine_learning_task,
        )

    # 11. Guardar o documento final.

    try:
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(
                croissant,
                file,
                ensure_ascii=False,
                indent=2,
            )

    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Não foi possível guardar o documento Croissant.",
        ) from exc

    # 12. Validar o documento FINAL com mlcroissant.

    try:
        validated_dataset = mlc.Dataset(
            jsonld=str(output_path),
        )

        # Forçar a leitura dos metadados.
        validated_dataset.metadata.to_json()

    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                "O documento final não passou na validação mlcroissant: "
                f"{exc}"
            ),
        ) from exc

    return croissant
