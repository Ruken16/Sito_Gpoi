from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import re
from typing import Any


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


def _parse_grade(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    text = str(value).replace(",", ".").strip()
    lowered = text.lower()
    if lowered in {"ass", "a", "nc", "n.c.", "non classificato"}:
        return None
    if "½" in text:
        text = text.replace("½", ".5")
    text = text.replace(" ", "")
    sign_adjustment = 0.0
    if text.endswith("+"):
        sign_adjustment = 0.25
        text = text[:-1]
    elif text.endswith("-"):
        sign_adjustment = -0.25
        text = text[:-1]
    try:
        return round(float(text) + sign_adjustment, 2)
    except ValueError:
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        if match:
            try:
                return round(float(match.group(1)) + sign_adjustment, 2)
            except ValueError:
                return None
        return None


def _first_grade_value(item: dict[str, Any]) -> Any:
    for key in GRADE_VALUE_KEYS:
        if key in item and item.get(key) not in (None, "", "-"):
            return item.get(key)
    return None


def _first_text(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return re.sub(r"\s+", " ", value).strip()
        if value not in (None, "", [], {}) and not isinstance(value, (list, dict)):
            return str(value).strip()
    return ""


def _grade_contributes_to_average(item: dict[str, Any]) -> bool:
    color = str(item.get("color") or "").strip().lower()
    if bool(item.get("canceled")):
        return False
    if color == "blue":
        return False
    weight = item.get("weightFactor")
    if weight in (0, "0", 0.0, "0.0"):
        return False
    return True


def _parse_date(value: Any) -> date | None:
    if value in (None, "", [], {}):
        return None
    text = str(value).strip()
    for fmt, length in (
        ("%Y-%m-%d", 10),
        ("%Y%m%d", 8),
        ("%d/%m/%Y", 10),
        ("%Y-%m-%dT%H:%M:%S", 19),
        ("%Y-%m-%d %H:%M:%S", 19),
    ):
        try:
            return datetime.strptime(text[:length], fmt).date()
        except Exception:
            continue
    return None


def _grade_date(item: dict[str, Any]) -> date | None:
    for key in ("evtDate", "gradeDate", "date", "lessonDate", "insertDate"):
        parsed = _parse_date(item.get(key))
        if parsed:
            return parsed
    return None


def _period_key_from_item(item: dict[str, Any]) -> str:
    position = item.get("periodPos")
    description = item.get("periodDesc")
    if position not in (None, ""):
        return f"period-{position}"
    if description not in (None, ""):
        return f"period-{str(description).strip().lower()}"
    return "all"


def _period_label_from_item(item: dict[str, Any]) -> str:
    description = _first_text(item, ("periodDesc",))
    if description:
        return description
    position = item.get("periodPos")
    if position not in (None, ""):
        return f"Periodo {position}"
    return "Tutto l'anno"


def _normalize_periods(raw_periods: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_periods, list):
        return []

    periods: list[dict[str, Any]] = []
    for index, item in enumerate(raw_periods, start=1):
        if not isinstance(item, dict):
            continue
        position = item.get("periodPos") or item.get("pos") or item.get("id") or index
        description = _first_text(item, ("periodDesc", "desc", "description", "name", "title")) or f"Periodo {position}"
        start = None
        end = None
        for key in ("dateStart", "startDate", "from", "periodStart", "dtStart", "start"):
            start = _parse_date(item.get(key))
            if start:
                break
        for key in ("dateEnd", "endDate", "to", "periodEnd", "dtEnd", "end"):
            end = _parse_date(item.get(key))
            if end:
                break

        periods.append(
            {
                "key": f"period-{position}",
                "position": position,
                "label": description,
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
                "raw": item,
            }
        )
    return periods


def _period_for_grade(item: dict[str, Any], periods: list[dict[str, Any]]) -> tuple[str, str]:
    direct_key = _period_key_from_item(item)
    direct_label = _period_label_from_item(item)
    if direct_key != "all":
        return direct_key, direct_label

    grade_day = _grade_date(item)
    if grade_day:
        for period in periods:
            start = _parse_date(period.get("start"))
            end = _parse_date(period.get("end"))
            if start and end and start <= grade_day <= end:
                return period["key"], period["label"]

    return "all", "Tutto l'anno"


def _average_rows(subject_values: dict[str, list[float]]) -> list[dict[str, Any]]:
    rows = [
        {
            "subject": subject,
            "average": round(sum(values) / len(values), 2),
            "count": len(values),
        }
        for subject, values in subject_values.items()
        if values
    ]
    rows.sort(key=lambda item: item["average"])
    return rows


def _overall_from_values(subject_values: dict[str, list[float]]) -> float | None:
    values = [value for rows in subject_values.values() for value in rows]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def build_performance_snapshot(sections: dict[str, Any]) -> dict[str, Any]:
    votes_result = sections.get("voti", {})
    absences_result = sections.get("assenze", {})
    notes_result = sections.get("note", {})
    periods_result = sections.get("periodi", {})

    grades = votes_result.get("data", []) if votes_result.get("ok") else []
    absences = absences_result.get("data", []) if absences_result.get("ok") else []
    notes = notes_result.get("data", {}) if notes_result.get("ok") else {}
    periods = _normalize_periods(periods_result.get("data", []) if periods_result.get("ok") else [])

    subject_values: dict[str, list[float]] = defaultdict(list)
    period_subject_values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    period_labels: dict[str, str] = {period["key"]: period["label"] for period in periods}
    recent_grades: list[dict[str, Any]] = []

    for item in grades:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subjectDesc") or item.get("subject") or "Materia non indicata")
        value = _parse_grade(_first_grade_value(item))
        period_key, period_label = _period_for_grade(item, periods)
        period_labels[period_key] = period_label
        contributes_to_average = _grade_contributes_to_average(item)
        if value is not None and contributes_to_average:
            subject_values[subject].append(value)
            period_subject_values[period_key][subject].append(value)
        recent_grades.append(
            {
                "subject": subject,
                "grade": value,
                "display_grade": _first_text(item, GRADE_VALUE_KEYS) or str(value),
                "description": _first_text(item, GRADE_DESCRIPTION_KEYS),
                "teacher": _first_text(item, ("teacherName", "teacher")) or "Docente non indicato",
                "date": item.get("evtDate") or item.get("gradeDate") or "",
                "period_key": period_key,
                "period_label": period_label,
                "contributes_to_average": contributes_to_average,
                "color": str(item.get("color") or ""),
            }
        )

    all_subject_averages = _average_rows(subject_values)
    all_overall_average = _overall_from_values(subject_values)

    period_averages: list[dict[str, Any]] = []
    for period_key, values_by_subject in period_subject_values.items():
        subject_averages = _average_rows(values_by_subject)
        period_averages.append(
            {
                "key": period_key,
                "label": period_labels.get(period_key, "Periodo"),
                "overall_average": _overall_from_values(values_by_subject),
                "subject_averages": subject_averages,
                "count": sum(len(values) for values in values_by_subject.values()),
            }
        )

    known_order = {period["key"]: index for index, period in enumerate(periods)}
    period_averages.sort(key=lambda item: (known_order.get(item["key"], 999), str(item["label"])))

    today = date.today()
    current_period_key = None
    for period in periods:
        start = _parse_date(period.get("start"))
        end = _parse_date(period.get("end"))
        if start and end and start <= today <= end:
            current_period_key = period["key"]
            break
    if not current_period_key and period_averages:
        current_period_key = period_averages[-1]["key"]

    active_period = next((item for item in period_averages if item["key"] == current_period_key), None)
    subject_averages = active_period["subject_averages"] if active_period else all_subject_averages
    overall_average = active_period["overall_average"] if active_period else all_overall_average

    risk_subjects = [item for item in subject_averages if item["average"] < 6.5][:3]
    strong_subjects = sorted(subject_averages, key=lambda item: item["average"], reverse=True)[:3]

    notes_count = 0
    if isinstance(notes, dict):
        for value in notes.values():
            if isinstance(value, list):
                notes_count += len(value)

    return {
        "overall_average": overall_average,
        "overall_all_periods": all_overall_average,
        "subject_averages": subject_averages,
        "subject_averages_all_periods": all_subject_averages,
        "periods": periods,
        "period_averages": period_averages,
        "active_period_key": current_period_key,
        "active_period_label": active_period["label"] if active_period else "Tutto l'anno",
        "risk_subjects": risk_subjects,
        "strong_subjects": strong_subjects,
        "grades_total_count": len([item for item in grades if isinstance(item, dict)]),
        "grades_for_average_count": sum(1 for item in recent_grades if item.get("grade") is not None and item.get("contributes_to_average")),
        "recent_grades": sorted(recent_grades, key=lambda item: item["date"], reverse=True)[:8],
        "absences_count": len(absences) if isinstance(absences, list) else 0,
        "notes_count": notes_count,
    }


def _task_weight(task: dict[str, Any], today: date) -> tuple[int, int, int]:
    due = datetime.strptime(task["due_date"], "%Y-%m-%d").date()
    days_left = (due - today).days
    priority = int(task.get("priority") or 3)
    difficulty = int(task.get("difficulty") or 3)
    urgency_rank = 0 if days_left < 0 else 1 if days_left <= 1 else 2 if days_left <= 3 else 3
    return (urgency_rank, -priority, -difficulty)


def build_study_plan(tasks: list[dict[str, Any]], profile: dict[str, Any], performance: dict[str, Any]) -> dict[str, Any]:
    today = date.today()
    active_tasks = [task for task in tasks if task.get("status") != "done"]
    active_tasks.sort(key=lambda task: _task_weight(task, today))

    daily_minutes = int(profile.get("daily_study_minutes") or 120)
    session_minutes = max(20, int(profile.get("session_minutes") or 40))
    if profile.get("learning_mode") == "dsa":
        session_minutes = min(session_minutes, 30)
        daily_minutes = int(daily_minutes * 0.9)

    plan_days: list[dict[str, Any]] = []
    pending = [dict(task) for task in active_tasks]

    for offset in range(7):
        current_day = today + timedelta(days=offset)
        remaining = daily_minutes
        sessions: list[dict[str, Any]] = []
        index = 0
        while index < len(pending) and remaining >= 20:
            task = pending[index]
            left = int(task.get("remaining_minutes") or task.get("estimated_minutes") or session_minutes)
            allocation = min(session_minutes, left, remaining)
            sessions.append(
                {
                    "task_id": task["id"],
                    "title": task["title"],
                    "subject": task["subject"],
                    "minutes": allocation,
                    "category": task["category"],
                }
            )
            left -= allocation
            remaining -= allocation
            if left <= 0:
                pending.pop(index)
            else:
                task["remaining_minutes"] = left
                pending[index] = task
                index += 1

        if not sessions and offset < 3 and performance.get("risk_subjects"):
            focus = performance["risk_subjects"][0]["subject"]
            sessions.append(
                {
                    "task_id": None,
                    "title": f"Sessione di recupero {focus}",
                    "subject": focus,
                    "minutes": min(session_minutes, daily_minutes),
                    "category": "recupero",
                }
            )
            remaining = max(0, remaining - min(session_minutes, daily_minutes))

        plan_days.append(
            {
                "date": current_day.isoformat(),
                "label": current_day.strftime("%d/%m"),
                "planned_minutes": daily_minutes - remaining,
                "available_minutes": daily_minutes,
                "sessions": sessions,
            }
        )

    completion_ratio = 0.0
    if tasks:
        done = sum(1 for task in tasks if task.get("status") == "done")
        completion_ratio = round(done / len(tasks), 2)

    return {
        "days": plan_days,
        "session_minutes": session_minutes,
        "daily_minutes": daily_minutes,
        "completion_ratio": completion_ratio,
        "overdue_count": sum(1 for task in active_tasks if task["due_date"] < today.isoformat()),
    }


def build_tutor_suggestions(tasks: list[dict[str, Any]], performance: dict[str, Any], plan: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []

    overdue = [task for task in tasks if task.get("status") != "done" and task["due_date"] < date.today().isoformat()]
    if overdue:
        suggestions.append(
            {
                "title": "Riduci il backlog",
                "body": f"Hai {len(overdue)} attività scadute: conviene dedicare la prima sessione di oggi al recupero.",
                "tone": "warning",
            }
        )

    if performance.get("risk_subjects"):
        weakest = performance["risk_subjects"][0]
        suggestions.append(
            {
                "title": f"Priorità su {weakest['subject']}",
                "body": f"La media attuale è {weakest['average']}. Inserisci sessioni brevi ma frequenti nei prossimi 3 giorni.",
                "tone": "focus",
            }
        )

    if performance.get("overall_average") is not None and performance["overall_average"] >= 7:
        suggestions.append(
            {
                "title": "Rendimento in buona forma",
                "body": f"La media generale è {performance['overall_average']}. Mantieni il ritmo alternando materie forti e deboli.",
                "tone": "success",
            }
        )

    total_planned = sum(day["planned_minutes"] for day in plan["days"])
    if total_planned < 180:
        suggestions.append(
            {
                "title": "Piano troppo leggero",
                "body": "Il planner ha meno di 3 ore distribuite nella settimana: aggiungi attività o aumenta i minuti giornalieri.",
                "tone": "warning",
            }
        )

    if profile.get("learning_mode") == "dsa":
        suggestions.append(
            {
                "title": "Modalità DSA attiva",
                "body": "Il piano usa sessioni più corte. Dopo ogni blocco, prenditi una pausa e usa mappe o riepiloghi visivi.",
                "tone": "neutral",
            }
        )

    if not suggestions:
        suggestions.append(
            {
                "title": "Prossimo passo",
                "body": "Aggiungi almeno un compito manuale o sincronizza i dati disponibili per ottenere suggerimenti più precisi.",
                "tone": "neutral",
            }
        )

    return suggestions[:5]


def build_leaderboard(display_name: str, performance: dict[str, Any], tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base_points = sum(12 for task in tasks if task.get("status") == "done")
    if performance.get("overall_average") is not None:
        base_points += int(performance["overall_average"] * 14)

    samples = [
        ("Sofia", 182),
        ("Luca", 170),
        ("Marta", 163),
        ("Giulia", 156),
        ("Ahmed", 148),
        ("Noemi", 139),
        ("Tommaso", 132),
        ("Elisa", 125),
        ("Riccardo", 118),
    ]
    entries = [{"name": name, "points": points} for name, points in samples]
    entries.append({"name": display_name or "Tu", "points": base_points})
    entries.sort(key=lambda item: item["points"], reverse=True)

    prizes = ["Badge Oro", "Buono libri", "Mentorship", "Badge Argento", "Badge Bronzo"]
    output = []
    for index, entry in enumerate(entries[:10], start=1):
        output.append(
            {
                "rank": index,
                "name": entry["name"],
                "points": entry["points"],
                "prize": prizes[index - 1] if index <= len(prizes) else "Top 10",
                "is_current_user": entry["name"] == (display_name or "Tu"),
            }
        )
    return output


def _section_titles(section: dict[str, Any] | None, *, limit: int = 3) -> list[str]:
    if not section or not section.get("ok"):
        return []

    titles: list[str] = []
    if section.get("kind") == "documents":
        for group in section.get("groups", []):
            for item in group.get("items", []):
                title = str(item.get("title") or "").strip()
                if title:
                    titles.append(title)
                    if len(titles) >= limit:
                        return titles
    else:
        for item in section.get("items", []):
            title = str(item.get("title") or "").strip()
            if title:
                titles.append(title)
                if len(titles) >= limit:
                    return titles
    return titles


def _task_summary(tasks: list[dict[str, Any]]) -> dict[str, int]:
    today = date.today().isoformat()
    active = [task for task in tasks if task.get("status") != "done"]
    return {
        "active": len(active),
        "done": sum(1 for task in tasks if task.get("status") == "done"),
        "overdue": sum(1 for task in active if task.get("due_date", today) < today),
        "today": sum(1 for task in active if task.get("due_date") == today),
    }


def build_tutor_brief(
    display_name: str,
    tasks: list[dict[str, Any]],
    performance: dict[str, Any],
    plan: dict[str, Any],
    profile: dict[str, Any],
    school: dict[str, Any],
) -> dict[str, Any]:
    summary = _task_summary(tasks)
    sections = school.get("sections", {})
    risk_subjects = performance.get("risk_subjects", [])
    strongest = performance.get("strong_subjects", [])
    bacheca_titles = _section_titles(sections.get("bacheca"))
    document_titles = _section_titles(sections.get("documenti"))

    cards = [
        {
            "label": "Backlog",
            "value": str(summary["active"]),
            "note": f"{summary['overdue']} in ritardo · {summary['today']} in scadenza oggi",
        },
        {
            "label": "Media",
            "value": str(performance.get("overall_average") or "n/d"),
            "note": "Panoramica del rendimento attuale",
        },
        {
            "label": "Focus",
            "value": risk_subjects[0]["subject"] if risk_subjects else (strongest[0]["subject"] if strongest else "Routine"),
            "note": "Materia che influenza di più il piano di studio",
        },
        {
            "label": "Bacheca",
            "value": str(sections.get("bacheca", {}).get("count", 0) or 0),
            "note": "Circolari e comunicazioni disponibili",
        },
    ]

    starter_prompts = [
        "Organizzami lo studio di oggi in modo sostenibile.",
        "Su quale materia dovrei concentrarmi per prima?",
        "Ci sono circolari o documenti importanti da leggere?",
        "Come posso migliorare la mia media senza accumulare stress?",
    ]
    if risk_subjects:
        starter_prompts[1] = f"Come recupero {risk_subjects[0]['subject']} questa settimana?"
    if bacheca_titles:
        starter_prompts[2] = "Riassumimi le ultime circolari importanti."
    if profile.get("learning_mode") == "dsa":
        starter_prompts[3] = "Adatta il mio piano a sessioni brevi e più visive."

    focus_subject = risk_subjects[0]["subject"] if risk_subjects else None
    strong_subject = strongest[0]["subject"] if strongest else None
    status = (
        f"Pronto per {display_name or 'lo studente'}: "
        f"{summary['active']} attività aperte, media {performance.get('overall_average') or 'n/d'}, "
        f"focus su {focus_subject or strong_subject or 'organizzazione'}."
    )

    return {
        "status": status,
        "starter_prompts": starter_prompts,
        "context_cards": cards,
        "highlights": {
            "bacheca_titles": bacheca_titles,
            "document_titles": document_titles,
            "risk_subjects": risk_subjects,
            "strong_subjects": strongest,
        },
    }


def _format_task(task: dict[str, Any]) -> str:
    return f"{task.get('title')} ({task.get('subject')}, scadenza {task.get('due_date')})"


def _find_subject_in_question(question: str, performance: dict[str, Any]) -> dict[str, Any] | None:
    lower = question.lower()
    for item in performance.get("subject_averages", []):
        subject = str(item.get("subject") or "").lower()
        if subject and subject in lower:
            return item
    return None


def build_tutor_reply(
    *,
    question: str,
    display_name: str,
    tasks: list[dict[str, Any]],
    performance: dict[str, Any],
    plan: dict[str, Any],
    profile: dict[str, Any],
    school: dict[str, Any],
) -> dict[str, Any]:
    prompt = re.sub(r"\s+", " ", question).strip()
    summary = _task_summary(tasks)
    brief = build_tutor_brief(display_name, tasks, performance, plan, profile, school)
    sections = school.get("sections", {})
    active_tasks = [task for task in tasks if task.get("status") != "done"]
    next_tasks = active_tasks[:3]
    next_days = [day for day in plan.get("days", []) if day.get("sessions")][:2]
    risk_subjects = performance.get("risk_subjects", [])
    strong_subjects = performance.get("strong_subjects", [])
    mentioned_subject = _find_subject_in_question(prompt, performance)
    lower = prompt.lower()

    topic = "Piano di studio"
    blocks: list[str] = []
    chips: list[str] = []

    if not prompt:
        blocks.append("Posso aiutarti a capire cosa studiare oggi, leggere le circolari più importanti o costruire un piano settimanale sostenibile.")

    if any(token in lower for token in ("oggi", "stud", "piano", "organ", "planner", "settim")):
        topic = "Organizzazione dello studio"
        if next_days:
            day = next_days[0]
            lines = [f"Per partire bene, oggi ti conviene seguire questo ordine:"]
            for session in day.get("sessions", [])[:3]:
                lines.append(f"• {session['title']} in {session['subject']} per circa {session['minutes']} minuti.")
            blocks.append("\n".join(lines))
            chips.append(f"{day.get('planned_minutes', 0)} min pianificati oggi")
        elif next_tasks:
            blocks.append(
                "Non ci sono sessioni già distribuite nel planner, quindi partirei da queste priorità:\n"
                + "\n".join(f"• {_format_task(task)}" for task in next_tasks)
            )
        else:
            blocks.append("In questo momento non vedo attività aperte: possiamo costruire insieme un piano partendo da una materia o da una verifica vicina.")

    if any(token in lower for token in ("compit", "agenda", "verific", "interrog", "scadenz", "cosa devo fare")):
        topic = "Agenda e compiti"
        agenda_lines = (
            _generic_section_lines(school, "agenda_da_a", limit=8)
            or _generic_section_lines(school, "agenda", limit=8)
            or _generic_section_lines(school, "calendario_da_a", limit=8)
        )
        if agenda_lines:
            blocks.append("Dall'agenda ClasseViva vedo queste voci utili:\n" + "\n".join(agenda_lines))
            chips.append(f"{len(agenda_lines)} voci agenda")
        else:
            blocks.append("In questa sessione non ho ricevuto voci agenda leggibili. Se aggiorni il periodo della pagina Agenda, posso ragionare sui compiti vicini.")

    if any(token in lower for token in ("voto", "media", "rendimento", "materia", "recuper", "miglior")):
        topic = "Rendimento scolastico"
        if mentioned_subject:
            blocks.append(
                f"Per {mentioned_subject['subject']} la media attuale è {mentioned_subject['average']} su {mentioned_subject['count']} voti. "
                "Ti conviene fare sessioni brevi ma frequenti, alternate a una materia più sicura, così abbassi il carico cognitivo."
            )
            chips.append(f"{mentioned_subject['subject']}: {mentioned_subject['average']}")
        elif risk_subjects:
            weakest = risk_subjects[0]
            blocks.append(
                f"La priorità principale è {weakest['subject']}, che al momento ha una media di {weakest['average']}. "
                "La strategia migliore è distribuire 2 o 3 ripassi ravvicinati nei prossimi giorni e collegarli ai compiti già in scadenza."
            )
            chips.append(f"Focus: {weakest['subject']}")
        elif performance.get("overall_average") is not None:
            blocks.append(
                f"La media generale è {performance['overall_average']}. "
                "In questo momento la cosa più utile è consolidare il ritmo, non aumentare il carico in modo aggressivo."
            )
            chips.append(f"Media {performance['overall_average']}")

    if any(token in lower for token in ("assenz", "ritardo", "note", "comport")):
        topic = "Monitoraggio"
        blocks.append(
            f"Dal quadro attuale risultano {performance.get('absences_count', 0)} assenze e {performance.get('notes_count', 0)} note registrate. "
            "Se vuoi, posso aiutarti a capire come compensare le giornate perse nel planner."
        )
        chips.append(f"Assenze {performance.get('absences_count', 0)}")

    if any(token in lower for token in ("circolar", "bacheca", "document", "material", "file", "alleg")):
        topic = "Comunicazioni scolastiche"
        bacheca_titles = brief["highlights"]["bacheca_titles"]
        document_titles = brief["highlights"]["document_titles"]
        if bacheca_titles:
            blocks.append("Le comunicazioni da guardare per prime sono:\n" + "\n".join(f"• {title}" for title in bacheca_titles))
            chips.append(f"{len(bacheca_titles)} circolari recenti")
        if document_titles:
            blocks.append("Tra i documenti disponibili vedo anche:\n" + "\n".join(f"• {title}" for title in document_titles))
            chips.append(f"{len(document_titles)} documenti utili")
        if not bacheca_titles and not document_titles:
            blocks.append("In questa sessione non vedo circolari o documenti leggibili da evidenziare.")

    if any(token in lower for token in ("stress", "ansia", "sopraff", "stanco", "tempo", "non ce la faccio")):
        topic = "Benessere e sostenibilità"
        session_minutes = plan.get("session_minutes") or profile.get("session_minutes") or 40
        blocks.append(
            f"Per non accumulare stress ti suggerisco blocchi da circa {session_minutes} minuti, con una pausa breve tra una sessione e l'altra. "
            "Nei prossimi giorni conviene chiudere prima le attività più vicine e lasciare in fondo quelle a bassa priorità."
        )
        chips.append(f"Sessioni da {session_minutes} min")

    if any(token in lower for token in ("genitor", "famigl")):
        topic = "Vista famiglia"
        blocks.append(
            f"Il quadro che puoi condividere in modo semplice è questo: {summary['active']} attività aperte, "
            f"media {performance.get('overall_average') or 'n/d'} e {summary['overdue']} attività in ritardo. "
            "La parte più utile da mostrare è il piano della settimana, perché rende visibile il metodo senza essere invasivo."
        )

    if not blocks:
        topic = "Sintesi del tutor"
        general_lines = ["Guardando insieme attività, rendimento e comunicazioni, queste sono le priorità migliori adesso:"]
        if next_tasks:
            general_lines.extend(f"• {_format_task(task)}" for task in next_tasks)
        if risk_subjects:
            general_lines.append(f"• Mantieni alta l'attenzione su {risk_subjects[0]['subject']}.")
            chips.append(f"Rischio: {risk_subjects[0]['subject']}")
        if strong_subjects:
            general_lines.append(f"• Usa {strong_subjects[0]['subject']} come materia ponte per non appesantire troppo la giornata.")
            chips.append(f"Punto forte: {strong_subjects[0]['subject']}")
        blocks.append("\n".join(general_lines))

    closing = "Se vuoi, nel prossimo messaggio posso trasformare questa analisi in un piano operativo molto concreto per oggi o per la settimana."
    return {
        "topic": topic,
        "content": "\n\n".join([block for block in blocks if block] + [closing]),
        "chips": chips[:4] or [card["value"] for card in brief["context_cards"][:3]],
    }
