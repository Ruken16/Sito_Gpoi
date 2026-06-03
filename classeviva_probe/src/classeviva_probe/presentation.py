from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from urllib.parse import quote


SECTION_TITLES: dict[str, str] = {
    "documenti": "Documenti",
    "assenze": "Assenze",
    "voti": "Voti",
    "note": "Note",
    "agenda": "Agenda",
    "bacheca": "Bacheca",
    "calendario": "Calendario",
    "carta": "Carta studente",
    "didattica": "Didattica",
    "libri": "Libri",
    "materie": "Materie",
    "periodi": "Periodi",
    "lezioni_giorno": "Lezioni del giorno",
    "assenze_da_a": "Assenze per intervallo",
    "agenda_da_a": "Agenda per intervallo",
    "calendario_da_a": "Calendario per intervallo",
    "lezioni_da_a": "Lezioni per intervallo",
    "panoramica_da_a": "Panoramica per intervallo",
}

SECTION_ORDER = [
    "documenti",
    "bacheca",
    "didattica",
    "voti",
    "assenze",
    "note",
    "agenda",
    "calendario",
    "lezioni_giorno",
    "lezioni_da_a",
    "panoramica_da_a",
    "materie",
    "periodi",
    "libri",
    "carta",
    "assenze_da_a",
    "agenda_da_a",
    "calendario_da_a",
]

TITLE_KEYS = (
    "title",
    "desc",
    "description",
    "eventTitle",
    "evtTitle",
    "subjectDesc",
    "subject",
    "argomento",
    "lessonArg",
    "name",
    "contentTitle",
    "cntTitle",
    "materialTitle",
)
SUBTITLE_KEYS = (
    "teacherName",
    "authorName",
    "author",
    "subjectDesc",
    "subject",
    "materia",
    "category",
    "evtCode",
    "eventCode",
)
BODY_KEYS = (
    "evtText",
    "text",
    "notes",
    "note",
    "message",
    "description",
    "details",
    "annotation",
    "lessonArg",
    "content",
    "body",
)
DATE_KEYS = (
    "evtDatetimeBegin",
    "evtDate",
    "publishDate",
    "pubDT",
    "date",
    "evtDateBegin",
    "evtDateEnd",
    "gradeDate",
    "lessonDate",
    "createdAt",
    "insertDate",
)
ID_KEYS = ("id", "pubId", "contentId", "evtId", "hash")
META_PRIORITY = (
    "subjectDesc",
    "subject",
    "materia",
    "teacherName",
    "authorName",
    "displayValue",
    "decimalValue",
    "grade",
    "value",
    "periodDesc",
    "notesForFamily",
    "evtCode",
    "status",
    "read",
    "isRead",
    "justified",
    "absenceType",
)
RESOURCE_LABELS = {
    "viewlink": "Apri",
    "confirmlink": "Apri",
    "downloadurl": "Scarica",
    "url": "Apri collegamento",
    "href": "Apri collegamento",
    "link": "Apri collegamento",
}
GRADE_VALUE_KEYS = (
    "displayValue",
    "decimalValue",
    "grade",
    "value",
    "gradeValue",
    "displayGrade",
    "evtValue",
    "formattedValue",
)
GRADE_DESCRIPTION_KEYS = (
    "notesForFamily",
    "notes",
    "note",
    "description",
    "evtText",
    "lessonArg",
    "componentDesc",
)
GRADE_DATE_KEYS = ("evtDate", "gradeDate", "date", "lessonDate", "insertDate")
AGENDA_DATE_KEYS = (
    "evtDatetimeBegin",
    "evtDateBegin",
    "evtDate",
    "date",
    "day",
    "startDate",
    "deadline",
    "dueDate",
)


def humanize_key(key: str) -> str:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key.replace("_", " "))
    return " ".join(word.capitalize() for word in spaced.split())


def compact_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "Sì" if value else "No"
    if value is None:
        return "—"
    return str(value)


def choose_first(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    lowered = {str(key).lower(): value for key, value in mapping.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, "", [], {}):
            return value
    return None


def parse_date_value(value: Any) -> date | None:
    if value in (None, "", [], {}):
        return None
    text = str(value).strip()
    formats = (
        ("%Y-%m-%dT%H:%M:%S", 19),
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y-%m-%d", 10),
        ("%Y%m%d", 8),
        ("%d/%m/%Y", 10),
    )
    for fmt, length in formats:
        try:
            return datetime.strptime(text[:length], fmt).date()
        except Exception:
            continue
    return None


def parse_time_value(value: Any) -> str | None:
    if value in (None, "", [], {}):
        return None
    text = str(value).strip()
    for fmt, length in (
        ("%Y-%m-%dT%H:%M:%S", 19),
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%H:%M:%S", 8),
        ("%H:%M", 5),
    ):
        try:
            return datetime.strptime(text[:length], fmt).strftime("%H:%M")
        except Exception:
            continue
    return None


def parse_grade_value(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    text = str(value).replace(",", ".").strip()
    if text.lower() in {"ass", "a", "nc", "n.c.", "non classificato"}:
        return None
    text = text.replace("½", ".5").replace(" ", "")
    adjustment = 0.0
    if text.endswith("+"):
        adjustment = 0.25
        text = text[:-1]
    elif text.endswith("-"):
        adjustment = -0.25
        text = text[:-1]
    try:
        return round(float(text) + adjustment, 2)
    except ValueError:
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        if not match:
            return None
        try:
            return round(float(match.group(1)) + adjustment, 2)
        except ValueError:
            return None


def grade_contributes_to_average(item: dict[str, Any]) -> bool:
    color = str(item.get("color") or "").strip().lower()
    if bool(item.get("canceled")):
        return False
    if color == "blue":
        return False
    weight = item.get("weightFactor")
    if weight in (0, "0", 0.0, "0.0"):
        return False
    return True


def looks_like_url(value: str) -> bool:
    return value.startswith(("http://", "https://", "/"))


def flatten_payload(payload: Any, *, group: str | None = None) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        items: list[dict[str, Any]] = []
        for index, value in enumerate(payload, start=1):
            if isinstance(value, dict):
                items.append({"group": group, "value": value, "index": index})
            else:
                items.append({"group": group, "value": {"value": value}, "index": index})
        return items
    if isinstance(payload, dict):
        flattened: list[dict[str, Any]] = []
        contains_lists = any(isinstance(value, list) for value in payload.values())
        if contains_lists:
            for key, value in payload.items():
                flattened.extend(flatten_payload(value, group=humanize_key(str(key))))
            return flattened
        return [{"group": group, "value": payload, "index": 1}]
    return [{"group": group, "value": {"value": payload}, "index": 1}]


def _sanitize_text(value: Any) -> str:
    text = compact_scalar(value)
    return re.sub(r"\s+", " ", text).strip()


def guess_title(item: dict[str, Any], fallback: str) -> str:
    chosen = choose_first(item, TITLE_KEYS)
    if isinstance(chosen, str):
        text = _sanitize_text(chosen)
        if text:
            return text
    for key in ("grade", "value", "hash"):
        value = item.get(key)
        if value not in (None, ""):
            return f"{humanize_key(key)} {value}"
    return fallback


def guess_subtitle(item: dict[str, Any]) -> str | None:
    chosen = choose_first(item, SUBTITLE_KEYS)
    if isinstance(chosen, str):
        text = _sanitize_text(chosen)
        return text or None
    return None


def guess_date(item: dict[str, Any]) -> str | None:
    chosen = choose_first(item, DATE_KEYS)
    if chosen in (None, ""):
        return None
    parsed = parse_date_value(chosen)
    return parsed.strftime("%d/%m/%Y") if parsed else str(chosen).strip()


def guess_date_iso(item: dict[str, Any], keys: tuple[str, ...] = DATE_KEYS) -> str | None:
    chosen = choose_first(item, keys)
    parsed = parse_date_value(chosen)
    return parsed.isoformat() if parsed else None


def guess_time(item: dict[str, Any]) -> str | None:
    for key in ("evtDatetimeBegin", "evtDatetimeEnd", "time", "startTime", "endTime"):
        parsed = parse_time_value(item.get(key))
        if parsed:
            return parsed
    return None


def guess_body(item: dict[str, Any]) -> str | None:
    for key in BODY_KEYS:
        value = choose_first(item, (key,))
        if isinstance(value, str):
            text = value.strip()
            if len(text) > 12:
                return text
    longest = ""
    for value in item.values():
        if isinstance(value, str) and len(value.strip()) > len(longest):
            longest = value.strip()
    return longest or None


def guess_id(item: dict[str, Any], index: int) -> str:
    for key in ID_KEYS:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return f"item-{index}"


def attachment_count(payload: Any) -> int:
    if isinstance(payload, dict):
        total = 0
        for key, value in payload.items():
            key_text = str(key).lower()
            if "attach" in key_text or "alleg" in key_text or "file" in key_text:
                if isinstance(value, bool):
                    total += 1 if value else 0
                elif isinstance(value, int):
                    total += value
                elif isinstance(value, list):
                    total += len(value)
                elif value not in (None, "", {}):
                    total += 1
            total += attachment_count(value)
        return total
    if isinstance(payload, list):
        return sum(attachment_count(item) for item in payload)
    return 0


def build_meta(item: dict[str, Any], *, group: str | None = None) -> list[dict[str, str]]:
    meta: list[dict[str, str]] = []
    if group:
        meta.append({"label": "Gruppo", "value": group})

    for key in META_PRIORITY:
        value = item.get(key)
        if value not in (None, "", [], {}):
            meta.append({"label": humanize_key(key), "value": compact_scalar(value)})

    for key, value in item.items():
        if key in META_PRIORITY or key in TITLE_KEYS or key in SUBTITLE_KEYS or key in BODY_KEYS:
            continue
        if len(meta) >= 6:
            break
        if isinstance(value, (list, dict)) or value in (None, "", []):
            continue
        meta.append({"label": humanize_key(str(key)), "value": compact_scalar(value)})
    return meta[:6]


def dedupe_actions(actions: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    output: list[dict[str, str]] = []
    for action in actions:
        key = (action.get("label", ""), action.get("href", ""))
        if key in seen or not key[1]:
            continue
        seen.add(key)
        output.append(action)
    return output


def resource_actions(payload: Any) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []

    def visit(value: Any, context: dict[str, Any] | None = None) -> None:
        if isinstance(value, dict):
            lowered = {str(key).lower(): raw for key, raw in value.items()}
            doc_hash = lowered.get("hash")
            if isinstance(doc_hash, str) and doc_hash:
                filename = choose_first(value, ("filename", "fileName", "name", "desc", "title"))
                safe_name = quote(str(filename or doc_hash))
                quoted_hash = quote(doc_hash)
                actions.append(
                    {
                        "label": "Leggi nel programma",
                        "href": f"/api/details/document/{quoted_hash}?filename={safe_name}",
                    }
                )
                actions.append(
                    {
                        "label": "Apri in pagina",
                        "href": f"/api/preview/document/{quoted_hash}?filename={safe_name}",
                    }
                )
                actions.append(
                    {
                        "label": "Scarica documento",
                        "href": f"/api/download/document/{quoted_hash}?filename={safe_name}&download=1",
                    }
                )
            for key, raw in value.items():
                label = RESOURCE_LABELS.get(str(key).lower(), "Apri allegato")
                if isinstance(raw, str) and looks_like_url(raw):
                    filename = choose_first(value, ("filename", "fileName", "name", "title"))
                    if "spaggiari.eu" in raw or raw.startswith("/"):
                        safe_name = quote(str(filename or "risorsa"))
                        preview_href = f"/api/preview/resource?url={quote(raw, safe='')}&filename={safe_name}"
                        download_href = f"/api/download/resource?url={quote(raw, safe='')}&filename={safe_name}&download=1"
                        actions.append(
                            {
                                "label": "Leggi nel viewer",
                                "href": preview_href,
                            }
                        )
                        actions.append(
                            {
                                "label": "Scarica materiale",
                                "href": download_href,
                            }
                        )
                    else:
                        actions.append({"label": label, "href": raw})
                else:
                    visit(raw, value)
            return

        if isinstance(value, list):
            for item in value:
                visit(item, context)

    visit(payload)
    return dedupe_actions(actions)


def build_card(item: dict[str, Any], *, index: int, group: str | None = None, fallback_prefix: str = "Elemento") -> dict[str, Any]:
    title = guess_title(item, f"{fallback_prefix} {index}")
    subtitle = guess_subtitle(item)
    badges: list[str] = []
    date_text = guess_date(item)
    date_iso = guess_date_iso(item)
    time_text = guess_time(item)
    if date_text:
        badges.append(date_text)
    if time_text:
        badges.append(time_text)
    if attachment_count(item):
        badges.append(f"{attachment_count(item)} allegati")

    return {
        "id": guess_id(item, index),
        "title": title,
        "subtitle": subtitle,
        "body": guess_body(item),
        "badges": badges,
        "date_iso": date_iso,
        "date_text": date_text,
        "time": time_text,
        "meta": build_meta(item, group=group),
        "actions": resource_actions(item),
        "raw": item,
    }


def error_section(title: str, error: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": False,
        "kind": "error",
        "title": title,
        "count": 0,
        "error": error,
    }


def normalize_documents(payload: dict[str, Any]) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    total = 0
    for key, value in payload.items():
        entries = value if isinstance(value, list) else [value]
        items = [build_card(item if isinstance(item, dict) else {"value": item}, index=i, group=humanize_key(str(key)), fallback_prefix=humanize_key(str(key))) for i, item in enumerate(entries, start=1)]
        total += len(items)
        groups.append(
            {
                "title": humanize_key(str(key)),
                "count": len(items),
                "items": items,
            }
        )

    return {
        "ok": True,
        "kind": "documents",
        "title": SECTION_TITLES["documenti"],
        "summary": f"{total} file o voci documentali disponibili",
        "count": total,
        "groups": groups,
        "raw": payload,
    }


def normalize_cards_section(key: str, payload: Any) -> dict[str, Any]:
    flattened = flatten_payload(payload)
    items = [
        build_card(entry["value"], index=entry["index"], group=entry["group"], fallback_prefix=SECTION_TITLES.get(key, "Elemento"))
        for entry in flattened
    ]
    return {
        "ok": True,
        "kind": "cards",
        "title": SECTION_TITLES.get(key, humanize_key(key)),
        "summary": f"{len(items)} elementi",
        "count": len(items),
        "items": items,
        "raw": payload,
    }


def normalize_grades(payload: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        subject = compact_scalar(item.get("subjectDesc") or item.get("subject") or "Materia non indicata")
        teacher = compact_scalar(item.get("teacherName") or item.get("teacher") or "Docente non indicato")
        grade_value = choose_first(item, GRADE_VALUE_KEYS)
        grade = compact_scalar(grade_value or "—")
        numeric_grade = parse_grade_value(grade_value)
        description_value = choose_first(item, GRADE_DESCRIPTION_KEYS)
        description = str(description_value).strip() if description_value not in (None, "", [], {}) else ""
        date_iso = guess_date_iso(item, GRADE_DATE_KEYS)
        date_text = parse_date_value(choose_first(item, GRADE_DATE_KEYS))
        period_position = item.get("periodPos")
        period_label = compact_scalar(item.get("periodDesc") or (f"Periodo {period_position}" if period_position not in (None, "") else "Tutto l'anno"))
        period_key = f"period-{period_position}" if period_position not in (None, "") else f"period-{period_label.lower()}"
        component = compact_scalar(item.get("componentDesc") or item.get("component") or "")
        contributes_to_average = grade_contributes_to_average(item)
        color = str(item.get("color") or "").strip().lower()
        badges = [
            badge
            for badge in (
                date_text.strftime("%d/%m/%Y") if date_text else None,
                period_label,
                component or None,
                None if contributes_to_average else "non fa media",
            )
            if badge
        ]

        items.append(
            {
                "id": guess_id(item, index),
                "title": subject,
                "subtitle": teacher,
                "body": description or None,
                "badges": badges,
                "meta": [],
                "actions": [],
                "raw": item,
                "subject": subject,
                "teacher": teacher,
                "grade": grade,
                "display_grade": grade,
                "numeric_grade": numeric_grade,
                "description": description,
                "date_iso": date_iso,
                "date_text": date_text.strftime("%d/%m/%Y") if date_text else "",
                "period_key": period_key,
                "period_label": period_label,
                "component": component,
                "color": color,
                "contributes_to_average": contributes_to_average,
                "canceled": bool(item.get("canceled")),
                "weight_factor": item.get("weightFactor"),
            }
        )

    return {
        "ok": True,
        "kind": "grades",
        "title": SECTION_TITLES["voti"],
        "summary": f"{len(items)} voti registrati",
        "count": len(items),
        "items": items,
        "raw": payload,
    }


def normalize_record_section(key: str, payload: dict[str, Any]) -> dict[str, Any]:
    fields = [
        {"label": humanize_key(str(field)), "value": compact_scalar(value)}
        for field, value in payload.items()
        if not isinstance(value, (list, dict))
    ]
    nested = {
        field: value
        for field, value in payload.items()
        if isinstance(value, (list, dict))
    }
    return {
        "ok": True,
        "kind": "record",
        "title": SECTION_TITLES.get(key, humanize_key(key)),
        "summary": f"{len(fields)} campi principali",
        "count": len(fields),
        "fields": fields,
        "nested": nested,
        "raw": payload,
    }


def normalize_agenda(key: str, payload: Any) -> dict[str, Any]:
    flattened = flatten_payload(payload)
    today = date.today()
    items: list[dict[str, Any]] = []
    for entry in flattened:
        item = entry["value"]
        card = build_card(item, index=entry["index"], group=entry["group"], fallback_prefix=SECTION_TITLES.get(key, "Agenda"))
        agenda_day = parse_date_value(choose_first(item, AGENDA_DATE_KEYS))
        card["date_iso"] = agenda_day.isoformat() if agenda_day else card.get("date_iso")
        card["date_text"] = agenda_day.strftime("%d/%m/%Y") if agenda_day else card.get("date_text")
        card["time"] = guess_time(item)
        card["importance"] = "near"
        if agenda_day:
            delta = (agenda_day - today).days
            if delta < 0:
                card["importance"] = "past"
            elif delta <= 2:
                card["importance"] = "urgent"
            elif delta <= 10:
                card["importance"] = "upcoming"
        items.append(card)

    def sort_key(card: dict[str, Any]) -> tuple[int, str, str]:
        parsed = parse_date_value(card.get("date_iso"))
        if not parsed:
            return (9999, "", str(card.get("title", "")))
        delta = (parsed - today).days
        rank = abs(delta) + (2 if delta < 0 else 0)
        return (rank, parsed.isoformat(), str(card.get("time") or ""))

    items.sort(key=sort_key)
    return {
        "ok": True,
        "kind": "agenda",
        "title": SECTION_TITLES.get(key, humanize_key(key)),
        "summary": f"{len(items)} eventi ordinati per vicinanza",
        "count": len(items),
        "items": items,
        "raw": payload,
    }


def normalize_noticeboard(payload: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for index, item in enumerate(payload, start=1):
        card = build_card(item, index=index, fallback_prefix="Circolare")
        pub_id = item.get("pubId")
        evt_code = item.get("evtCode")
        actions = list(card["actions"])
        if pub_id not in (None, "") and evt_code not in (None, ""):
            safe_title = quote(str(card.get("title") or f"Circolare {pub_id}"))
            safe_body = quote(str(card.get("body") or ""))
            actions.insert(
                0,
                {
                    "label": "Apri circolare",
                    "href": (
                        f"/api/details/noticeboard/{quote(str(pub_id))}"
                        f"?evtCode={quote(str(evt_code))}"
                        f"&attachment={'1' if attachment_count(item) else '0'}"
                        f"&title={safe_title}&body={safe_body}"
                    ),
                },
            )
        card["actions"] = dedupe_actions(actions)
        items.append(card)

    return {
        "ok": True,
        "kind": "cards",
        "title": SECTION_TITLES["bacheca"],
        "summary": f"{len(items)} circolari o comunicazioni",
        "count": len(items),
        "items": items,
        "raw": payload,
    }


def normalize_didactics(payload: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for index, item in enumerate(payload, start=1):
        card = build_card(item, index=index, fallback_prefix="Materiale")
        content_id = item.get("contentId") or item.get("id")
        actions = list(card["actions"])
        if content_id not in (None, ""):
            actions.insert(
                0,
                {
                    "label": "Leggi materiale",
                    "href": f"/api/details/didactics/{quote(str(content_id))}",
                },
            )
        card["actions"] = dedupe_actions(actions)
        items.append(card)

    return {
        "ok": True,
        "kind": "cards",
        "title": SECTION_TITLES["didattica"],
        "summary": f"{len(items)} materiali didattici",
        "count": len(items),
        "items": items,
        "raw": payload,
    }


def normalize_section(key: str, payload: Any) -> dict[str, Any]:
    if key == "documenti" and isinstance(payload, dict):
        return normalize_documents(payload)
    if key == "voti" and isinstance(payload, list):
        return normalize_grades(payload)
    if key in {"agenda", "calendario", "agenda_da_a", "calendario_da_a"}:
        return normalize_agenda(key, payload)
    if key == "bacheca" and isinstance(payload, list):
        return normalize_noticeboard(payload)
    if key == "didattica" and isinstance(payload, list):
        return normalize_didactics(payload)
    if isinstance(payload, dict) and not any(isinstance(value, list) for value in payload.values()):
        return normalize_record_section(key, payload)
    return normalize_cards_section(key, payload)


def build_overview(info: dict[str, Any], sections: dict[str, Any]) -> dict[str, Any]:
    user = info.get("utente", {}) if isinstance(info, dict) else {}
    alerts = []
    for key, section in sections.items():
        if section.get("ok"):
            continue
        alerts.append(
            {
                "title": section.get("title", humanize_key(key)),
                "message": section["error"].get("message", "Errore sconosciuto"),
                "hints": section["error"].get("hints", []),
            }
        )

    stats = [
        {"label": "Documenti", "value": sections.get("documenti", {}).get("count", 0)},
        {"label": "Circolari", "value": sections.get("bacheca", {}).get("count", 0)},
        {"label": "Materiali", "value": sections.get("didattica", {}).get("count", 0)},
        {"label": "Voti", "value": sections.get("voti", {}).get("count", 0)},
    ]

    return {
        "student_name": " ".join(filter(None, [user.get("firstName"), user.get("lastName")])),
        "student_id": user.get("ident"),
        "resolved_student_id": info.get("student_id_risolto"),
        "original_student_id": info.get("student_id_originale"),
        "status": info.get("stato"),
        "connected": info.get("connesso"),
        "seconds_left": info.get("secondi_rimasti"),
        "library_version": info.get("versione_libreria"),
        "stats": stats,
        "alerts": alerts,
    }


def present_dashboard(bundle: dict[str, Any]) -> dict[str, Any]:
    info_result = bundle.get("info", {})
    info = info_result.get("data", {}) if info_result.get("ok") else {}

    sections: dict[str, Any] = {}
    for key in SECTION_ORDER:
        result = bundle.get("sections", {}).get(key)
        if not result:
            continue
        if result.get("ok"):
            sections[key] = normalize_section(key, result.get("data"))
        else:
            sections[key] = error_section(SECTION_TITLES.get(key, humanize_key(key)), result.get("error", {}))

    return {
        "ok": True,
        "filters": bundle.get("filters", {}),
        "overview": build_overview(info, sections),
        "sections": sections,
        "section_order": [key for key in SECTION_ORDER if key in sections],
    }


def _detail_body(payload: Any) -> str | None:
    if isinstance(payload, dict):
        body = guess_body(payload)
        if body:
            return body
        for value in payload.values():
            nested = _detail_body(value)
            if nested:
                return nested
    if isinstance(payload, list):
        for item in payload:
            nested = _detail_body(item)
            if nested:
                return nested
    if isinstance(payload, str) and len(payload.strip()) > 12:
        return payload.strip()
    return None


def detail_payload(raw: Any, *, fallback_title: str, fallback_download: str | None = None) -> dict[str, Any]:
    root = raw if isinstance(raw, dict) else {"value": raw}
    actions = resource_actions(raw)
    if fallback_download:
        actions.insert(0, {"label": "Scarica allegato", "href": fallback_download})

    return {
        "ok": True,
        "title": guess_title(root, fallback_title),
        "subtitle": guess_subtitle(root),
        "body": _detail_body(raw),
        "meta": build_meta(root),
        "actions": dedupe_actions(actions),
        "raw": raw,
    }
