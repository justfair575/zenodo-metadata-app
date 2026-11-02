import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse


KNOWN_SPDX_LICENSES = {
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "BSD-3-Clause-Clear",
    "ISC",
    "MPL-2.0",
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "LGPL-2.1-only",
    "LGPL-2.1-or-later",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
    "AGPL-3.0-only",
    "AGPL-3.0-or-later",
    "CC0-1.0",
    "CC-BY-4.0",
    "CC-BY-SA-4.0",
    "CC-BY-NC-4.0",
    "CC-BY-NC-SA-4.0",
    "Unlicense",
    "Zlib",
    "EPL-2.0",
}

ALLOWED_LICENSE_HOSTS = {
    "opensource.org",
    "www.opensource.org",
    "spdx.org",
    "www.gnu.org",
    "apache.org",
    "www.apache.org",
    "creativecommons.org",
    "www.creativecommons.org",
}

DATASET_TYPES = {
    "tabular dataset",
    "image dataset",
    "audio dataset",
    "text dataset",
    "video dataset",
    "time series dataset",
    "geospatial dataset",
    "multimodal dataset",
    "graph dataset",
    "document dataset",
    "other",
}

DATA_MODALITIES = {
    "tabular",
    "image",
    "audio",
    "text",
    "video",
    "time series",
    "geospatial",
    "multimodal",
    "graph",
    "document",
}

KNOWN_LANGUAGES = {
    "ar", "bg", "bn", "ca", "cs", "da", "de", "el",
    "en", "es", "et", "eu", "fa", "fi", "fr", "ga",
    "gl", "he", "hi", "hr", "hu", "id", "is", "it",
    "ja", "ko", "lt", "lv", "ms", "mt", "nl", "no",
    "pl", "pt", "ro", "ru", "sk", "sl", "sq", "sr",
    "sv", "th", "tr", "uk", "ur", "vi", "zh",
}


def is_empty(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    if isinstance(value, (list, dict)):
        return len(value) == 0

    return False


def validate_text(
        value: Any,
        field_name: str,
        minimum: int = 1,
        maximum: int = 5000,
) -> list[str]:
    errors = []

    if not isinstance(value, str):
        return [f"{field_name}: tem de ser texto."]

    value = value.strip()

    if len(value) < minimum:
        errors.append(
            f"{field_name}: tem de conter pelo menos {minimum} caracteres."
        )

    if len(value) > maximum:
        errors.append(
            f"{field_name}: não pode ultrapassar {maximum} caracteres."
        )

    if any(
            ord(char) < 32 and char not in "\n\t\r"
            for char in value
    ):
        errors.append(
            f"{field_name}: contém caracteres de controlo inválidos."
        )

    return errors


def validate_creators(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]

    if not isinstance(value, list) or not value:
        return ["Indica pelo menos um criador."]

    if len(value) > 50:
        return ["Não podes indicar mais de 50 criadores."]

    errors = []

    for index, creator in enumerate(value, start=1):
        if isinstance(creator, str):
            name = creator.strip()

        elif isinstance(creator, dict):
            name = creator.get("name")

            if not isinstance(name, str):
                errors.append(
                    f"Criador {index}: o campo 'name' tem de ser texto."
                )
                continue

            name = name.strip()

        else:
            errors.append(
                f"Criador {index}: formato inválido."
            )
            continue

        if not name:
            errors.append(
                f"Criador {index}: o nome não pode estar vazio."
            )
        elif len(name) > 200:
            errors.append(
                f"Criador {index}: o nome não pode ultrapassar 200 caracteres."
            )

    return errors


def validate_keywords(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]

    if not isinstance(value, list):
        return ["As palavras-chave têm de ser texto ou uma lista de textos."]

    if len(value) > 100:
        return ["Não podes indicar mais de 100 palavras-chave."]

    errors = []

    for index, keyword in enumerate(value, start=1):
        if not isinstance(keyword, str):
            errors.append(
                f"Palavra-chave {index}: tem de ser texto."
            )
            continue

        if not keyword.strip():
            errors.append(
                f"Palavra-chave {index}: não pode estar vazia."
            )
        elif len(keyword.strip()) > 100:
            errors.append(
                f"Palavra-chave {index}: não pode ultrapassar 100 caracteres."
            )

    return errors


def validate_license(value: Any) -> list[str]:
    if not isinstance(value, str):
        return ["A licença tem de ser um identificador SPDX ou um URL."]

    value = value.strip()

    if value in KNOWN_SPDX_LICENSES:
        return []

    parsed = urlparse(value)

    if (
            parsed.scheme == "https"
            and parsed.hostname in ALLOWED_LICENSE_HOSTS
            and parsed.path not in ("", "/")
            and not parsed.username
            and not parsed.password
    ):
        return []

    return [
        "Licença não reconhecida. Utiliza um identificador SPDX "
        "suportado, como MIT ou Apache-2.0, ou um URL HTTPS "
        "de uma entidade de licenciamento reconhecida."
    ]


def validate_language(value: Any) -> list[str]:
    if isinstance(value, str):
        languages = [value]
    elif isinstance(value, list):
        languages = value
    else:
        return ["O idioma tem de ser um código ou uma lista de códigos."]

    if not languages:
        return ["Indica pelo menos um idioma."]

    errors = []

    for language in languages:
        if not isinstance(language, str):
            errors.append("Cada idioma tem de ser texto.")
            continue

        language = language.strip()

        if not re.fullmatch(
                r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*",
                language,
        ):
            errors.append(
                f"'{language}' não tem um formato de idioma válido."
            )
            continue

        primary_language = language.split("-")[0].lower()

        if primary_language not in KNOWN_LANGUAGES:
            errors.append(
                f"'{language}' utiliza um código de idioma não reconhecido."
            )

    return errors


def validate_number_of_records(value: Any) -> list[str]:
    if isinstance(value, bool):
        return ["O número de registos tem de ser um número inteiro."]

    if not isinstance(value, int):
        return ["O número de registos tem de ser um número inteiro."]

    if value < 0:
        return ["O número de registos não pode ser negativo."]

    return []


def validate_date_published(value: Any) -> list[str]:
    if not isinstance(value, str):
        return [
            "A data de publicação tem de ser texto no formato ISO 8601."
        ]

    value = value.strip()

    if not value:
        return ["A data de publicação é obrigatória."]

    try:
        # Datas sem hora: YYYY-MM-DD
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            parsed_date = date.fromisoformat(value)

            if parsed_date > date.today():
                return [
                    "A data de publicação não pode ser posterior à data de hoje."
                ]

            return []

        # Datas com hora: timestamp ISO 8601.
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed_datetime = datetime.fromisoformat(normalized)

        # Com fuso horário, comparar usando o mesmo fuso.
        # Sem fuso horário, comparar com a hora local do servidor.
        if parsed_datetime.tzinfo is not None:
            current_datetime = datetime.now(parsed_datetime.tzinfo)
        else:
            current_datetime = datetime.now()

        if parsed_datetime > current_datetime:
            return [
                "A data de publicação não pode estar no futuro."
            ]

    except ValueError:
        return [
            "Data de publicação inválida. Utiliza YYYY-MM-DD "
            "ou um timestamp ISO 8601."
        ]

    return []


def validate_enum(
        value: Any,
        allowed_values: set[str],
        field_name: str,
) -> list[str]:
    if not isinstance(value, str):
        return [f"{field_name}: tem de ser texto."]

    if value.strip().lower() not in allowed_values:
        options = ", ".join(sorted(allowed_values))

        return [
            f"{field_name}: valor não reconhecido. "
            f"Valores aceites: {options}."
        ]

    return []


def validate_metadata_field(
        field_name: str,
        value: Any,
) -> list[str]:

    if field_name == "title":
        return validate_text(value, "Título", 3, 200)

    if field_name == "description":
        return validate_text(value, "Descrição", 10, 5000)

    if field_name == "creators":
        return validate_creators(value)

    if field_name == "license":
        return validate_license(value)

    if field_name == "date_published":
        return validate_date_published(value)

    if field_name == "keywords":
        return validate_keywords(value)

    if field_name == "dataset_type":
        return validate_enum(
            value,
            DATASET_TYPES,
            "Tipo de dataset",
        )

    if field_name == "data_modality":
        return validate_enum(
            value,
            DATA_MODALITIES,
            "Modalidade dos dados",
        )

    if field_name == "language":
        return validate_language(value)

    if field_name == "number_of_records":
        return validate_number_of_records(value)

    if field_name == "machine_learning_task":
        return validate_text(
            value,
            "Tarefa de machine learning",
            2,
            200,
        )

    return []
