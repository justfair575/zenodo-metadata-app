
from copy import deepcopy

from fastapi import HTTPException

from app.metadata_schema import (
    ConfirmMetadataRequest,
    ConfirmedMetadataResponse,
    MetadataField,
)


# Política atual da aplicação, mantida do metadata_extractor.py.
REQUIRED_FIELDS = [
    "title",
    "description",
    "creators",
    "license",
    "dataset_type",
    "data_modality",
]


def is_empty(value):
    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    if isinstance(value, (list, dict)):
        return len(value) == 0

    return False


def apply_metadata_reviews(
        request: ConfirmMetadataRequest,
) -> ConfirmedMetadataResponse:

    metadata = deepcopy(request.metadata)

    for field_name, review in request.reviews.items():

        field = getattr(metadata, field_name)

        # Nesta versão, os campos revistos individualmente
        # são MetadataField.
        if not isinstance(field, MetadataField):
            raise HTTPException(
                status_code=422,
                detail=f"Campo não suportado para revisão: {field_name}",
            )

        if review.action == "accept":

            if is_empty(field.suggested_value):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Não existe sugestão para aceitar "
                        f"no campo '{field_name}'."
                    ),
                )

            field.value = field.suggested_value
            field.status = "confirmed"

        elif review.action == "edit":

            if is_empty(review.value):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"O campo '{field_name}' não pode "
                        "ser confirmado com um valor vazio."
                    ),
                )

            field.value = review.value
            field.status = "confirmed"

        elif review.action == "reject":

            field.value = None
            field.status = "rejected"

    pending_fields = []
    rejected_fields = []

    for field_name in REQUIRED_FIELDS:

        field = getattr(metadata, field_name)

        if field.status == "rejected":
            rejected_fields.append(field_name)

        if (
                field.status != "confirmed"
                or is_empty(field.value)
        ):
            pending_fields.append(field_name)

    metadata.missing_information = pending_fields.copy()

    can_generate = len(pending_fields) == 0

    return ConfirmedMetadataResponse(
        metadata=metadata,
        confirmed=can_generate,
        pending_fields=pending_fields,
        rejected_fields=rejected_fields,
        can_generate_croissant=can_generate,
    )
