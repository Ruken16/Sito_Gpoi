from __future__ import annotations

import argparse
import asyncio
from datetime import date

from .core import COMMON_METHODS, RANGE_METHODS, fetch_info, fetch_method, friendly_error, json_text, load_config, package_version


def _print(payload):
    print(json_text(payload))


async def cmd_smoke(_: argparse.Namespace) -> int:
    payload = {
        "ok": True,
        "import": True,
        "package": "Classeviva.py",
        "versione_libreria": package_version(),
        "utente_class": True,
        "metodi_principali": [
            "accedi",
            "documenti",
            "assenze",
            "lezioni_giorno",
            "voti",
            "note",
            "agenda",
            "bacheca",
        ],
    }
    _print(payload)
    return 0


async def cmd_info(args: argparse.Namespace) -> int:
    cfg = load_config(username=args.username, password=args.password, debug=bool(args.debug))
    _print(await fetch_info(cfg))
    return 0


async def cmd_simple(args: argparse.Namespace) -> int:
    cfg = load_config(username=args.username, password=args.password, debug=bool(args.debug))
    _print(await fetch_method(cfg, args.method_name))
    return 0


async def cmd_lezioni_giorno(args: argparse.Namespace) -> int:
    cfg = load_config(username=args.username, password=args.password, debug=bool(args.debug))
    selected_date = args.date or date.today().isoformat()
    _print(await fetch_method(cfg, "lezioni_giorno", selected_date))
    return 0


async def cmd_range(args: argparse.Namespace) -> int:
    cfg = load_config(username=args.username, password=args.password, debug=bool(args.debug))
    _print(await fetch_method(cfg, args.method_name, args.start, args.end))
    return 0


async def _run_async(args: argparse.Namespace) -> int:
    try:
        return await args.handler(args)
    except KeyboardInterrupt:
        _print({"ok": False, "message": "Esecuzione interrotta dall'utente"})
        return 130
    except Exception as exc:
        if getattr(args, "debug", False):
            raise
        _print(friendly_error(exc))
        return 1



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cv-probe",
        description="CLI minimale per verificare se Classeviva.py funziona nel tuo ambiente.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_flags(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--username", help="Username ClasseViva, es. S1234567X")
        subparser.add_argument("--password", help="Password ClasseViva")
        subparser.add_argument("--debug", action="store_true", help="Mostra stack trace completo in caso di errore")

    smoke = subparsers.add_parser("smoke", help="Verifica import e metodi principali della libreria")
    smoke.set_defaults(handler=cmd_smoke)

    info = subparsers.add_parser("info", help="Esegue login e mostra informazioni base della sessione")
    add_common_flags(info)
    info.set_defaults(handler=cmd_info)

    for cmd_name in COMMON_METHODS:
        if cmd_name == "info":
            continue
        p = subparsers.add_parser(cmd_name, help=COMMON_METHODS[cmd_name][0])
        add_common_flags(p)
        p.set_defaults(handler=cmd_simple, method_name=COMMON_METHODS[cmd_name][1])

    lezioni = subparsers.add_parser("lezioni-giorno", help="Recupera le lezioni di una data")
    add_common_flags(lezioni)
    lezioni.add_argument("--date", help="Data in formato YYYY-MM-DD. Default: oggi")
    lezioni.set_defaults(handler=cmd_lezioni_giorno)

    for cmd_name in RANGE_METHODS:
        p = subparsers.add_parser(cmd_name.replace("_", "-"), help=RANGE_METHODS[cmd_name][0])
        add_common_flags(p)
        p.add_argument("--start", required=True, help="Data iniziale YYYY-MM-DD")
        p.add_argument("--end", required=True, help="Data finale YYYY-MM-DD")
        p.set_defaults(handler=cmd_range, method_name=RANGE_METHODS[cmd_name][1])

    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    code = asyncio.run(_run_async(args))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
