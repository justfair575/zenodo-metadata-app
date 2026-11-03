"""Serviços OAuth para autenticar criadores através da ORCID.

Esta primeira implementação destina-se ao desenvolvimento local com FastAPI
num único processo. O estado OAuth e os tokens ficam apenas em memória.
Para produção/múltiplos workers, devem ser substituídos por armazenamento
partilhado e persistente, associado a uma sessão de utilizador.
"""

from __future__ import annotations

import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

from app.metadata_schema import is_valid_orcid, normalize_orcid


# ============================================================
# CONFIGURAÇÃO
# ============================================================

ORCID_CLIENT_ID = os.getenv("ORCID_CLIENT_ID", "").strip()
ORCID_CLIENT_SECRET = os.getenv("ORCID_CLIENT_SECRET", "").strip()

ORCID_API_BASE_URL = os.getenv(
    "ORCID_API_BASE_URL",
    "https://sandbox.orcid.org",
).strip().rstrip("/")

ORCID_REDIRECT_URI = os.getenv("ORCID_REDIRECT_URI", "").strip()

ORCID_STATE_TTL_SECONDS = 600
ORCID_CREATOR_SESSION_TTL_SECONDS = 8 * 60 * 60

_ALLOWED_ORCID_BASE_URLS = {
    "https://sandbox.orcid.org",
    "https://orcid.org",
}

# state -> timestamp de expiração (Unix time).
_PENDING_ORCID_STATES: dict[str, float] = {}

# ORCID iD -> token OAuth. Nunca é devolvido ao frontend.
_AUTHENTICATED_ORCID_TOKENS: dict[str, dict[str, Any]] = {}

# Token opaco da aplicação -> identidade ORCID autenticada.
_AUTHENTICATED_CREATOR_SESSIONS: dict[str, dict[str, Any]] = {}


# ============================================================
# VALIDAR CONFIGURAÇÃO
# ============================================================

def _validate_configuration() -> None:
    """Valida a configuração antes de iniciar um fluxo OAuth."""

    missing = []

    if not ORCID_CLIENT_ID:
        missing.append("ORCID_CLIENT_ID")

    if not ORCID_CLIENT_SECRET:
        missing.append("ORCID_CLIENT_SECRET")

    if not ORCID_REDIRECT_URI:
        missing.append("ORCID_REDIRECT_URI")

    if missing:
        raise RuntimeError(
            "Configuração ORCID incompleta no .env: "
            + ", ".join(missing)
        )

    if ORCID_API_BASE_URL not in _ALLOWED_ORCID_BASE_URLS:
        raise RuntimeError(
            "ORCID_API_BASE_URL deve ser "
            "https://sandbox.orcid.org ou https://orcid.org."
        )

    parsed = urlsplit(ORCID_REDIRECT_URI)

    if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
    ):
        raise RuntimeError(
            "ORCID_REDIRECT_URI deve ser um URL HTTPS completo, "
            "sem credenciais, query string ou fragmento."
        )


# ============================================================
# GERAR URL DE AUTORIZAÇÃO
# ============================================================

def create_orcid_authorization_url() -> str:
    """Cria um state anti-CSRF e devolve o URL de autorização ORCID."""

    _validate_configuration()

    now = time.time()

    expired_states = [
        key
        for key, expires_at in _PENDING_ORCID_STATES.items()
        if expires_at <= now
    ]

    for key in expired_states:
        _PENDING_ORCID_STATES.pop(key, None)

    state = secrets.token_urlsafe(32)

    _PENDING_ORCID_STATES[state] = (
            now + ORCID_STATE_TTL_SECONDS
    )

    params = {
        "client_id": ORCID_CLIENT_ID,
        "response_type": "code",
        "scope": "/authenticate",
        "redirect_uri": ORCID_REDIRECT_URI,
        "state": state,
    }

    return (
        f"{ORCID_API_BASE_URL}/oauth/authorize?"
        f"{urlencode(params)}"
    )


# ============================================================
# VALIDAR STATE
# ============================================================

def consume_orcid_state(state: str) -> bool:
    """Consome o state uma única vez e confirma que não expirou."""

    expires_at = _PENDING_ORCID_STATES.pop(
        state,
        None,
    )

    return (
            expires_at is not None
            and expires_at > time.time()
    )


# ============================================================
# TROCAR CÓDIGO POR TOKEN
# ============================================================

async def exchange_orcid_authorization_code(
        *,
        code: str,
        state: str,
) -> dict[str, Any]:
    """Valida state e troca o código OAuth por identidade/token ORCID."""

    _validate_configuration()

    if not consume_orcid_state(state):
        raise ValueError(
            "O state ORCID é inválido, já foi utilizado ou expirou. "
            "Inicia novamente a autenticação."
        )

    token_url = (
        f"{ORCID_API_BASE_URL}/oauth/token"
    )

    payload = {
        "client_id": ORCID_CLIENT_ID,
        "client_secret": ORCID_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": ORCID_REDIRECT_URI,
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    20.0,
                    connect=5.0,
                ),
                follow_redirects=False,
        ) as client:

            response = await client.post(
                token_url,
                data=payload,
                headers=headers,
            )

            response.raise_for_status()

            token_data = response.json()

    except (httpx.HTTPError, ValueError) as exc:

        # Não expor corpo da resposta, credenciais ou detalhes do token.
        raise RuntimeError(
            "Falha na comunicação OAuth com a ORCID."
        ) from exc

    # ========================================================
    # VALIDAR ORCID ID
    # ========================================================

    raw_orcid = token_data.get("orcid")

    if (
            not isinstance(raw_orcid, str)
            or not raw_orcid.strip()
    ):
        raise RuntimeError(
            "A ORCID não devolveu um ORCID iD."
        )

    orcid_id = normalize_orcid(raw_orcid)

    if not is_valid_orcid(orcid_id):
        raise RuntimeError(
            "A ORCID devolveu um identificador inválido."
        )

    # ========================================================
    # VALIDAR ACCESS TOKEN
    # ========================================================

    access_token = token_data.get("access_token")

    if (
            not isinstance(access_token, str)
            or not access_token
    ):
        raise RuntimeError(
            "A ORCID não devolveu um access token válido."
        )

    # ========================================================
    # CALCULAR EXPIRAÇÃO
    # ========================================================

    expires_in = token_data.get("expires_in")

    try:
        expires_at = (
                time.time() + int(expires_in)
        )
    except (TypeError, ValueError):
        expires_at = None

    # ========================================================
    # GUARDAR TOKEN NO BACKEND
    # ========================================================

    _AUTHENTICATED_ORCID_TOKENS[orcid_id] = {
        "access_token": access_token,
        "token_type": token_data.get(
            "token_type",
            "bearer",
        ),
        "scope": token_data.get(
            "scope",
            "/authenticate",
        ),
        "expires_at": expires_at,
        "refresh_token": token_data.get(
            "refresh_token"
        ),
    }

    # ========================================================
    # OBTER NOME DEVOLVIDO PELA ORCID
    # ========================================================

    name = token_data.get("name")

    if not isinstance(name, str):
        name = None

    # ========================================================
    # CRIAR SESSÃO DA APLICAÇÃO
    # ========================================================

    creator_session_token = secrets.token_urlsafe(40)

    _cleanup_expired_creator_sessions()

    _AUTHENTICATED_CREATOR_SESSIONS[
        creator_session_token
    ] = {
        "creator": {
            "creator_type": "person",
            "name": name,
            "orcid_id": orcid_id,
        },
        "expires_at": (
                time.time()
                + ORCID_CREATOR_SESSION_TTL_SECONDS
        ),
    }

    return {
        "orcid": orcid_id,
        "name": name,
        "scope": token_data.get(
            "scope",
            "/authenticate",
        ),
        "creator_session_token": creator_session_token,
    }


# ============================================================
# LIMPAR SESSÕES EXPIRADAS
# ============================================================

def _cleanup_expired_creator_sessions() -> None:

    now = time.time()

    expired = [
        token
        for token, session
        in _AUTHENTICATED_CREATOR_SESSIONS.items()
        if session.get("expires_at", 0) <= now
    ]

    for token in expired:
        _AUTHENTICATED_CREATOR_SESSIONS.pop(
            token,
            None,
        )


# ============================================================
# OBTER IDENTIDADE AUTENTICADA
# ============================================================

def get_authenticated_creator_session(
        creator_session_token: str,
) -> dict[str, str] | None:
    """Devolve a identidade associada a uma sessão válida."""

    if (
            not isinstance(creator_session_token, str)
            or not creator_session_token
    ):
        return None

    _cleanup_expired_creator_sessions()

    session = _AUTHENTICATED_CREATOR_SESSIONS.get(
        creator_session_token
    )

    if not session:
        return None

    creator = session.get("creator")

    if not isinstance(creator, dict):
        return None

    return {
        "creator_type": "person",
        "name": str(
            creator.get("name") or ""
        ).strip(),
        "orcid_id": normalize_orcid(
            str(creator.get("orcid_id") or "")
        ),
    }


# ============================================================
# OBTER TOKEN ORCID
# ============================================================

def get_authenticated_orcid_token(
        orcid_id: str,
) -> dict[str, Any] | None:
    """Obtém token em memória para utilização interna futura."""

    normalized = normalize_orcid(orcid_id)

    if not is_valid_orcid(normalized):
        return None

    return _AUTHENTICATED_ORCID_TOKENS.get(
        normalized
    )