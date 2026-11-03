
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


ReviewStatus = Literal["suggested", "confirmed", "rejected"]


class MetadataField(BaseModel):
    suggested_value: Any = None
    value: Any = None

    source: str | None = None
    evidence: str | None = None

    confidence: float = Field(default=0, ge=0, le=1)
    status: ReviewStatus = "suggested"

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_value(cls, data):
        """
        Permite receber respostas antigas do Ollama:
        {"value": "...", "source": "...", ...}
        ou valores simples, incluindo listas.
        """
        if isinstance(data, dict):
            return data

        return {
            "value": data,
            "suggested_value": data,
            "status": "suggested",
        }


class ExtractedMetadata(BaseModel):
    title: MetadataField = Field(default_factory=MetadataField)
    description: MetadataField = Field(default_factory=MetadataField)
    creators: MetadataField = Field(default_factory=MetadataField)
    license: MetadataField = Field(default_factory=MetadataField)

    date_published: MetadataField = Field(default_factory=MetadataField)

    keywords: MetadataField = Field(default_factory=MetadataField)

    dataset_type: MetadataField = Field(default_factory=MetadataField)
    machine_learning_task: MetadataField = Field(
        default_factory=MetadataField
    )
    data_modality: MetadataField = Field(default_factory=MetadataField)
    language: MetadataField = Field(default_factory=MetadataField)
    number_of_records: MetadataField = Field(
        default_factory=MetadataField
    )

    splits: dict[str, Any] = Field(default_factory=dict)

    additional_information: list[MetadataField] = Field(
        default_factory=list
    )

    missing_information: list[str] = Field(default_factory=list)


class FieldReview(BaseModel):
    action: Literal["accept", "edit", "reject"]
    value: Any = None


class ConfirmMetadataRequest(BaseModel):
    metadata: ExtractedMetadata
    reviews: dict[str, FieldReview]

    @model_validator(mode="after")
    def validate_review_fields(self):
        allowed_fields = set(ExtractedMetadata.model_fields)

        invalid = set(self.reviews) - allowed_fields

        if invalid:
            raise ValueError(
                f"Campos de revisão inválidos: {sorted(invalid)}"
            )

        return self


class ConfirmedMetadataResponse(BaseModel):
    metadata: ExtractedMetadata
    confirmed: bool
    pending_fields: list[str]
    rejected_fields: list[str]
    can_generate_croissant: bool
