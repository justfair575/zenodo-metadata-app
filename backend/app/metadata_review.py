
from copy import deepcopy

from fastapi import HTTPException

from app.metadata_schema import (
    ConfirmMetadataRequest,
    ConfirmedMetadataResponse,
    MetadataField,
)

from app.metadata_validation import (
    is_empty,
    validate_metadata_field,
)


REQUIRED_FIELDS = [
    "title",
    "description",
    "creators",
    "license",
    "date_published",
    "dataset_type",
    "data_modality",
]


def apply_metadata_reviews(
        request: ConfirmMetadataRequest,
) -> ConfirmedMetadataResponse:

    metadata = deepcopy(request.metadata)

    for field_name, review in request.reviews.items():

        field = getattr(metadata, field_name)

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

            value_to_validate = field.suggested_value

        elif review.action == "edit":

            if is_empty(review.value):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"O campo '{field_name}' não pode "
                        "ser confirmado com um valor vazio."
                    ),
                )

            value_to_validate = review.value

        elif review.action == "reject":

            field.value = None
            field.status = "rejected"
            continue

        else:
            raise HTTPException(
                status_code=422,
                detail=f"Ação de revisão inválida: {review.action}",
            )

        validation_errors = validate_metadata_field(
            field_name,
            value_to_validate,
        )

        if validation_errors:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": (
                        f"O valor introduzido no campo "
                        f"'{field_name}' não é válido."
                    ),
                    "field": field_name,
                    "errors": validation_errors,
                },
            )

        field.value = value_to_validate
        field.status = "confirmed"

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
