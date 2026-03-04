#!/usr/bin/env python3
"""
azure-poc-manager.py
Avvia o spegne automaticamente le risorse Azure di un ambiente POC.

Uso:
    python azure-poc-manager.py start  [--config poc-resources.json]
    python azure-poc-manager.py stop   [--config poc-resources.json]
    python azure-poc-manager.py status [--config poc-resources.json]
    python azure-poc-manager.py status --filter vm        # filtra per tipo
    python azure-poc-manager.py stop   --filter vm-spm    # filtra per nome

Tipi di risorsa supportati:
    vm          — Virtual Machine (deallocate per stop, no costi compute)
    aci         — Azure Container Instance
    aks         — Azure Kubernetes Service
    webapp      — App Service / Web App
    functionapp — Function App
    sql         — Azure SQL Database serverless (pause/resume)
    postgres    — Azure Database for PostgreSQL Flexible Server (stop/start)
    logicapp    — Azure Logic App workflow (disable/enable)
"""

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# ── ANSI colors ──────────────────────────────────────────────────────────────
R    = "\033[91m"
G    = "\033[92m"
Y    = "\033[93m"
B    = "\033[94m"
C    = "\033[96m"
BOLD = "\033[1m"
DIM  = "\033[2m"
RST  = "\033[0m"

SUPPORTED_TYPES = {"vm", "aci", "aks", "webapp", "appservice", "functionapp", "sql", "postgres", "logicapp"}


# ── Azure CLI wrapper ─────────────────────────────────────────────────────────
def az_run(*args: str, check: bool = True) -> Any:
    """Esegue az CLI e restituisce il risultato JSON (o stringa)."""
    cmd = ["az"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(err)
    if result.stdout.strip():
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout.strip()
    return None


def az_check_login() -> bool:
    """Verifica che az CLI sia autenticato."""
    try:
        az_run("account", "show")
        return True
    except RuntimeError:
        return False


_sub_id_cache: dict = {}

def _get_subscription_id(sub_args: list) -> str:
    """Restituisce l'ID subscription (da sub_args o dall'account corrente)."""
    if sub_args:
        return sub_args[1]  # ["--subscription", "xxxx-..."]
    if "_default" not in _sub_id_cache:
        data = az_run("account", "show")
        _sub_id_cache["_default"] = data.get("id", "") if isinstance(data, dict) else ""
    return _sub_id_cache["_default"]


# ── Operazioni per tipo risorsa ───────────────────────────────────────────────
def _start(rtype: str, name: str, rg: str, sub_args: list, resource: dict) -> str:
    if rtype == "vm":
        az_run("vm", "start", "-n", name, "-g", rg, *sub_args, "--no-wait")
        return "avvio in corso (no-wait)"
    elif rtype == "aci":
        az_run("container", "start", "-n", name, "-g", rg, *sub_args)
        return "avviato"
    elif rtype == "aks":
        az_run("aks", "start", "-n", name, "-g", rg, *sub_args, "--no-wait")
        return "avvio in corso (no-wait)"
    elif rtype in ("webapp", "appservice"):
        az_run("webapp", "start", "-n", name, "-g", rg, *sub_args)
        return "avviato"
    elif rtype == "functionapp":
        az_run("functionapp", "start", "-n", name, "-g", rg, *sub_args)
        return "avviato"
    elif rtype == "sql":
        server = resource.get("server", "")
        if not server:
            raise ValueError("campo 'server' richiesto per risorse SQL")
        az_run("sql", "db", "resume", "-n", name, "-g", rg, "-s", server, *sub_args)
        return "ripristinato (resume)"
    elif rtype == "postgres":
        az_run("postgres", "flexible-server", "start", "-n", name, "-g", rg, *sub_args)
        return "avviato"
    elif rtype == "logicapp":
        sub_id = _get_subscription_id(sub_args)
        url = f"/subscriptions/{sub_id}/resourceGroups/{rg}/providers/Microsoft.Logic/workflows/{name}/enable?api-version=2016-06-01"
        az_run("rest", "--method", "POST", "--url", url)
        return "abilitato"
    else:
        raise ValueError(f"tipo '{rtype}' non supportato")


def _stop(rtype: str, name: str, rg: str, sub_args: list, resource: dict) -> str:
    if rtype == "vm":
        # deallocate = stop + rilascia compute (no costi)
        az_run("vm", "deallocate", "-n", name, "-g", rg, *sub_args, "--no-wait")
        return "deallocazione in corso (no-wait)"
    elif rtype == "aci":
        az_run("container", "stop", "-n", name, "-g", rg, *sub_args)
        return "fermato"
    elif rtype == "aks":
        az_run("aks", "stop", "-n", name, "-g", rg, *sub_args, "--no-wait")
        return "arresto in corso (no-wait)"
    elif rtype in ("webapp", "appservice"):
        az_run("webapp", "stop", "-n", name, "-g", rg, *sub_args)
        return "fermato"
    elif rtype == "functionapp":
        az_run("functionapp", "stop", "-n", name, "-g", rg, *sub_args)
        return "fermato"
    elif rtype == "sql":
        server = resource.get("server", "")
        if not server:
            raise ValueError("campo 'server' richiesto per risorse SQL")
        az_run("sql", "db", "pause", "-n", name, "-g", rg, "-s", server, *sub_args)
        return "sospeso (pause)"
    elif rtype == "postgres":
        az_run("postgres", "flexible-server", "stop", "-n", name, "-g", rg, *sub_args)
        return "fermato"
    elif rtype == "logicapp":
        sub_id = _get_subscription_id(sub_args)
        url = f"/subscriptions/{sub_id}/resourceGroups/{rg}/providers/Microsoft.Logic/workflows/{name}/disable?api-version=2016-06-01"
        az_run("rest", "--method", "POST", "--url", url)
        return "disabilitato"
    else:
        raise ValueError(f"tipo '{rtype}' non supportato")


def _status(rtype: str, name: str, rg: str, sub_args: list, resource: dict) -> str:
    if rtype == "vm":
        data = az_run("vm", "show", "-d", "-n", name, "-g", rg, *sub_args)
        return data.get("powerState", "unknown") if isinstance(data, dict) else "unknown"
    elif rtype == "aci":
        data = az_run("container", "show", "-n", name, "-g", rg, *sub_args)
        if isinstance(data, dict):
            return data.get("instanceView", {}).get("state", "unknown")
        return "unknown"
    elif rtype == "aks":
        data = az_run("aks", "show", "-n", name, "-g", rg, *sub_args)
        if isinstance(data, dict):
            ps = data.get("powerState", {})
            return ps.get("code", "unknown") if isinstance(ps, dict) else str(ps)
        return "unknown"
    elif rtype in ("webapp", "appservice"):
        data = az_run("webapp", "show", "-n", name, "-g", rg, *sub_args)
        return data.get("state", "unknown") if isinstance(data, dict) else "unknown"
    elif rtype == "functionapp":
        data = az_run("functionapp", "show", "-n", name, "-g", rg, *sub_args)
        return data.get("state", "unknown") if isinstance(data, dict) else "unknown"
    elif rtype == "sql":
        server = resource.get("server", "")
        if not server:
            raise ValueError("campo 'server' richiesto per risorse SQL")
        data = az_run("sql", "db", "show", "-n", name, "-g", rg, "-s", server, *sub_args)
        return data.get("status", "unknown") if isinstance(data, dict) else "unknown"
    elif rtype == "postgres":
        data = az_run("postgres", "flexible-server", "show", "-n", name, "-g", rg, *sub_args)
        return data.get("state", "unknown") if isinstance(data, dict) else "unknown"
    elif rtype == "logicapp":
        sub_id = _get_subscription_id(sub_args)
        url = f"/subscriptions/{sub_id}/resourceGroups/{rg}/providers/Microsoft.Logic/workflows/{name}?api-version=2016-06-01"
        data = az_run("rest", "--method", "GET", "--url", url)
        if isinstance(data, dict):
            return data.get("properties", {}).get("state", "unknown")
        return "unknown"
    else:
        raise ValueError(f"tipo '{rtype}' non supportato per status")


# ── Handler principale per singola risorsa ───────────────────────────────────
def handle_resource(resource: dict, action: str) -> tuple[bool, str]:
    """Esegue l'azione su una risorsa. Restituisce (ok, messaggio)."""
    name  = resource.get("name", "?")
    rtype = resource.get("type", "").lower()
    rg    = resource.get("resource_group", "")
    sub   = resource.get("subscription")

    if not name or not rtype or not rg:
        return False, "campi 'name', 'type', 'resource_group' obbligatori"

    if rtype not in SUPPORTED_TYPES:
        return False, f"tipo '{rtype}' non supportato"

    sub_args = ["--subscription", sub] if sub else []

    try:
        if action == "start":
            msg = _start(rtype, name, rg, sub_args, resource)
        elif action == "stop":
            msg = _stop(rtype, name, rg, sub_args, resource)
        elif action == "status":
            msg = _status(rtype, name, rg, sub_args, resource)
        else:
            return False, f"azione non valida: {action}"
        return True, msg
    except Exception as e:
        return False, str(e)


# ── Output helpers ────────────────────────────────────────────────────────────
_STATE_COLORS = {
    "running":        G,
    "vm running":     G,
    "Running":        G,
    "Started":        G,
    "Enabled":        G,
    "succeeded":      G,
    "Online":         G,
    "ready":          G,
    "stopped":        Y,
    "vm stopped":     Y,
    "vm deallocated": Y,
    "Stopped":        Y,
    "deallocated":    Y,
    "Paused":         Y,
    "Disabled":       Y,
    "failed":         R,
    "Failed":         R,
    "error":          R,
}

def state_color(state: str) -> str:
    sl = state.lower()
    for k, c in _STATE_COLORS.items():
        if k.lower() in sl:
            return c
    return C  # cyan per stati sconosciuti/in transizione


def print_banner(action: str, count: int):
    bar = "─" * 56
    icons = {"start": "▶", "stop": "■", "status": "●"}
    icon = icons.get(action, "•")
    print(f"\n{BOLD}{bar}{RST}")
    print(f"{BOLD}  {icon}  Azure POC Manager — {action.upper()}  ({count} risorse){RST}")
    print(f"{BOLD}{bar}{RST}\n")


def print_result(resource: dict, ok: bool, msg: str, action: str):
    rtype = resource["type"].upper().ljust(12)
    name  = resource["name"].ljust(32)
    rg    = f"{DIM}[{resource['resource_group']}]{RST}"

    if ok:
        if action == "status":
            color = state_color(msg)
            status_icon = "●"
            print(f"  {color}{status_icon}{RST}  {BOLD}{rtype}{RST} {name} {color}{msg}{RST}  {rg}")
        else:
            print(f"  {G}✓{RST}  {BOLD}{rtype}{RST} {name} {DIM}{msg}{RST}  {rg}")
    else:
        print(f"  {R}✗{RST}  {BOLD}{rtype}{RST} {name} {R}{msg}{RST}  {rg}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Azure POC Resource Manager — start/stop/status risorse in blocco",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "action", choices=["start", "stop", "status"],
        help="Azione da eseguire su tutte le risorse"
    )
    parser.add_argument(
        "--config", "-c", default="poc-resources.json",
        help="File JSON con la lista delle risorse (default: poc-resources.json)"
    )
    parser.add_argument(
        "--parallel", "-p", type=int, default=6,
        help="Numero di operazioni in parallelo (default: 6)"
    )
    parser.add_argument(
        "--filter", "-f",
        help="Filtra risorse per nome o tipo (substring match, case-insensitive)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Mostra cosa verrebbe eseguito senza fare nulla"
    )
    args = parser.parse_args()

    # ── Carica config
    config_path = Path(args.config)
    if not config_path.exists():
        # prova a cercarlo nella stessa directory dello script
        config_path = Path(__file__).parent / args.config
    if not config_path.exists():
        print(f"{R}Errore: config non trovato: {args.config}{RST}")
        print(f"       Crea poc-resources.json partendo da poc-resources.example.json")
        sys.exit(1)

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"{R}Errore JSON in {config_path}: {e}{RST}")
        sys.exit(1)

    resources = config.get("resources", [])

    # ── Filtra
    if args.filter:
        f = args.filter.lower()
        resources = [
            r for r in resources
            if f in r.get("name", "").lower() or f in r.get("type", "").lower()
        ]

    if not resources:
        print(f"{Y}Nessuna risorsa trovata (filtro: {args.filter!r}).{RST}")
        sys.exit(0)

    # ── Dry-run
    if args.dry_run:
        print(f"\n{Y}{BOLD}DRY-RUN — azioni che verrebbero eseguite:{RST}\n")
        for r in resources:
            print(f"  {r['type'].upper():<12} {r['name']:<32} [{r['resource_group']}]  → {args.action}")
        print()
        sys.exit(0)

    # ── Verifica login az CLI
    if not az_check_login():
        print(f"{R}Non autenticato su Azure CLI.{RST}")
        print(f"  Esegui: {BOLD}az login{RST}  oppure  {BOLD}az login --use-device-code{RST}")
        sys.exit(1)

    print_banner(args.action, len(resources))

    # ── Esecuzione in parallelo
    results: list[tuple[dict, bool, str]] = []
    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        futures = {
            executor.submit(handle_resource, r, args.action): r
            for r in resources
        }
        for future in as_completed(futures):
            resource = futures[future]
            try:
                ok, msg = future.result()
            except Exception as e:
                ok, msg = False, str(e)
            results.append((resource, ok, msg))

    # ── Stampa risultati ordinati per nome
    results.sort(key=lambda x: x[0]["name"])
    ok_count  = sum(1 for _, ok, _ in results if ok)
    err_count = len(results) - ok_count

    for resource, ok, msg in results:
        print_result(resource, ok, msg, args.action)

    print()
    if err_count == 0:
        print(f"  {G}{BOLD}Completato: {ok_count}/{len(results)} OK{RST}")
    else:
        print(f"  {Y}{BOLD}Completato: {ok_count} OK  —  {R}{err_count} errori{RST}")
    print()

    sys.exit(0 if err_count == 0 else 1)


if __name__ == "__main__":
    main()
