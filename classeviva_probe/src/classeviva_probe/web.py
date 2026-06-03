from __future__ import annotations

import argparse
import asyncio
import html
import io
import json
import mimetypes
import secrets
import threading
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse
from xml.etree import ElementTree as ET

from .ai_client import AIConfigurationError, AIProviderError, gemini_generate_reply, load_ai_config
from .coach import (
    build_leaderboard,
    build_performance_snapshot,
    build_study_plan,
    build_tutor_brief,
    build_tutor_reply,
    build_tutor_suggestions,
)
from .core import (
    DownloadedFile,
    RuntimeConfig,
    SECTION_METHODS as CORE_SECTION_METHODS,
    download_document,
    download_noticeboard_attachment,
    fetch_dashboard_bundle,
    fetch_didactics_detail,
    fetch_info,
    fetch_noticeboard_detail,
    friendly_error,
    load_config,
    proxy_resource,
    save_env_file,
)
from .presentation import detail_payload, present_dashboard
from .storage import (
    Database,
    append_chat_message,
    create_chat_thread,
    create_task,
    delete_task,
    ensure_chat_thread,
    ensure_profile,
    get_db_config,
    init_db,
    list_chat_messages,
    list_chat_threads,
    list_tasks,
    update_profile,
    update_task,
    create_user,
    get_user_by_email,
    update_user_cv_credentials,
)


SESSION_COOKIE_NAME = "cvprobe_session"
SESSION_TTL_SECONDS = 60 * 60 * 12

HTML_ROUTES = {
    "/",
    "/home",
    "/dashboard",
    "/tutor",
    "/voti",
    "/planner",
    "/attivita",
    "/agenda",
    "/rendimento",
    "/bacheca",
    "/documenti",
    "/profilo",
}

PAGE_SCHOOL_SECTIONS: dict[str, tuple[str, ...]] = {
    "dashboard": ("voti", "periodi", "agenda", "agenda_da_a", "bacheca", "documenti"),
    "tutor": ("voti", "periodi", "agenda", "agenda_da_a", "calendario", "calendario_da_a", "bacheca", "documenti", "didattica", "assenze", "note"),
    "voti": ("voti", "assenze", "note", "periodi", "materie"),
    "planner": ("agenda", "agenda_da_a", "calendario", "calendario_da_a", "voti"),
    "attivita": ("agenda", "agenda_da_a"),
    "agenda": ("agenda", "agenda_da_a", "calendario", "calendario_da_a"),
    "rendimento": ("voti", "assenze", "note", "periodi", "materie"),
    "bacheca": ("bacheca",),
    "documenti": ("documenti", "didattica"),
    "profilo": ("carta", "libri", "materie", "periodi"),
}


@dataclass
class SessionRecord:
    user_id: int | None
    username: str | None
    password: str | None
    created_at: float
    last_seen: float
    profile: dict[str, Any] | None = None


class SessionStore:
    def __init__(self) -> None:
        self._items: dict[str, SessionRecord] = {}
        self._lock = threading.Lock()

    def create(self, *, user_id: int | None = None, username: str | None = None, password: str | None = None, profile: dict[str, Any] | None = None) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            self._items[token] = SessionRecord(
                user_id=user_id,
                username=username,
                password=password,
                created_at=now,
                last_seen=now,
                profile=profile,
            )
        return token

    def get(self, token: str | None) -> SessionRecord | None:
        if not token:
            return None
        now = time.time()
        with self._lock:
            record = self._items.get(token)
            if not record:
                return None
            if now - record.last_seen > SESSION_TTL_SECONDS:
                self._items.pop(token, None)
                return None
            record.last_seen = now
            return record

    def delete(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._items.pop(token, None)


class ProbeWebApplication:
    def __init__(self, *, dotenv_path: str = ".env") -> None:
        self.project_root = Path.cwd()
        self.dotenv_path = (self.project_root / dotenv_path).resolve() if not Path(dotenv_path).is_absolute() else Path(dotenv_path)
        self.sessions = SessionStore()
        db_cfg = get_db_config()
        self.db = Database(**db_cfg)
        init_db(self.db)

    def asset_bytes(self, name: str) -> bytes:
        return resources.files("classeviva_probe").joinpath("web_static").joinpath(name).read_bytes()

    def saved_config(self) -> RuntimeConfig:
        return load_config(dotenv_path=self.dotenv_path)


def _current_filters(query: dict[str, list[str]]) -> dict[str, str]:
    today = date.today().isoformat()
    default_start = f"{date.today().year}-09-01"
    return {
        "day": (query.get("day") or [today])[0] or today,
        "start": (query.get("start") or [default_start])[0] or default_start,
        "end": (query.get("end") or [today])[0] or today,
    }


def _derive_display_name(info_data: dict[str, Any]) -> str:
    user = info_data.get("utente", {}) if isinstance(info_data, dict) else {}
    return " ".join(filter(None, [user.get("firstName"), user.get("lastName")])) or "Studente"


def _derive_user_key(cfg: RuntimeConfig, info_data: dict[str, Any]) -> str:
    user = info_data.get("utente", {}) if isinstance(info_data, dict) else {}
    return str(user.get("ident") or cfg.username or "default-user")


def _task_summary(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    today = date.today().isoformat()
    done = sum(1 for task in tasks if task.get("status") == "done")
    todo = sum(1 for task in tasks if task.get("status") == "todo")
    doing = sum(1 for task in tasks if task.get("status") == "doing")
    due_today = sum(1 for task in tasks if task.get("status") != "done" and task.get("due_date") == today)
    overdue = sum(1 for task in tasks if task.get("status") != "done" and task.get("due_date", today) < today)
    return {
        "total": len(tasks),
        "done": done,
        "todo": todo,
        "doing": doing,
        "due_today": due_today,
        "overdue": overdue,
    }


def _overview_payload(info_data: dict[str, Any], profile: dict[str, Any], tasks: list[dict[str, Any]], performance: dict[str, Any]) -> dict[str, Any]:
    summary = _task_summary(tasks)
    user = info_data.get("utente", {})
    stats = [
        {"label": "Attività aperte", "value": summary["todo"] + summary["doing"]},
        {"label": "Scadenze oggi", "value": summary["due_today"]},
        {"label": "Media scolastica", "value": performance.get("overall_average") or "n/d"},
        {"label": "Task completate", "value": summary["done"]},
    ]
    return {
        "student_name": _derive_display_name(info_data),
        "student_id": user.get("ident"),
        "resolved_student_id": info_data.get("student_id_risolto"),
        "status": info_data.get("stato"),
        "connected": info_data.get("connesso"),
        "seconds_left": info_data.get("secondi_rimasti"),
        "library_version": info_data.get("versione_libreria"),
        "study_goal": profile.get("study_goal"),
        "learning_mode": profile.get("learning_mode"),
        "stats": stats,
    }


def _page_school_payload(bundle: dict[str, Any]) -> dict[str, Any]:
    presented = present_dashboard(bundle)
    return {
        "sections": presented["sections"],
        "order": presented["section_order"],
    }


def _dashboard_cards(tasks: list[dict[str, Any]], plan: dict[str, Any], suggestions: list[dict[str, Any]], school: dict[str, Any]) -> dict[str, Any]:
    next_tasks = tasks[:4]
    next_days = plan["days"][:3]
    school_sections = school.get("sections", {})
    bacheca_items = school_sections.get("bacheca", {}).get("items", [])[:3]
    flat_documents = _flatten_document_items(school)[:3]
    return {
        "next_tasks": next_tasks,
        "next_days": next_days,
        "suggestions": suggestions[:3],
        "bacheca": bacheca_items,
        "documents": flat_documents[:3],
    }


def _flatten_document_items(school: dict[str, Any]) -> list[dict[str, Any]]:
    school_sections = school.get("sections", {})
    documents_groups = school_sections.get("documenti", {}).get("groups", [])
    items: list[dict[str, Any]] = []
    for group in documents_groups:
        items.extend(group.get("items", []))
    return items


def _load_workspace(
    *,
    app: ProbeWebApplication,
    user_id: int,
    cfg: RuntimeConfig,
    section_keys: tuple[str, ...],
    filters: dict[str, str],
) -> dict[str, Any]:
    bundle = asyncio.run(
        fetch_dashboard_bundle(
            cfg,
            day=filters["day"],
            start=filters["start"],
            end=filters["end"],
            section_keys=section_keys,
        )
    )
    info_data = bundle["info"]["data"]
    display_name = _derive_display_name(info_data)
    profile = ensure_profile(app.db, user_id=user_id, display_name=display_name)
    tasks = list_tasks(app.db, user_id=user_id)
    performance = build_performance_snapshot(bundle["sections"])
    plan = build_study_plan(tasks, profile, performance)
    suggestions = build_tutor_suggestions(tasks, performance, plan, profile)
    leaderboard = build_leaderboard(display_name, performance, tasks)
    school = _page_school_payload(bundle)
    return {
        "bundle": bundle,
        "info_data": info_data,
        "user_id": user_id,
        "display_name": display_name,
        "profile": profile,
        "tasks": tasks,
        "performance": performance,
        "plan": plan,
        "suggestions": suggestions,
        "leaderboard": leaderboard,
        "school": school,
    }


def _welcome_message(display_name: str, brief: dict[str, Any]) -> str:
    return (
        f"Ciao {display_name or 'studente'}, sono il tuo tutor digitale.\n\n"
        f"{brief['status']}\n\n"
        "Posso aiutarti a organizzare lo studio, leggere le circolari più importanti, "
        "capire dove recuperare nei voti e trasformare tutto in un piano concreto."
    )


def _chat_provider_payload(app: ProbeWebApplication) -> dict[str, Any]:
    config = load_ai_config(dotenv_path=app.dotenv_path)
    return {
        "provider": config.provider,
        "label": config.label,
        "enabled": config.enabled,
        "hint": None
        if config.enabled
        else "Per attivare la chat con AI reale aggiungi GEMINI_API_KEY al file .env.",
    }


def _chat_history_for_llm(messages: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in messages[-limit:]:
        role = "model" if item.get("role") == "assistant" else "user"
        output.append({"role": role, "parts": [{"text": item.get("content", "")}]})
    return output


def _grade_context_lines(performance: dict[str, Any], *, limit: int = 4) -> list[str]:
    rows = []
    for item in performance.get("subject_averages", [])[:limit]:
        rows.append(f"- {item['subject']}: media {item['average']} su {item['count']} voti")
    return rows


def _grade_detail_lines(school: dict[str, Any], *, limit: int = 20) -> list[str]:
    section = school.get("sections", {}).get("voti", {})
    if not section or not section.get("ok") or section.get("kind") != "grades":
        return []

    rows = []
    for item in section.get("items", [])[:limit]:
        subject = item.get("subject") or item.get("title") or "Materia non indicata"
        teacher = item.get("teacher") or item.get("subtitle") or "Docente non indicato"
        grade = item.get("grade") or "—"
        description = item.get("description") or "nessuna descrizione"
        rows.append(f"- {subject} | voto {grade} | docente {teacher} | descrizione {description}")
    return rows


def _task_context_lines(tasks: list[dict[str, Any]], *, limit: int = 5) -> list[str]:
    rows = []
    for task in tasks[:limit]:
        rows.append(
            f"- {task.get('title')} | {task.get('subject')} | scadenza {task.get('due_date')} | stato {task.get('status')}"
        )
    return rows


def _noticeboard_context_lines(school: dict[str, Any], *, limit: int = 4) -> list[str]:
    items = school.get("sections", {}).get("bacheca", {}).get("items", [])[:limit]
    rows = []
    for item in items:
        rows.append(f"- {item.get('title')}")
    return rows


def _documents_context_lines(school: dict[str, Any], *, limit: int = 4) -> list[str]:
    rows = []
    for item in _flatten_document_items(school)[:limit]:
        rows.append(f"- {item.get('title')}")
    return rows


def _generic_section_lines(school: dict[str, Any], section_key: str, *, limit: int = 6) -> list[str]:
    section = school.get("sections", {}).get(section_key, {})
    if not section or not section.get("ok"):
        return []
    if section.get("kind") == "documents":
        lines = []
        for item in _flatten_document_items(school)[:limit]:
            lines.append(f"- {item.get('title')}")
        return lines
    lines = []
    for item in section.get("items", [])[:limit]:
        title = item.get("title") or "Elemento"
        subtitle = item.get("subtitle") or ""
        body = item.get("body") or ""
        text = " | ".join(part for part in (title, subtitle, body) if part)
        lines.append(f"- {text}")
    return lines


def _plan_context_lines(plan: dict[str, Any], *, limit_days: int = 2) -> list[str]:
    rows = []
    for day in plan.get("days", [])[:limit_days]:
        if not day.get("sessions"):
            continue
        sessions = ", ".join(f"{entry['title']} ({entry['minutes']} min)" for entry in day.get("sessions", [])[:3])
        rows.append(f"- {day.get('date')}: {sessions}")
    return rows


def _llm_system_instruction(
    *,
    display_name: str,
    profile: dict[str, Any],
    performance: dict[str, Any],
    tasks: list[dict[str, Any]],
    plan: dict[str, Any],
    school: dict[str, Any],
) -> str:
    risk_subjects = performance.get("risk_subjects", [])
    strong_subjects = performance.get("strong_subjects", [])
    focus_risk = ", ".join(item["subject"] for item in risk_subjects[:3]) or "nessuna criticità evidente"
    focus_strong = ", ".join(item["subject"] for item in strong_subjects[:3]) or "non ancora chiaro"
    return "\n".join(
        [
            "Sei un tutor scolastico digitale che risponde in italiano in modo concreto, amichevole e sintetico.",
            "Devi basarti solo sul contesto fornito. Se un'informazione non è presente, dichiaralo chiaramente.",
            "Evita frasi vaghe e proponi passi operativi, sostenibili e personalizzati.",
            f"Studente: {display_name}",
            f"Modalità di studio: {profile.get('learning_mode') or 'standard'}",
            f"Obiettivo dichiarato: {profile.get('study_goal') or 'non indicato'}",
            f"Media generale: {performance.get('overall_average') or 'n/d'}",
            f"Materie più fragili: {focus_risk}",
            f"Materie più forti: {focus_strong}",
            "Attività aperte:",
            *(_task_context_lines([task for task in tasks if task.get('status') != 'done']) or ["- nessuna attività aperta"]),
            "Prossime sessioni di studio:",
            *(_plan_context_lines(plan) or ["- nessuna sessione pianificata"]),
            "Medie per materia:",
            *(_grade_context_lines(performance) or ["- nessun dato voti disponibile"]),
            "Voti dettagliati disponibili nel sito:",
            *(_grade_detail_lines(school) or ["- nessun voto dettagliato disponibile"]),
            "Circolari recenti:",
            *(_noticeboard_context_lines(school) or ["- nessuna circolare disponibile"]),
            "Documenti recenti:",
            *(_documents_context_lines(school) or ["- nessun documento disponibile"]),
            "Materiali didattici:",
            *(_generic_section_lines(school, "didattica") or ["- nessun materiale didattico disponibile"]),
            "Agenda e compiti dal sito:",
            *(
                _generic_section_lines(school, "agenda_da_a", limit=10)
                or _generic_section_lines(school, "agenda", limit=10)
                or _generic_section_lines(school, "calendario_da_a", limit=10)
                or ["- nessuna voce agenda disponibile"]
            ),
            "Assenze registrate:",
            *(_generic_section_lines(school, "assenze") or ["- nessuna assenza disponibile"]),
            "Note disciplinari o annotazioni:",
            *(_generic_section_lines(school, "note") or ["- nessuna nota disponibile"]),
            "Quando l'utente chiede di organizzare lo studio, restituisci un mini piano ordinato per priorità.",
            "Quando l'utente chiede di voti o rendimento, evidenzia materia, criticità e contromossa pratica.",
            "Quando l'utente chiede di circolari o documenti, riassumi ciò che sai dai titoli e invita ad aprire il documento se il testo completo non è disponibile.",
            "Se sono presenti voti dettagliati, non dire mai che mancano i dati dei voti o della media: usa ciò che hai nel contesto.",
        ]
    )


def _build_chat_payload(
    *,
    app: ProbeWebApplication,
    user_id: int,
    display_name: str,
    profile: dict[str, Any],
    tasks: list[dict[str, Any]],
    performance: dict[str, Any],
    plan: dict[str, Any],
    school: dict[str, Any],
    include_messages: bool,
    thread_id: int | None = None,
) -> dict[str, Any]:
    effective_name = profile.get("display_name") or display_name
    brief = build_tutor_brief(effective_name, tasks, performance, plan, profile, school)
    provider = _chat_provider_payload(app)
    active_thread = ensure_chat_thread(app.db, user_id=user_id, thread_id=thread_id)
    threads = list_chat_threads(app.db, user_id=user_id)
    messages = list_chat_messages(app.db, user_id=user_id, thread_id=active_thread["id"], limit=36) if include_messages else []
    if include_messages and not messages:
        append_chat_message(
            app.db,
            user_id=user_id,
            thread_id=active_thread["id"],
            role="assistant",
            content=_welcome_message(effective_name, brief),
            context={"topic": "welcome"},
        )
        messages = list_chat_messages(app.db, user_id=user_id, thread_id=active_thread["id"], limit=36)
        threads = list_chat_threads(app.db, user_id=user_id)

    last_message = messages[-1]["content"] if messages else _welcome_message(effective_name, brief)
    return {
        "thread_id": active_thread["id"],
        "thread": active_thread,
        "threads": threads,
        "status": brief["status"],
        "starter_prompts": brief["starter_prompts"],
        "context_cards": brief["context_cards"],
        "preview_message": last_message,
        "messages": messages,
        "provider": provider,
    }


def _build_page_payload(
    *,
    app: ProbeWebApplication,
    user_id: int,
    cfg: RuntimeConfig,
    page_id: str,
    filters: dict[str, str],
) -> dict[str, Any]:
    section_keys = PAGE_SCHOOL_SECTIONS.get(page_id, PAGE_SCHOOL_SECTIONS["dashboard"])
    workspace = _load_workspace(app=app, user_id=user_id, cfg=cfg, section_keys=section_keys, filters=filters)
    info_data = workspace["info_data"]
    profile = workspace["profile"]
    tasks = workspace["tasks"]
    performance = workspace["performance"]
    plan = workspace["plan"]
    suggestions = workspace["suggestions"]
    leaderboard = workspace["leaderboard"]
    school = workspace["school"]

    payload = {
        "ok": True,
        "page_id": page_id,
        "filters": filters,
        "overview": _overview_payload(info_data, profile, tasks, performance),
        "profile": profile,
        "tasks": tasks,
        "task_summary": _task_summary(tasks),
        "performance": performance,
        "plan": plan,
        "suggestions": suggestions,
        "leaderboard": leaderboard,
        "school": school,
    }

    if page_id == "dashboard":
        payload["dashboard"] = _dashboard_cards(tasks, plan, suggestions, school)
        payload["chat"] = _build_chat_payload(
            app=app,
            user_id=workspace["user_id"],
            display_name=workspace["display_name"],
            profile=profile,
            tasks=tasks,
            performance=performance,
            plan=plan,
            school=school,
            include_messages=False,
        )
    if page_id == "tutor":
        payload["chat"] = _build_chat_payload(
            app=app,
            user_id=workspace["user_id"],
            display_name=workspace["display_name"],
            profile=profile,
            tasks=tasks,
            performance=performance,
            plan=plan,
            school=school,
            include_messages=True,
        )

    return payload


def _docx_to_html(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")
    except Exception:
        return "<p>Impossibile generare un'anteprima leggibile per questo file .docx.</p>"

    root = ET.fromstring(xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    parts: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        texts = [node.text for node in paragraph.findall(".//w:t", namespace) if node.text]
        joined = "".join(texts).strip()
        if joined:
            parts.append(f"<p>{html.escape(joined)}</p>")
    return "".join(parts) or "<p>Documento Word senza testo estraibile.</p>"


def _preview_document_html(*, title: str, body_html: str, raw_url: str, filename: str | None = None) -> bytes:
    safe_title = html.escape(title)
    safe_name = html.escape(filename or "allegato")
    page = f"""<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{safe_title}</title>
    <style>
      body {{
        margin: 0;
        font-family: "Avenir Next", "Segoe UI", sans-serif;
        background: #f7f1e8;
        color: #19211b;
      }}
      main {{
        max-width: 860px;
        margin: 0 auto;
        padding: 28px 18px 42px;
      }}
      .top {{
        display: flex;
        justify-content: space-between;
        gap: 18px;
        align-items: start;
        margin-bottom: 20px;
      }}
      .tag {{
        display: inline-flex;
        padding: 6px 12px;
        border-radius: 999px;
        background: rgba(15, 123, 108, 0.12);
        color: #0f7b6c;
        font-weight: 700;
      }}
      article {{
        background: rgba(255,255,255,0.78);
        border-radius: 20px;
        padding: 22px;
        line-height: 1.7;
        box-shadow: 0 14px 40px rgba(26, 33, 27, 0.12);
      }}
      a {{
        color: #0f7b6c;
        font-weight: 700;
      }}
    </style>
  </head>
  <body>
    <main>
      <div class="top">
        <div>
          <span class="tag">Anteprima interna</span>
          <h1>{safe_title}</h1>
          <p>{safe_name}</p>
        </div>
        <a href="{html.escape(raw_url)}" target="_blank" rel="noopener">Apri file originale</a>
      </div>
      <article>{body_html}</article>
    </main>
  </body>
</html>"""
    return page.encode("utf-8")


def _preview_pdf_html(*, title: str, raw_url: str, filename: str | None = None) -> bytes:
    safe_title = html.escape(title)
    safe_name = html.escape(filename or "allegato.pdf")
    safe_raw_url = html.escape(raw_url)
    page = f"""<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{safe_title}</title>
    <style>
      html,
      body {{
        height: 100%;
        margin: 0;
        background: #f5f5f7;
        color: #1d1d1f;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
      }}
      .pdf-shell {{
        display: grid;
        grid-template-rows: auto 1fr;
        min-height: 100%;
      }}
      .pdf-toolbar {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        padding: 12px 14px;
        border-bottom: 1px solid rgba(0, 0, 0, 0.08);
        background: rgba(255, 255, 255, 0.88);
      }}
      strong {{
        display: block;
        font-size: 14px;
      }}
      small {{
        color: #6e6e73;
      }}
      a {{
        border-radius: 999px;
        padding: 8px 12px;
        color: #fff;
        background: #0071e3;
        text-decoration: none;
        font-weight: 700;
        font-size: 13px;
        white-space: nowrap;
      }}
      object,
      iframe {{
        width: 100%;
        height: 100%;
        border: 0;
        background: #fff;
      }}
      .fallback {{
        padding: 24px;
      }}
    </style>
  </head>
  <body>
    <main class="pdf-shell">
      <header class="pdf-toolbar">
        <div>
          <strong>{safe_title}</strong>
          <small>{safe_name}</small>
        </div>
        <a href="{safe_raw_url}" target="_blank" rel="noopener">Apri originale</a>
      </header>
      <object data="{safe_raw_url}" type="application/pdf">
        <iframe src="{safe_raw_url}" title="{safe_title}"></iframe>
        <p class="fallback">Il PDF non puo essere mostrato qui. <a href="{safe_raw_url}" target="_blank" rel="noopener">Aprilo in una nuova scheda</a>.</p>
      </object>
    </main>
  </body>
</html>"""
    return page.encode("utf-8")


def _preview_response(file: DownloadedFile, raw_url: str, title: str) -> tuple[bytes, str]:
    name = (file.filename or "").lower()
    content_type = file.content_type or "application/octet-stream"
    guessed_type, _ = mimetypes.guess_type(file.filename or "")
    if content_type in {"application/octet-stream", "binary/octet-stream"} and guessed_type:
        content_type = guessed_type

    if content_type == "application/pdf" or name.endswith(".pdf"):
        return _preview_pdf_html(title=title, raw_url=raw_url, filename=file.filename), "text/html; charset=utf-8"

    if content_type.startswith("image/"):
        return file.content, content_type

    if "text/html" in content_type:
        return file.content, "text/html; charset=utf-8"

    if name.endswith(".docx") or "wordprocessingml.document" in content_type:
        return _preview_document_html(title=title, body_html=_docx_to_html(file.content), raw_url=raw_url, filename=file.filename), "text/html; charset=utf-8"

    if content_type.startswith("text/") or "rtf" in content_type or name.endswith((".txt", ".csv", ".json", ".xml", ".html", ".htm", ".md", ".rtf")):
        text = file.content.decode("utf-8", errors="ignore")
        body = "".join(f"<p>{html.escape(line)}</p>" for line in text.splitlines() if line.strip()) or "<p>File di testo vuoto.</p>"
        return _preview_document_html(title=title, body_html=body, raw_url=raw_url, filename=file.filename), "text/html; charset=utf-8"

    body = (
        "<p>Questo formato non è facilmente anteprimabile dentro il browser.</p>"
        f"<p>Puoi comunque aprire il file originale da <a href=\"{html.escape(raw_url)}\" target=\"_blank\" rel=\"noopener\">questo link</a>.</p>"
    )
    return _preview_document_html(title=title, body_html=body, raw_url=raw_url, filename=file.filename), "text/html; charset=utf-8"


def _noticeboard_has_no_content(exc: Exception) -> bool:
    message = str(exc).lower()
    return "no content available" in message or "nothing attached" in message or "there is nothing attached" in message


def _noticeboard_empty_html(*, title: str, pub_id: int | str) -> bytes:
    body = (
        "<p>ClasseViva non ha restituito un allegato apribile per questa circolare.</p>"
        "<p>La comunicazione resta visibile in bacheca, ma il file non e disponibile tramite API.</p>"
    )
    return _preview_document_html(
        title=title,
        body_html=body,
        raw_url="#",
        filename=f"circolare-{pub_id}",
    )


class ProbeJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


class ProbeRequestHandler(BaseHTTPRequestHandler):
    app: ProbeWebApplication

    def log_message(self, format: str, *args: Any) -> None:
        return

    @property
    def query(self) -> dict[str, list[str]]:
        return parse_qs(urlparse(self.path).query, keep_blank_values=True)

    @property
    def route_path(self) -> str:
        return urlparse(self.path).path

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _finish_response(self, body: bytes | None = None) -> None:
        try:
            self.end_headers()
            if body:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_json(self, payload: dict[str, Any], *, status: int = 200, cookie_value: str | None = None, clear_cookie: bool = False) -> None:
        body = json.dumps(payload, ensure_ascii=False, cls=ProbeJSONEncoder).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cookie_value:
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE_NAME}={cookie_value}; HttpOnly; Path=/; SameSite=Lax; Max-Age={SESSION_TTL_SECONDS}",
            )
        elif clear_cookie:
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE_NAME}=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0",
            )
        self._finish_response(body)

    def _send_head_only(self, *, content_type: str, content_length: int, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self._finish_response()

    def _send_bytes(self, content: bytes, *, content_type: str, filename: str | None = None, force_download: bool = False) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        if filename:
            disposition = "attachment" if force_download else "inline"
            self.send_header("Content-Disposition", f'{disposition}; filename="{filename}"')
        self._finish_response(content)

    def _send_text(self, content: bytes, *, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self._finish_response(content)

    def _send_error(self, status: int, exc: Exception | dict[str, Any]) -> None:
        payload = exc if isinstance(exc, dict) else friendly_error(exc)
        self._send_json({"ok": False, "error": payload}, status=status)

    def _session_token(self) -> str | None:
        raw_cookie = self.headers.get("Cookie")
        if not raw_cookie:
            return None
        cookie = SimpleCookie()
        cookie.load(raw_cookie)
        morsel = cookie.get(SESSION_COOKIE_NAME)
        return morsel.value if morsel else None

    def _session_record(self) -> SessionRecord | None:
        return self.app.sessions.get(self._session_token())

    def _runtime_config(self) -> RuntimeConfig | None:
        record = self._session_record()
        if not record:
            return None
        return RuntimeConfig(username=record.username, password=record.password)

    def _restore_from_env(self) -> tuple[str | None, dict[str, Any] | None]:
        cfg = self.app.saved_config()
        if not cfg.username or not cfg.password:
            return None, None
        try:
            info = asyncio.run(fetch_info(cfg))
        except Exception:
            return None, None
        token = self.app.sessions.create(username=cfg.username, password=cfg.password, profile=info)
        return token, info

    def _query_value(self, key: str, default: str | None = None) -> str | None:
        values = self.query.get(key)
        return values[0] if values else default

    def _download_flag(self) -> bool:
        return self._query_value("download", "0") in {"1", "true", "yes"}

    def _require_config(self) -> RuntimeConfig | None:
        cfg = self._runtime_config()
        if cfg is None:
            self._send_json(
                {
                    "ok": False,
                    "error": {"message": "Sessione scaduta o non presente. Effettua di nuovo l'accesso."},
                },
                status=401,
            )
        return cfg

    def _build_user_context(self, cfg: RuntimeConfig) -> tuple[str, dict[str, Any]]:
        info = asyncio.run(fetch_info(cfg))
        user_key = _derive_user_key(cfg, info)
        return user_key, info

    def do_GET(self) -> None:
        path = self.route_path.rstrip("/") or "/"

        if path in HTML_ROUTES:
            self._send_text(self.app.asset_bytes("index.html"), content_type="text/html; charset=utf-8")
            return
        if path == "/assets/app.css":
            self._send_text(self.app.asset_bytes("app.css"), content_type="text/css; charset=utf-8")
            return
        if path == "/assets/app.js":
            self._send_text(self.app.asset_bytes("app.js"), content_type="application/javascript; charset=utf-8")
            return
        if path == "/api/health":
            self._send_json({"ok": True, "status": "healthy"})
            return
        if path == "/api/session":
            self._handle_get_session()
            return
        if path.startswith("/api/page/"):
            self._handle_page()
            return
        if path == "/api/chat/threads":
            self._handle_chat_threads()
            return
        if path == "/api/chat":
            self._handle_get_chat()
            return
        if path == "/api/tasks":
            self._handle_tasks_list()
            return
        if path.startswith("/api/details/document/"):
            self._handle_document_detail()
            return
        if path.startswith("/api/details/noticeboard/"):
            self._handle_noticeboard_detail()
            return
        if path.startswith("/api/details/didactics/"):
            self._handle_didactics_detail()
            return
        if path.startswith("/api/preview/document/"):
            self._handle_document_preview()
            return
        if path.startswith("/api/preview/noticeboard/"):
            self._handle_noticeboard_preview()
            return
        if path == "/api/preview/resource":
            self._handle_resource_preview()
            return
        if path.startswith("/api/download/document/"):
            self._handle_document_download()
            return
        if path.startswith("/api/download/noticeboard/"):
            self._handle_noticeboard_download()
            return
        if path == "/api/download/resource":
            self._handle_resource_download()
            return

        self._send_json({"ok": False, "message": "Risorsa non trovata"}, status=404)

    def do_HEAD(self) -> None:
        path = self.route_path.rstrip("/") or "/"
        if path in HTML_ROUTES:
            content = self.app.asset_bytes("index.html")
            self._send_head_only(content_type="text/html; charset=utf-8", content_length=len(content))
            return
        if path == "/assets/app.css":
            content = self.app.asset_bytes("app.css")
            self._send_head_only(content_type="text/css; charset=utf-8", content_length=len(content))
            return
        if path == "/assets/app.js":
            content = self.app.asset_bytes("app.js")
            self._send_head_only(content_type="application/javascript; charset=utf-8", content_length=len(content))
            return
        if path == "/api/health":
            body = json.dumps({"ok": True, "status": "healthy"}).encode("utf-8")
            self._send_head_only(content_type="application/json; charset=utf-8", content_length=len(body))
            return
        self._send_head_only(content_type="application/json; charset=utf-8", content_length=0, status=404)

    def do_POST(self) -> None:
        path = self.route_path.rstrip("/") or "/"
        if path == "/api/register":
            self._handle_register()
            return
        if path == "/api/session":
            self._handle_create_session()
            return
        if path == "/api/chat/threads":
            self._handle_chat_thread_create()
            return
        if path == "/api/chat":
            self._handle_chat_message()
            return
        if path == "/api/tasks":
            self._handle_task_create()
            return
        self._send_json({"ok": False, "message": "Risorsa non trovata"}, status=404)

    def do_PATCH(self) -> None:
        path = self.route_path.rstrip("/") or "/"
        if path == "/api/profile":
            self._handle_profile_update()
            return
        if path.startswith("/api/tasks/"):
            self._handle_task_update()
            return
        self._send_json({"ok": False, "message": "Risorsa non trovata"}, status=404)

    def do_DELETE(self) -> None:
        path = self.route_path.rstrip("/") or "/"
        if path == "/api/session":
            self.app.sessions.delete(self._session_token())
            self._send_json({"ok": True}, clear_cookie=True)
            return
        if path.startswith("/api/tasks/"):
            self._handle_task_delete()
            return
        self._send_json({"ok": False, "message": "Risorsa non trovata"}, status=404)

    def _handle_register(self) -> None:
        payload = self._read_json_body()
        email = str(payload.get("email", "")).strip()
        name = str(payload.get("name", "")).strip()
        school_level = str(payload.get("school_level", "")).strip()

        if not email or not name or not school_level:
            self._send_json({"ok": False, "message": "Email, nome e livello scolastico sono obbligatori"}, status=400)
            return

        try:
            user = get_user_by_email(self.app.db, email)
            if not user:
                user = create_user(self.app.db, email, name, school_level)

            token = self.app.sessions.create(user_id=user["id"])
            self._send_json({"ok": True, "user": user}, cookie_value=token)
        except Exception as exc:
            self._send_error(500, exc)

    def _handle_get_session(self) -> None:
        record = self._session_record()
        if record:
            self._send_json(
                {
                    "ok": True,
                    "authenticated": bool(record.username and record.password),
                    "onboarded": bool(record.user_id),
                    "user_id": record.user_id,
                    "profile": record.profile,
                }
            )
            return

        self._send_json(
            {
                "ok": True,
                "authenticated": False,
                "onboarded": False,
            }
        )

    def _handle_create_session(self) -> None:
        record = self._session_record()
        if not record or not record.user_id:
            self._send_json({"ok": False, "message": "Devi prima completare la registrazione base"}, status=401)
            return

        payload = self._read_json_body()
        cfg = RuntimeConfig(
            username=str(payload.get("username", "")).strip() or None,
            password=str(payload.get("password", "")).strip() or None,
        )

        try:
            info = asyncio.run(fetch_info(cfg))
        except Exception as exc:
            self._send_error(401, exc)
            return

        update_user_cv_credentials(self.app.db, record.user_id, cfg.username or "", cfg.password or "")
        
        # Aggiorna il record di sessione esistente
        record.username = cfg.username
        record.password = cfg.password
        record.profile = info
        
        self._send_json({"ok": True, "authenticated": True, "profile": info})

    def _handle_page(self) -> None:
        record = self._session_record()
        if not record or not record.user_id:
            self._send_json({"ok": False, "message": "Non autorizzato"}, status=401)
            return
            
        cfg = self._require_config()
        if cfg is None:
            return
        page_id = (self.route_path.rstrip("/") or "/").rsplit("/", 1)[-1] or "dashboard"
        if page_id not in PAGE_SCHOOL_SECTIONS:
            self._send_json({"ok": False, "message": "Pagina non trovata"}, status=404)
            return

        try:
            payload = _build_page_payload(app=self.app, user_id=record.user_id, cfg=cfg, page_id=page_id, filters=_current_filters(self.query))
            self._send_json(payload)
        except Exception as exc:
            self._send_error(500, exc)

    def _handle_get_chat(self) -> None:
        record = self._session_record()
        if not record or not record.user_id:
            self._send_json({"ok": False, "message": "Non autorizzato"}, status=401)
            return
            
        cfg = self._require_config()
        if cfg is None:
            return
        try:
            filters = _current_filters(self.query)
            thread_id_value = self._query_value("thread_id")
            thread_id = int(thread_id_value) if thread_id_value else None
            workspace = _load_workspace(
                app=self.app,
                user_id=record.user_id,
                cfg=cfg,
                section_keys=PAGE_SCHOOL_SECTIONS["tutor"],
                filters=filters,
            )
            payload = _build_chat_payload(
                app=self.app,
                user_id=record.user_id,
                display_name=workspace["display_name"],
                profile=workspace["profile"],
                tasks=workspace["tasks"],
                performance=workspace["performance"],
                plan=workspace["plan"],
                school=workspace["school"],
                include_messages=True,
                thread_id=thread_id,
            )
            self._send_json({"ok": True, "chat": payload, "filters": filters})
        except Exception as exc:
            self._send_error(500, exc)

    def _handle_chat_threads(self) -> None:
        record = self._session_record()
        if not record or not record.user_id:
            self._send_json({"ok": False, "message": "Non autorizzato"}, status=401)
            return
            
        cfg = self._require_config()
        if cfg is None:
            return
        try:
            display_name = _derive_display_name(record.profile or {})
            ensure_profile(self.app.db, user_id=record.user_id, display_name=display_name)
            active = ensure_chat_thread(self.app.db, user_id=record.user_id)
            self._send_json({"ok": True, "active_thread": active, "threads": list_chat_threads(self.app.db, user_id=record.user_id)})
        except Exception as exc:
            self._send_error(500, exc)

    def _handle_chat_thread_create(self) -> None:
        record = self._session_record()
        if not record or not record.user_id:
            self._send_json({"ok": False, "message": "Non autorizzato"}, status=401)
            return
            
        cfg = self._require_config()
        if cfg is None:
            return
        payload = self._read_json_body()
        try:
            display_name = _derive_display_name(record.profile or {})
            ensure_profile(self.app.db, user_id=record.user_id, display_name=display_name)
            thread = create_chat_thread(
                self.app.db,
                user_id=record.user_id,
                title=str(payload.get("title") or "Nuova chat"),
            )
            self._send_json({"ok": True, "thread": thread, "threads": list_chat_threads(self.app.db, user_id=record.user_id)}, status=201)
        except Exception as exc:
            self._send_error(500, exc)

    def _handle_chat_message(self) -> None:
        record = self._session_record()
        if not record or not record.user_id:
            self._send_json({"ok": False, "message": "Non autorizzato"}, status=401)
            return

        cfg = self._require_config()
        if cfg is None:
            return
        payload = self._read_json_body()
        message = str(payload.get("message", "")).strip()
        if not message:
            self._send_json({"ok": False, "message": "Messaggio vuoto"}, status=400)
            return

        filters = {
            "day": str(payload.get("day") or _current_filters(self.query)["day"]),
            "start": str(payload.get("start") or _current_filters(self.query)["start"]),
            "end": str(payload.get("end") or _current_filters(self.query)["end"]),
        }
        thread_id = int(payload["thread_id"]) if payload.get("thread_id") else None

        try:
            workspace = _load_workspace(
                app=self.app,
                user_id=record.user_id,
                cfg=cfg,
                section_keys=PAGE_SCHOOL_SECTIONS["tutor"],
                filters=filters,
            )
            append_chat_message(
                self.app.db,
                user_id=record.user_id,
                thread_id=thread_id,
                role="user",
                content=message,
                context={"filters": filters},
            )
            display_name = workspace["profile"].get("display_name") or workspace["display_name"]
            active_thread = ensure_chat_thread(self.app.db, user_id=record.user_id, thread_id=thread_id)
            chat_messages = list_chat_messages(self.app.db, user_id=record.user_id, thread_id=active_thread["id"], limit=10)
            ai_config = load_ai_config(dotenv_path=self.app.dotenv_path)
            provider_mode = "local"
            if ai_config.enabled:
                try:
                    llm_text = asyncio.run(gemini_generate_reply(
                        config=ai_config,
                        system_instruction=_llm_system_instruction(
                            display_name=display_name,
                            profile=workspace["profile"],
                            performance=workspace["performance"],
                            tasks=workspace["tasks"],
                            plan=workspace["plan"],
                            school=workspace["school"],
                        ),
                        history=_chat_history_for_llm(chat_messages, limit=10),
                    ))
                    reply = {
                        "topic": "Tutor AI",
                        "content": llm_text,
                        "chips": [ai_config.label],
                    }
                    provider_mode = "gemini"
                except (AIProviderError, AIConfigurationError):
                    reply = build_tutor_reply(
                        question=message,
                        display_name=display_name,
                        tasks=workspace["tasks"],
                        performance=workspace["performance"],
                        plan=workspace["plan"],
                        profile=workspace["profile"],
                        school=workspace["school"],
                    )
            else:
                reply = build_tutor_reply(
                    question=message,
                    display_name=display_name,
                    tasks=workspace["tasks"],
                    performance=workspace["performance"],
                    plan=workspace["plan"],
                    profile=workspace["profile"],
                    school=workspace["school"],
                )
            append_chat_message(
                self.app.db,
                user_id=record.user_id,
                thread_id=active_thread["id"],
                role="assistant",
                content=reply["content"],
                context={"topic": reply.get("topic"), "chips": reply.get("chips", []), "provider": provider_mode},
            )
            chat_payload = _build_chat_payload(
                app=self.app,
                user_id=record.user_id,
                display_name=workspace["display_name"],
                profile=workspace["profile"],
                tasks=workspace["tasks"],
                performance=workspace["performance"],
                plan=workspace["plan"],
                school=workspace["school"],
                include_messages=True,
                thread_id=active_thread["id"],
            )
            self._send_json({"ok": True, "chat": chat_payload, "reply": reply})
        except Exception as exc:
            self._send_error(500, exc)

    def _handle_tasks_list(self) -> None:
        record = self._session_record()
        if not record or not record.user_id:
            self._send_json({"ok": False, "message": "Non autorizzato"}, status=401)
            return
            
        cfg = self._require_config()
        if cfg is None:
            return
        try:
            display_name = _derive_display_name(record.profile or {})
            profile = ensure_profile(self.app.db, user_id=record.user_id, display_name=display_name)
            tasks = list_tasks(self.app.db, user_id=record.user_id)
            self._send_json({"ok": True, "tasks": tasks, "summary": _task_summary(tasks), "profile": profile})
        except Exception as exc:
            self._send_error(500, exc)

    def _handle_task_create(self) -> None:
        record = self._session_record()
        if not record or not record.user_id:
            self._send_json({"ok": False, "message": "Non autorizzato"}, status=401)
            return
            
        cfg = self._require_config()
        if cfg is None:
            return
        payload = self._read_json_body()
        try:
            display_name = _derive_display_name(record.profile or {})
            ensure_profile(self.app.db, user_id=record.user_id, display_name=display_name)
            task = create_task(
                self.app.db,
                user_id=record.user_id,
                title=str(payload.get("title", "")).strip(),
                subject=str(payload.get("subject", "")).strip() or "Materia libera",
                due_date=str(payload.get("due_date", "")).strip() or date.today().isoformat(),
                category=str(payload.get("category", "compito")).strip() or "compito",
                estimated_minutes=max(15, int(payload.get("estimated_minutes") or 45)),
                difficulty=min(5, max(1, int(payload.get("difficulty") or 3))),
                priority=min(5, max(1, int(payload.get("priority") or 3))),
                notes=str(payload.get("notes", "")).strip(),
            )
            self._send_json({"ok": True, "task": task}, status=201)
        except Exception as exc:
            self._send_error(400, exc)

    def _handle_task_update(self) -> None:
        record = self._session_record()
        if not record or not record.user_id:
            self._send_json({"ok": False, "message": "Non autorizzato"}, status=401)
            return
            
        cfg = self._require_config()
        if cfg is None:
            return
        payload = self._read_json_body()
        task_id = int((self.route_path.rstrip("/") or "/").rsplit("/", 1)[-1])
        try:
            task = update_task(self.app.db, user_id=record.user_id, task_id=task_id, fields=payload)
            self._send_json({"ok": True, "task": task})
        except Exception as exc:
            self._send_error(400, exc)

    def _handle_task_delete(self) -> None:
        record = self._session_record()
        if not record or not record.user_id:
            self._send_json({"ok": False, "message": "Non autorizzato"}, status=401)
            return
            
        cfg = self._require_config()
        if cfg is None:
            return
        task_id = int((self.route_path.rstrip("/") or "/").rsplit("/", 1)[-1])
        try:
            delete_task(self.app.db, user_id=record.user_id, task_id=task_id)
            self._send_json({"ok": True})
        except Exception as exc:
            self._send_error(400, exc)

    def _handle_profile_update(self) -> None:
        record = self._session_record()
        if not record or not record.user_id:
            self._send_json({"ok": False, "message": "Non autorizzato"}, status=401)
            return
            
        cfg = self._require_config()
        if cfg is None:
            return
        payload = self._read_json_body()
        try:
            display_name = _derive_display_name(record.profile or {})
            ensure_profile(self.app.db, user_id=record.user_id, display_name=display_name)
            profile = update_profile(
                self.app.db,
                user_id=record.user_id,
                display_name=payload.get("display_name"),
                study_goal=payload.get("study_goal"),
                learning_mode=payload.get("learning_mode"),
                daily_study_minutes=payload.get("daily_study_minutes"),
                session_minutes=payload.get("session_minutes"),
            )
            self._send_json({"ok": True, "profile": profile})
        except Exception as exc:
            self._send_error(400, exc)

    def _handle_document_detail(self) -> None:
        cfg = self._require_config()
        if cfg is None:
            return

        document_hash = unquote(self.route_path.rstrip("/").rsplit("/", 1)[-1])
        filename = self._query_value("filename") or f"documento-{document_hash[:8]}"
        preview_url = f"/api/preview/document/{quote(document_hash, safe='')}?filename={quote(filename, safe='')}"
        raw_url = f"/api/download/document/{quote(document_hash, safe='')}?filename={quote(filename, safe='')}"

        payload = {
            "ok": True,
            "title": filename,
            "subtitle": "Documento ClasseViva",
            "body": (
                "Questo file viene aperto nel viewer interno quando il formato lo permette. "
                "Per PDF e immagini l'anteprima è diretta; per i .docx viene mostrata una versione HTML semplificata."
            ),
            "preview": {
                "label": "Anteprima documento",
                "url": preview_url,
                "raw_url": raw_url,
                "note": "Se il formato non è nativamente anteprimabile, vedrai comunque un fallback leggibile con il link al file originale.",
            },
            "actions": [
                {"label": "Apri nel viewer", "href": preview_url},
                {"label": "Scarica file", "href": f"{raw_url}&download=1"},
            ],
            "meta": [
                {"label": "Nome file", "value": filename},
                {"label": "Hash documento", "value": document_hash},
            ],
            "raw": {"hash": document_hash, "filename": filename},
        }
        self._send_json(payload)

    def _handle_noticeboard_detail(self) -> None:
        cfg = self._require_config()
        if cfg is None:
            return

        pub_id = self.route_path.rstrip("/").rsplit("/", 1)[-1]
        evt_code = self._query_value("evtCode")
        has_attachment = self._query_value("attachment", "0") in {"1", "true"}
        if not evt_code:
            self._send_json({"ok": False, "message": "evtCode mancante"}, status=400)
            return

        try:
            raw = asyncio.run(fetch_noticeboard_detail(cfg, evt_code, int(pub_id)))
            payload = detail_payload(raw, fallback_title=f"Circolare {pub_id}")
            if has_attachment:
                filename = self._guess_attachment_filename(raw)
                filename_query = f"&filename={quote(filename, safe='')}" if filename else ""
                preview_url = f"/api/preview/noticeboard/{pub_id}?evtCode={quote(evt_code, safe='')}{filename_query}"
                raw_url = f"/api/download/noticeboard/{pub_id}?evtCode={quote(evt_code, safe='')}{filename_query}"
                payload["preview"] = {
                    "label": "Anteprima allegato",
                    "url": preview_url,
                    "raw_url": raw_url,
                    "note": "PDF e immagini vengono aperti inline; i .docx vengono convertiti in una lettura semplificata interna.",
                }
                payload["actions"] = [
                    {"label": "Leggi allegato", "href": preview_url},
                    {"label": "Scarica allegato", "href": f"{raw_url}&download=1"},
                    *payload.get("actions", []),
                ]
            self._send_json(payload)
        except Exception as exc:
            if _noticeboard_has_no_content(exc):
                title = self._query_value("title") or f"Circolare {pub_id}"
                body = self._query_value("body") or (
                    "ClasseViva indica che questa comunicazione non ha un allegato o un contenuto apribile tramite API. "
                    "La voce resta visibile in bacheca, ma non c'è un file da mostrare nel viewer."
                )
                self._send_json(
                    {
                        "ok": True,
                        "title": title,
                        "subtitle": "Circolare senza allegato disponibile",
                        "body": body,
                        "actions": [],
                        "meta": [
                            {"label": "Pub ID", "value": pub_id},
                            {"label": "Codice evento", "value": evt_code},
                            {"label": "Stato allegato", "value": "non disponibile"},
                        ],
                        "raw": {"pubId": pub_id, "evtCode": evt_code, "no_content": True},
                    }
                )
                return
            self._send_error(500, exc)

    def _handle_didactics_detail(self) -> None:
        cfg = self._require_config()
        if cfg is None:
            return
        content_id = self.route_path.rstrip("/").rsplit("/", 1)[-1]
        try:
            raw = asyncio.run(fetch_didactics_detail(cfg, int(content_id)))
            payload = detail_payload(raw, fallback_title=f"Materiale {content_id}")
            preview_action = next((action for action in payload.get("actions", []) if str(action.get("href", "")).startswith("/api/preview/")), None)
            download_action = next((action for action in payload.get("actions", []) if "download=1" in str(action.get("href", ""))), None)
            if preview_action:
                payload["preview"] = {
                    "label": "Anteprima materiale",
                    "url": preview_action["href"],
                    "raw_url": download_action["href"] if download_action else preview_action["href"],
                    "note": "Quando il formato lo consente, il materiale viene letto direttamente nel programma.",
                }
            self._send_json(payload)
        except Exception as exc:
            self._send_error(500, exc)

    def _handle_document_preview(self) -> None:
        cfg = self._require_config()
        if cfg is None:
            return
        document_hash = unquote(self.route_path.rstrip("/").rsplit("/", 1)[-1])
        filename = self._query_value("filename") or f"documento-{document_hash[:8]}"
        raw_url = f"/api/download/document/{quote(document_hash, safe='')}?filename={quote(filename, safe='')}"
        try:
            file = asyncio.run(download_document(cfg, document_hash, fallback_name=filename))
            self._send_preview_file(file=file, raw_url=raw_url, title=filename)
        except Exception as exc:
            self._send_error(500, exc)

    def _handle_noticeboard_preview(self) -> None:
        cfg = self._require_config()
        if cfg is None:
            return

        pub_id = int(self.route_path.rstrip("/").rsplit("/", 1)[-1])
        evt_code = self._query_value("evtCode")
        filename = self._query_value("filename") or f"circolare-{pub_id}.bin"
        raw_url = f"/api/download/noticeboard/{pub_id}?evtCode={quote(evt_code, safe='') if evt_code else ''}&filename={quote(filename, safe='')}"
        try:
            file = asyncio.run(download_noticeboard_attachment(cfg, pub_id, evt_code=evt_code, fallback_name=filename))
            self._send_preview_file(file=file, raw_url=raw_url, title=f"Circolare {pub_id}")
        except Exception as exc:
            if _noticeboard_has_no_content(exc):
                body = _noticeboard_empty_html(title=f"Circolare {pub_id}", pub_id=pub_id)
                self._send_text(body, content_type="text/html; charset=utf-8")
                return
            self._send_error(500, exc)

    def _handle_document_download(self) -> None:
        cfg = self._require_config()
        if cfg is None:
            return
        document_hash = unquote(self.route_path.rstrip("/").rsplit("/", 1)[-1])
        filename = self._query_value("filename")
        try:
            file = asyncio.run(download_document(cfg, document_hash, fallback_name=filename))
            self._respond_file(file)
        except Exception as exc:
            self._send_error(500, exc)

    def _handle_noticeboard_download(self) -> None:
        cfg = self._require_config()
        if cfg is None:
            return
        pub_id = int(self.route_path.rstrip("/").rsplit("/", 1)[-1])
        filename = self._query_value("filename") or f"circolare-{pub_id}.bin"
        evt_code = self._query_value("evtCode")
        try:
            file = asyncio.run(download_noticeboard_attachment(cfg, pub_id, evt_code=evt_code, fallback_name=filename))
            self._respond_file(file)
        except Exception as exc:
            if _noticeboard_has_no_content(exc):
                self._send_error(
                    404,
                    {
                        "ok": False,
                        "error_type": "AllegatoNonDisponibile",
                        "message": "Questa circolare non contiene un allegato scaricabile.",
                        "hints": ["ClasseViva ha risposto che non c'e contenuto allegato per questa voce."],
                        "recoverable": True,
                    },
                )
                return
            self._send_error(500, exc)

    def _handle_resource_download(self) -> None:
        cfg = self._require_config()
        if cfg is None:
            return
        url = self._query_value("url")
        if not url:
            self._send_json({"ok": False, "message": "URL risorsa mancante"}, status=400)
            return
        try:
            file = asyncio.run(proxy_resource(cfg, url, fallback_name=self._query_value("filename")))
            self._respond_file(file)
        except Exception as exc:
            self._send_error(500, exc)

    def _handle_resource_preview(self) -> None:
        cfg = self._require_config()
        if cfg is None:
            return
        url = self._query_value("url")
        if not url:
            self._send_json({"ok": False, "message": "URL risorsa mancante"}, status=400)
            return
        filename = self._query_value("filename") or "materiale"
        raw_url = f"/api/download/resource?url={quote(url, safe='')}&filename={quote(filename, safe='')}"
        try:
            file = asyncio.run(proxy_resource(cfg, url, fallback_name=filename))
            self._send_preview_file(file=file, raw_url=raw_url, title=filename)
        except Exception as exc:
            self._send_error(500, exc)

    def _respond_file(self, file: DownloadedFile) -> None:
        self._send_bytes(
            file.content,
            content_type=file.content_type or "application/octet-stream",
            filename=file.filename,
            force_download=self._download_flag(),
        )

    def _send_preview_file(self, *, file: DownloadedFile, raw_url: str, title: str) -> None:
        body, content_type = _preview_response(file, raw_url=raw_url, title=title)
        if content_type.startswith("text/html"):
            self._send_text(body, content_type=content_type)
            return
        self._send_bytes(body, content_type=content_type, filename=file.filename, force_download=False)

    def _guess_attachment_filename(self, payload: Any) -> str | None:
        candidates: list[str] = []

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                for key, raw in value.items():
                    if isinstance(raw, str):
                        key_text = str(key).lower()
                        if "." in raw and any(token in key_text for token in ("file", "name", "attach", "alleg")):
                            candidates.append(raw)
                    visit(raw)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(payload)
        return candidates[0] if candidates else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cv-probe-web", description="Avvia la web app tutor per lo studio basata sui dati ClasseViva.")
    parser.add_argument("--host", default="127.0.0.1", help="Host di ascolto HTTP")
    parser.add_argument("--port", type=int, default=8765, help="Porta HTTP")
    parser.add_argument("--dotenv", default=".env", help="Percorso del file .env")
    return parser


def run_server(host: str, port: int, *, dotenv_path: str = ".env") -> None:
    app = ProbeWebApplication(dotenv_path=dotenv_path)
    ProbeRequestHandler.app = app
    server = ThreadingHTTPServer((host, port), ProbeRequestHandler)
    print(f"ClasseViva Probe Web disponibile su http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run_server(args.host, args.port, dotenv_path=args.dotenv)


if __name__ == "__main__":
    main()
