
from pathlib import Path

from app.ollama_service import extract_with_ollama
from app.metadata_schema import ExtractedMetadata, MetadataField


REQUIRED_FIELDS = [
    "title",
    "description",
    "creators",
    "license",
    "dataset_type",
    "data_modality",
]


FIELD_NAMES = [
    "title",
    "description",
    "creators",
    "license",
    "keywords",
    "dataset_type",
    "machine_learning_task",
    "data_modality",
    "language",
    "number_of_records",
]


def has_value(value):
    """Verifica se um valor está efetivamente preenchido."""
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, (list, dict)):
        return len(value) > 0

    return True


def normalize_field(field):
    """
    Normaliza os campos recebidos do Ollama.

    Campos sem valor não podem manter fontes, evidências
    ou confiança que sugiram que existe informação válida.

    Todas as sugestões permanecem pendentes de confirmação.
    """
    if field is None:
        return MetadataField()

    if not isinstance(field, MetadataField):
        field = MetadataField.model_validate(field)

    # Compatibilidade com respostas antigas do Ollama.
    if field.suggested_value is None and field.value is not None:
        field.suggested_value = field.value

    if field.value is None and field.suggested_value is not None:
        field.value = field.suggested_value

    # Determina o valor efetivamente sugerido.
    effective_value = field.suggested_value

    if effective_value is None:
        effective_value = field.value

    # Sem valor, não pode existir evidência associada.
    if not has_value(effective_value):
        field.suggested_value = None
        field.value = None
        field.source = None
        field.evidence = None
        field.confidence = 0

    field.status = "suggested"

    return field


def field_has_value(field):
    """Verifica se um campo contém uma sugestão utilizável."""
    if field is None:
        return False

    value = field.suggested_value

    if value is None:
        value = field.value

    return has_value(value)


def set_deterministic_suggestion(
        field: MetadataField,
        value,
        source: str,
        evidence: str,
        confidence: float,
):
    """
    Define uma sugestão baseada em informação técnica
    diretamente disponível no backend.

    Nunca confirma automaticamente o campo.
    """
    field.suggested_value = value
    field.value = value
    field.source = source
    field.evidence = evidence
    field.confidence = confidence
    field.status = "suggested"


def generate_title_from_filename(dataset_path: str) -> str | None:
    """
    Converte o nome do ficheiro num título legível.

    Exemplo:
    iris.csv -> Iris dataset
    """
    if not dataset_path:
        return None

    filename = Path(dataset_path).name
    stem = Path(filename).stem

    if not stem:
        return None

    words = stem.replace("_", " ").replace("-", " ")
    words = " ".join(words.split())

    if not words:
        return None

    title = words.title()

    if "dataset" not in title.lower():
        title = f"{title} dataset"

    return title


def apply_deterministic_metadata(
        metadata: ExtractedMetadata,
        dataset_inspection: dict | None,
):
    """
    Preenche informações técnicas que podem ser obtidas
    diretamente da inspeção do dataset.
    """
    if not dataset_inspection:
        return metadata

    dataset_path = dataset_inspection.get("path", "")

    dataset_format = (
            dataset_inspection.get("format")
            or Path(dataset_path).suffix
    ).lower()

    columns = dataset_inspection.get("columns", [])

    # 1. TITLE
    if not field_has_value(metadata.title):
        title = generate_title_from_filename(dataset_path)

        if title:
            set_deterministic_suggestion(
                field=metadata.title,
                value=title,
                source="filename",
                evidence=dataset_path,
                confidence=0.8,
            )

    # 2. DATASET TYPE E DATA MODALITY
    if dataset_format in [".csv", ".tsv"] and columns:

        set_deterministic_suggestion(
            field=metadata.dataset_type,
            value="Tabular dataset",
            source="selected_dataset_inspection",
            evidence=(
                f"Formato {dataset_format} com "
                f"{len(columns)} colunas inspecionadas."
            ),
            confidence=1.0,
        )

        set_deterministic_suggestion(
            field=metadata.data_modality,
            value="Tabular",
            source="selected_dataset_inspection",
            evidence=(
                f"Formato {dataset_format} com "
                f"{len(columns)} colunas inspecionadas."
            ),
            confidence=1.0,
        )

    # 3. NUMBER OF RECORDS
    number_of_records = dataset_inspection.get(
        "number_of_records"
    )

    if number_of_records is not None:
        set_deterministic_suggestion(
            field=metadata.number_of_records,
            value=number_of_records,
            source="selected_dataset_inspection",
            evidence=f"number_of_records: {number_of_records}",
            confidence=1.0,
        )

    return metadata


async def extract_repository_metadata(
        repository_data: dict,
        dataset_inspection: dict | None = None,
) -> ExtractedMetadata:

    extraction_data = dict(repository_data)

    if dataset_inspection:
        extraction_data["dataset_inspection"] = dataset_inspection

    # 1. Extração através do Ollama.
    metadata = await extract_with_ollama(extraction_data)

    # 2. Normalização de todos os campos.
    for field_name in FIELD_NAMES:
        field = getattr(metadata, field_name)

        setattr(
            metadata,
            field_name,
            normalize_field(field),
        )

    metadata.additional_information = [
        normalize_field(item)
        for item in metadata.additional_information
    ]

    # 3. Complemento com informação técnica verificável.
    metadata = apply_deterministic_metadata(
        metadata,
        dataset_inspection,
    )

    # 4. Identificação dos campos obrigatórios em falta.
    missing = set()

    for field_name in REQUIRED_FIELDS:
        field = getattr(metadata, field_name)

        if not field_has_value(field):
            missing.add(field_name)

    metadata.missing_information = sorted(missing)

    return metadata
