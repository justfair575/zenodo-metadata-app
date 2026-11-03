from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)


ReviewStatus = Literal[
    "suggested",
    "confirmed",
    "rejected",
]

CreatorType = Literal[
    "person",
    "organization",
]


# ============================================================
# ORCID
# ============================================================

def normalize_orcid(value: str) -> str:
    """Normaliza um ORCID para XXXX-XXXX-XXXX-XXXX."""

    value = value.strip()

    value = re.sub(
        r"^https?://orcid\.org/",
        "",
        value,
        flags=re.IGNORECASE,
    )

    return value.upper()


def is_valid_orcid(value: str) -> bool:
    """Valida o formato e o checksum MOD 11-2 de um ORCID."""

    orcid = normalize_orcid(value)

    if not re.fullmatch(
            r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]",
            orcid,
    ):
        return False

    digits = orcid.replace("-", "")

    total = 0

    for character in digits[:15]:
        total = (
                        total + int(character)
                ) * 2

    result = (12 - (total % 11)) % 11

    check_digit = (
        "X"
        if result == 10
        else str(result)
    )

    return digits[-1] == check_digit


# ============================================================
# ROR
# ============================================================

def normalize_ror(value: str) -> str:
    """Normaliza um ROR para URL canónica."""

    value = value.strip()

    value = re.sub(
        r"^https?://ror\.org/",
        "",
        value,
        flags=re.IGNORECASE,
    )

    return f"https://ror.org/{value}"


def is_valid_ror_format(value: str) -> bool:
    """Valida o formato de um ROR ID.

    Não confirma a existência do identificador no registo ROR.
    """

    ror_id = value.strip()

    ror_id = re.sub(
        r"^https?://ror\.org/",
        "",
        ror_id,
        flags=re.IGNORECASE,
    )

    return bool(
        re.fullmatch(
            r"0[a-z0-9]{6}[0-9]{2}",
            ror_id,
            re.IGNORECASE,
        )
    )


# ============================================================
# METADATA FIELD
# ============================================================

class MetadataField(BaseModel):

    suggested_value: Any = None

    value: Any = None

    source: str | None = None

    evidence: str | None = None

    confidence: float = Field(
        default=0,
        ge=0,
        le=1,
    )

    status: ReviewStatus = "suggested"

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_value(cls, data):
        """Aceita estruturas antigas e valores simples."""

        if isinstance(data, dict):
            return data

        return {
            "value": data,
            "suggested_value": data,
            "status": "suggested",
        }


# ============================================================
# CREATOR IDENTITY
# ============================================================

class CreatorIdentity(BaseModel):
    """Identidade estruturada de um criador."""

    creator_type: CreatorType | None = None

    name: str

    orcid_id: str | None = None

    ror_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_creator(cls, data):

        if isinstance(data, str):
            return {
                "name": data.strip(),
            }

        return data

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:

        value = value.strip()

        if not value:
            raise ValueError(
                "O nome do criador não pode estar vazio."
            )

        return value

    @field_validator("orcid_id")
    @classmethod
    def validate_orcid_format(
            cls,
            value: str | None,
    ) -> str | None:

        if value is None or not value.strip():
            return None

        normalized = normalize_orcid(value)

        if not is_valid_orcid(normalized):
            raise ValueError(
                "O ORCID iD tem formato ou checksum inválido."
            )

        return normalized

    @field_validator("ror_id")
    @classmethod
    def validate_ror_format(
            cls,
            value: str | None,
    ) -> str | None:

        if value is None or not value.strip():
            return None

        normalized = normalize_ror(value)

        if not is_valid_ror_format(normalized):
            raise ValueError(
                "O ROR ID tem formato inválido."
            )

        return normalized

    @model_validator(mode="after")
    def validate_identifier_matches_type(self):

        if self.orcid_id and self.ror_id:
            raise ValueError(
                "Um criador não pode ter ORCID e ROR simultaneamente."
            )

        if (
                self.creator_type == "person"
                and self.ror_id
        ):
            raise ValueError(
                "Uma pessoa deve ser identificada por ORCID, não ROR."
            )

        if (
                self.creator_type == "organization"
                and self.orcid_id
        ):
            raise ValueError(
                "Uma organização deve ser identificada por ROR, não ORCID."
            )

        return self


# ============================================================
# EXTRACTED METADATA
# ============================================================

class ExtractedMetadata(BaseModel):

    title: MetadataField = Field(
        default_factory=MetadataField
    )

    description: MetadataField = Field(
        default_factory=MetadataField
    )

    creators: MetadataField = Field(
        default_factory=MetadataField
    )

    license: MetadataField = Field(
        default_factory=MetadataField
    )

    date_published: MetadataField = Field(
        default_factory=MetadataField
    )

    keywords: MetadataField = Field(
        default_factory=MetadataField
    )

    dataset_type: MetadataField = Field(
        default_factory=MetadataField
    )

    machine_learning_task: MetadataField = Field(
        default_factory=MetadataField
    )

    data_modality: MetadataField = Field(
        default_factory=MetadataField
    )

    language: MetadataField = Field(
        default_factory=MetadataField
    )

    number_of_records: MetadataField = Field(
        default_factory=MetadataField
    )

    splits: dict[str, Any] = Field(
        default_factory=dict
    )

    additional_information: list[MetadataField] = Field(
        default_factory=list
    )

    missing_information: list[str] = Field(
        default_factory=list
    )

    @field_validator(
        "creators",
        mode="before",
    )
    @classmethod
    def normalize_creator_collection(cls, data):

        # Compatibilidade com respostas antigas do Ollama.
        if isinstance(data, dict):

            normalized = dict(data)

            for key in (
                    "value",
                    "suggested_value",
            ):

                if isinstance(
                        normalized.get(key),
                        str,
                ):

                    normalized[key] = [
                        normalized[key]
                    ]

            return normalized

        if isinstance(data, str):

            return {
                "value": [data],
                "suggested_value": [data],
                "status": "suggested",
            }

        return data

    @field_validator(
        "creators",
        mode="after",
    )
    @classmethod
    def parse_creator_identities(
            cls,
            field: MetadataField,
    ) -> MetadataField:

        for attribute in (
                "value",
                "suggested_value",
        ):

            raw_creators = getattr(
                field,
                attribute,
            )

            if raw_creators is None:
                continue

            if not isinstance(
                    raw_creators,
                    list,
            ):
                raise ValueError(
                    "Os criadores têm de ser apresentados numa lista."
                )

            parsed_creators = [
                creator
                if isinstance(
                    creator,
                    CreatorIdentity,
                )
                else CreatorIdentity.model_validate(
                    creator
                )
                for creator in raw_creators
            ]

            setattr(
                field,
                attribute,
                parsed_creators,
            )

        return field

    @model_validator(mode="after")
    def require_identifiers_for_confirmed_creators(self):

        creators_field = self.creators

        if creators_field.status != "confirmed":
            return self

        creators = creators_field.value

        if (
                not isinstance(creators, list)
                or not creators
        ):
            raise ValueError(
                "É necessário indicar pelo menos um criador."
            )

        for index, creator in enumerate(
                creators,
                start=1,
        ):

            if not isinstance(
                    creator,
                    CreatorIdentity,
            ):
                raise ValueError(
                    f"O criador {index} tem uma estrutura inválida."
                )

            if creator.creator_type == "person":

                if not creator.orcid_id:
                    raise ValueError(
                        f"O criador {index} é uma pessoa "
                        "e necessita de ORCID."
                    )

            elif creator.creator_type == "organization":

                if not creator.ror_id:
                    raise ValueError(
                        f"O criador {index} é uma organização "
                        "e necessita de ROR."
                    )

            else:
                raise ValueError(
                    f"É necessário indicar se o criador {index} "
                    "é pessoa ou organização."
                )

        return self


# ============================================================
# FIELD REVIEW
# ============================================================

class FieldReview(BaseModel):

    action: Literal[
        "accept",
        "edit",
        "reject",
    ]

    value: Any = None


# ============================================================
# CONFIRM METADATA REQUEST
# ============================================================

class ConfirmMetadataRequest(BaseModel):

    metadata: ExtractedMetadata

    reviews: dict[str, FieldReview]

    # Token opaco emitido pelo backend após autenticação ORCID.
    # Nunca deve conter o access token OAuth da ORCID.
    orcid_session_token: str | None = Field(
        default=None,
        min_length=20,
        max_length=256,
    )

    @model_validator(mode="after")
    def validate_review_fields(self):

        allowed_fields = set(
            ExtractedMetadata.model_fields
        )

        invalid = (
                set(self.reviews)
                - allowed_fields
        )

        if invalid:
            raise ValueError(
                f"Campos de revisão inválidos: {sorted(invalid)}"
            )

        return self


# ============================================================
# CONFIRMED METADATA RESPONSE
# ============================================================

class ConfirmedMetadataResponse(BaseModel):

    metadata: ExtractedMetadata

    confirmed: bool

    pending_fields: list[str]

    rejected_fields: list[str]

    can_generate_croissant: bool