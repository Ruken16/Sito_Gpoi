from __future__ import annotations

import asyncio
import json
import os
import re
import zipfile
import io
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any, Awaitable
from urllib.parse import urljoin, urlparse

import classeviva
import requests
from classeviva.collegamenti.collegamenti import Collegamenti
from classeviva.variabili.variabili import intestazione as base_headers
from dotenv import load_dotenv


@dataclass
class RuntimeConfig:
    username: str | None
    password: str | None
    debug: bool = False


@dataclass
class DownloadedFile:
    content: bytes
    filename: str | None = None
    content_type: str | None = None


class ClasseVivaProbeError(RuntimeError):
    pass


class MissingCredentialsError(ClasseVivaProbeError):
    pass


PROBE_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("get", "carta"),
    ("get", "periodi"),
    ("get", "materie"),
    ("get", "bacheca"),
    ("post", "documenti"),
)

SECTION_METHODS: dict[str, tuple[str, tuple[str, ...]]] = {
    "documenti": ("documenti", ()),
    "assenze": ("assenze", ()),
    "voti": ("voti", ()),
    "note": ("note", ()),
    "agenda": ("agenda", ()),
    "bacheca": ("bacheca", ()),
    "calendario": ("calendario", ()),
    "carta": ("carta", ()),
    "didattica": ("didattica", ()),
    "libri": ("libri", ()),
    "materie": ("materie", ()),
    "periodi": ("periodi", ()),
    "lezioni_giorno": ("lezioni_giorno", ("day",)),
    "assenze_da_a": ("assenze_da_a", ("start", "end")),
    "agenda_da_a": ("agenda_da_a", ("start", "end")),
    "calendario_da_a": ("calendario_da_a", ("start", "end")),
    "lezioni_da_a": ("lezioni_da_a", ("start", "end")),
    "panoramica_da_a": ("panoramica_da_a", ("start", "end")),
}


def package_version() -> str:
    try:
        return version("Classeviva.py")
    except Exception:
        try:
            return version("classeviva-py")
        except Exception:
            return "unknown"


def json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def load_config(*, dotenv_path: str | os.PathLike[str] | None = None, username: str | None = None, password: str | None = None, debug: bool = False) -> RuntimeConfig:
    load_dotenv(dotenv_path=dotenv_path)
    return RuntimeConfig(
        username=username or os.getenv("CV_USERNAME"),
        password=password or os.getenv("CV_PASSWORD"),
        debug=debug,
    )


def save_env_file(username: str, password: str, *, dotenv_path: str | os.PathLike[str] = ".env") -> Path:
    path = Path(dotenv_path)
    existing: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            existing[key.strip()] = value
    existing["CV_USERNAME"] = username
    existing["CV_PASSWORD"] = password
    content = "\n".join(f"{key}={value}" for key, value in existing.items()) + "\n"
    path.write_text(content, encoding="utf-8")
    return path


def require_credentials(cfg: RuntimeConfig) -> tuple[str, str]:
    if not cfg.username or not cfg.password:
        raise MissingCredentialsError(
            "Credenziali mancanti. Inserisci username e password oppure compila il file .env con CV_USERNAME e CV_PASSWORD."
        )
    return cfg.username, cfg.password


async def login(cfg: RuntimeConfig) -> classeviva.Utente:
    username, password = require_credentials(cfg)
    user = classeviva.Utente(username, password)
    await user.accedi()
    await ensure_student_id(user)
    return user


def _auth_headers(user: classeviva.Utente, *, include_content_type: bool = True) -> dict[str, str]:
    headers = base_headers.copy()
    if not include_content_type:
        headers.pop("content-type", None)
    headers["Z-Auth-Token"] = user.token
    return headers


def _allowed_resource_url(url: str) -> str:
    normalized = urljoin("https://web.spaggiari.eu", url)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise ClasseVivaProbeError("URL risorsa non valido.")
    if parsed.netloc and not parsed.netloc.endswith("spaggiari.eu"):
        raise ClasseVivaProbeError("Sono consentite solo risorse provenienti da spaggiari.eu.")
    return normalized


def _filename_from_response(response: requests.Response, fallback: str | None = None) -> str | None:
    content_disposition = response.headers.get("Content-Disposition", "")
    for token in content_disposition.split(";"):
        part = token.strip()
        if part.lower().startswith("filename="):
            return part.split("=", 1)[1].strip("\"'")
        if part.lower().startswith("filename*="):
            encoded = part.split("=", 1)[1]
            if "''" in encoded:
                return encoded.split("''", 1)[1].strip("\"'")
    return fallback


def _file_from_response(response: requests.Response, fallback: str | None = None) -> DownloadedFile:
    content_type = response.headers.get("Content-Type")
    inferred_type = _infer_content_type(response.content, fallback=fallback)
    if (
        not content_type
        or content_type in {"application/octet-stream", "binary/octet-stream"}
        or inferred_type == "application/pdf"
        or (inferred_type.startswith("image/") and not str(content_type).startswith("image/"))
    ):
        content_type = inferred_type
    return DownloadedFile(
        content=response.content,
        filename=_filename_from_response(response, fallback),
        content_type=content_type,
    )


def _raise_for_unsuccessful_response(response: requests.Response) -> None:
    try:
        body: Any = response.json()
    except Exception:
        body = response.text
    raise ClasseVivaProbeError(f"Richiesta fallita con HTTP {response.status_code}: {body}")


def _infer_content_type(content: bytes, *, fallback: str | None = None) -> str:
    lowered_name = (fallback or "").lower()
    if content.startswith(b"%PDF-") or lowered_name.endswith(".pdf"):
        return "application/pdf"
    if content.startswith((b"<!doctype html", b"<html", b"<!DOCTYPE html")) or lowered_name.endswith((".html", ".htm")):
        return "text/html; charset=utf-8"
    if content.startswith(b"\x89PNG\r\n\x1a\n") or lowered_name.endswith(".png"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff") or lowered_name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a") or lowered_name.endswith(".gif"):
        return "image/gif"
    if content.startswith(b"{") or content.startswith(b"[") or lowered_name.endswith(".json"):
        return "application/json; charset=utf-8"
    if content.startswith(b"{\\rtf") or lowered_name.endswith(".rtf"):
        return "application/rtf"
    if content.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
        except Exception:
            names = set()
        if "word/document.xml" in names or lowered_name.endswith(".docx"):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if "xl/workbook.xml" in names or lowered_name.endswith(".xlsx"):
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if "ppt/presentation.xml" in names or lowered_name.endswith(".pptx"):
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        if lowered_name.endswith(".zip"):
            return "application/zip"
    if lowered_name.endswith(".txt"):
        return "text/plain; charset=utf-8"
    try:
        content[:4096].decode("utf-8")
        return "text/plain; charset=utf-8"
    except Exception:
        return "application/octet-stream"


def _looks_like_portal_page(response: requests.Response) -> bool:
    content_type = response.headers.get("Content-Type", "").lower()
    if "text/html" not in content_type and not response.content.lstrip().lower().startswith((b"<!doctype html", b"<html")):
        return False
    preview = response.text[:2000].lower()
    return any(token in preview for token in ("authapi4", "spaggiari", "login", "bacheca_personale"))


def _response_body_text(response: requests.Response) -> str:
    try:
        return json.dumps(response.json(), ensure_ascii=False)
    except Exception:
        return response.text


def _invalid_student_id_response(response: requests.Response) -> bool:
    return "invalid student-id" in _response_body_text(response).lower()


def _candidate_variants(raw: Any) -> list[str]:
    if raw in (None, "", [], {}):
        return []

    text = str(raw).strip()
    if not text or len(text) > 80:
        return []

    variants: list[str] = []

    def add(value: str) -> None:
        candidate = value.strip()
        if not candidate or candidate in variants:
            return
        if len(candidate) < 4 or len(candidate) > 24:
            return
        variants.append(candidate)

    digits_only = "".join(re.findall(r"\d+", text))
    if len(digits_only) >= 5:
        add(digits_only)

    stripped_prefix = re.sub(r"^[A-Za-z]+", "", text)
    stripped_bounds = re.sub(r"^\W+|\W+$", "", stripped_prefix)
    stripped_trailing = re.sub(r"[A-Za-z]+$", "", stripped_bounds)

    add(stripped_trailing)
    add(stripped_bounds)
    add(re.sub(r"^\D+|\D+$", "", text))
    add(text)
    return variants


def _iter_keyed_scalars(payload: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    items: list[tuple[tuple[str, ...], Any]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            items.extend(_iter_keyed_scalars(value, path + (str(key),)))
        return items
    if isinstance(payload, list):
        for value in payload:
            items.extend(_iter_keyed_scalars(value, path))
        return items
    return [(path, payload)]


def _candidate_student_ids(user: classeviva.Utente) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        for candidate in _candidate_variants(value):
            if candidate in seen:
                continue
            seen.add(candidate)
            candidates.append(candidate)

    add(getattr(user, "id", None))
    add(getattr(user, "_id", None))

    raw_data = getattr(user, "_dati", {})
    if isinstance(raw_data, dict):
        ident = raw_data.get("ident")
        add(ident)
        for path, value in _iter_keyed_scalars(raw_data):
            path_text = ".".join(path).lower()
            if any(token in path_text for token in ("student", "ident", ".id", "uid", "user_id", "studentid")) or path and path[-1].lower() in {"id", "uid", "ident"}:
                add(value)

    return candidates


def _endpoint_url(endpoint_name: str, student_id: str) -> str:
    endpoint = getattr(Collegamenti, endpoint_name)
    return endpoint.format(student_id)


def _probe_student_id(user: classeviva.Utente, student_id: str) -> str:
    headers = _auth_headers(user)
    for method_name, endpoint_name in PROBE_ENDPOINTS:
        response = getattr(user._sessione, method_name)(
            _endpoint_url(endpoint_name, student_id),
            headers=headers,
            timeout=20,
        )
        if response.status_code == 200:
            return "valid"
        if _invalid_student_id_response(response):
            return "invalid"
        if response.status_code in {401, 403}:
            _raise_for_unsuccessful_response(response)
    return "unknown"


async def ensure_student_id(user: classeviva.Utente) -> str:
    cached = getattr(user, "_cvprobe_resolved_student_id", None)
    if isinstance(cached, str) and cached:
        user._id = cached
        return cached

    original_id = getattr(user, "_id", "")
    fallback_candidate: str | None = None

    for candidate in _candidate_student_ids(user):
        verdict = _probe_student_id(user, candidate)
        if verdict == "valid":
            user._id = candidate
            user._cvprobe_resolved_student_id = candidate
            user._cvprobe_original_student_id = original_id
            return candidate
        if verdict == "unknown" and fallback_candidate is None:
            fallback_candidate = candidate

    resolved = fallback_candidate or original_id
    user._id = resolved
    user._cvprobe_resolved_student_id = resolved
    user._cvprobe_original_student_id = original_id
    return resolved


def _portal_session(user: classeviva.Utente) -> requests.Session:
    session = requests.Session()
    session.post(
        url="https://web.spaggiari.eu/auth-p7/app/default/AuthApi4.php?a=aLoginPwd",
        data={"cid": None, "uid": user._id, "pwd": user.password, "pin": None, "target": None},
        timeout=30,
    )
    return session


async def fetch_info(cfg: RuntimeConfig) -> dict[str, Any]:
    user = await login(cfg)
    return {
        "ok": True,
        "utente": user.dati,
        "stato": user.stato,
        "connesso": user.connesso,
        "secondi_rimasti": user.secondi_rimasti,
        "versione_libreria": package_version(),
        "student_id_risolto": getattr(user, "_cvprobe_resolved_student_id", getattr(user, "_id", None)),
        "student_id_originale": getattr(user, "_cvprobe_original_student_id", getattr(user, "_id", None)),
    }


async def fetch_method(
    cfg: RuntimeConfig,
    method_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    user = await login(cfg)
    method = getattr(user, method_name)
    result = method(*args, **kwargs)
    if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
        return await result
    return result


async def fetch_noticeboard_detail(cfg: RuntimeConfig, evt_code: str, pub_id: int) -> dict[str, Any]:
    user = await login(cfg)
    return await user.bacheca_leggi(str(evt_code), int(pub_id))


async def fetch_didactics_detail(cfg: RuntimeConfig, content_id: int) -> Any:
    user = await login(cfg)
    return await user.didattica_elemento(int(content_id))


async def download_document(cfg: RuntimeConfig, document_hash: str, *, fallback_name: str | None = None) -> DownloadedFile:
    user = await login(cfg)
    try:
        available = await user.controlla_documento(document_hash)
    except Exception:
        available = True
    if not available:
        raise ClasseVivaProbeError("Il documento richiesto non risulta disponibile.")

    url = Collegamenti.leggi_documento.format(user._id, document_hash)
    last_response: requests.Response | None = None
    for method_name in ("get", "post"):
        response = getattr(user._sessione, method_name)(
            url,
            headers=_auth_headers(user, include_content_type=False),
            allow_redirects=True,
            timeout=60,
        )
        last_response = response
        if response.status_code == 200:
            return _file_from_response(response, fallback_name)
    if last_response is None:
        raise ClasseVivaProbeError("Impossibile scaricare il documento richiesto.")
    _raise_for_unsuccessful_response(last_response)
    raise AssertionError("unreachable")


async def download_noticeboard_attachment(
    cfg: RuntimeConfig,
    pub_id: int,
    *,
    evt_code: str | None = None,
    fallback_name: str | None = None,
) -> DownloadedFile:
    user = await login(cfg)
    rest_response: requests.Response | None = None
    if evt_code:
        rest_response = user._sessione.get(
            Collegamenti.bacheca_allega.format(user._id, str(evt_code), int(pub_id)),
            headers=_auth_headers(user, include_content_type=False),
            allow_redirects=True,
            timeout=60,
        )
        if rest_response.status_code == 200 and not _looks_like_portal_page(rest_response):
            return _file_from_response(rest_response, fallback_name)

    portal = _portal_session(user)
    portal.post(
        url="https://web.spaggiari.eu/sif/app/default/bacheca_personale.php",
        data={"action": "get_comunicazioni", "cerca": None, "ncna": 1, "tipo_com": None},
        timeout=30,
    )
    response = portal.get(
        Collegamenti.bacheca_allega_esterno.format(int(pub_id)),
        allow_redirects=True,
        timeout=60,
    )
    if response.status_code == 200 and not _looks_like_portal_page(response):
        return _file_from_response(response, fallback_name or f"circolare-{pub_id}.bin")
    if rest_response is not None and rest_response.status_code != 200:
        _raise_for_unsuccessful_response(rest_response)
    if response.status_code != 200:
        _raise_for_unsuccessful_response(response)
    raise ClasseVivaProbeError("ClasseViva non ha restituito un allegato leggibile per questa circolare.")


async def proxy_resource(cfg: RuntimeConfig, url: str, *, fallback_name: str | None = None) -> DownloadedFile:
    normalized = _allowed_resource_url(url)
    user = await login(cfg)
    parsed = urlparse(normalized)

    if "/rest/" in parsed.path:
        response = user._sessione.get(
            normalized,
            headers=_auth_headers(user, include_content_type=False),
            allow_redirects=True,
            timeout=60,
        )
    else:
        response = _portal_session(user).get(normalized, allow_redirects=True, timeout=60)

    if response.status_code != 200:
        _raise_for_unsuccessful_response(response)
    return _file_from_response(response, fallback_name)


async def fetch_dashboard_bundle(
    cfg: RuntimeConfig,
    *,
    day: str,
    start: str,
    end: str,
    section_keys: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    user = await login(cfg)

    async def run(method_name: str, *args: Any) -> dict[str, Any]:
        try:
            method = getattr(user, method_name)
            result = method(*args)
            if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
                payload = await result
            else:
                payload = result
            return {"ok": True, "data": payload}
        except Exception as exc:
            return {"ok": False, "error": friendly_error(exc, section=method_name)}

    requested_keys = section_keys or tuple(SECTION_METHODS.keys())
    sections: dict[str, Any] = {}
    values_by_name = {"day": day, "start": start, "end": end}
    for key in requested_keys:
        method_name, arg_names = SECTION_METHODS[key]
        sections[key] = await run(method_name, *[values_by_name[arg] for arg in arg_names])

    return {
        "ok": True,
        "info": {
            "ok": True,
            "data": {
                "utente": user.dati,
                "stato": user.stato,
                "connesso": user.connesso,
                "secondi_rimasti": user.secondi_rimasti,
                "versione_libreria": package_version(),
                "student_id_risolto": getattr(user, "_cvprobe_resolved_student_id", getattr(user, "_id", None)),
                "student_id_originale": getattr(user, "_cvprobe_original_student_id", getattr(user, "_id", None)),
            },
        },
        "filters": {"day": day, "start": start, "end": end},
        "sections": sections,
    }


def friendly_error(exc: Exception, *, section: str | None = None) -> dict[str, Any]:
    hints: list[str] = []
    recoverable = False
    message = str(exc).strip() or repr(exc)

    if isinstance(exc, MissingCredentialsError):
        hints.append("controlla il file .env o inserisci username e password nella schermata di accesso")
    elif isinstance(exc, requests.exceptions.RequestException):
        hints.append("problema di rete / DNS / timeout")
        hints.append("verifica accesso a web.spaggiari.eu dal tuo PC o dalla VPS")
    else:
        name = exc.__class__.__name__
        if "Password" in name or "Valida" in name:
            hints.append("possibili credenziali errate")
        if "HTTP" in name or "Richiesta fallita" in message:
            hints.append("risposta API inattesa o endpoint cambiato")

    lowered = message.lower()
    if "student-id" in lowered:
        message = "ClasseViva ha rifiutato l'identificativo studente per questa richiesta (invalid student-id)."
        hints.append("ClasseViva sta rifiutando l'identificativo studente usato per questa sezione")
        recoverable = True
        if section and (section.startswith("lezioni") or section in {"panoramica_da_a"}):
            hints.append("gli endpoint lezioni di questo account potrebbero essere mappati in modo diverso o non disponibili")
    if "wrong uri" in lowered:
        hints.append("l'API di ClasseViva sta rifiutando l'endpoint o i parametri richiesti")
    if "token" in lowered:
        hints.append("la sessione potrebbe essere scaduta: riprova effettuando di nuovo l'accesso")

    return {
        "ok": False,
        "error_type": exc.__class__.__name__,
        "message": message,
        "hints": hints,
        "recoverable": recoverable,
    }


COMMON_METHODS: dict[str, tuple[str, str]] = {
    "info": ("Informazioni utente e sessione", "info"),
    "documenti": ("Documenti", "documenti"),
    "assenze": ("Assenze", "assenze"),
    "voti": ("Voti", "voti"),
    "note": ("Note", "note"),
    "agenda": ("Agenda", "agenda"),
    "bacheca": ("Bacheca", "bacheca"),
    "calendario": ("Calendario", "calendario"),
    "carta": ("Carta studente", "carta"),
    "didattica": ("Didattica", "didattica"),
    "libri": ("Libri", "libri"),
    "materie": ("Materie", "materie"),
    "periodi": ("Periodi", "periodi"),
}

RANGE_METHODS: dict[str, tuple[str, str]] = {
    "assenze_da_a": ("Assenze per intervallo", "assenze_da_a"),
    "agenda_da_a": ("Agenda per intervallo", "agenda_da_a"),
    "calendario_da_a": ("Calendario per intervallo", "calendario_da_a"),
    "lezioni_da_a": ("Lezioni per intervallo", "lezioni_da_a"),
    "panoramica_da_a": ("Panoramica per intervallo", "panoramica_da_a"),
}
