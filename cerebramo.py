#!/usr/bin/env python3
"""CerebrAMO: routing + resource/health dashboard for DesarrollAMO.

Provider credentials remain delegated to OpenCode. Resource snapshots never read
provider secret files and unknown values stay explicitly unknown.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

VERSION = "0.2.0"
CONFIG_DIR = Path(os.environ.get("CEREBRAMO_CONFIG_DIR", Path.home() / ".config" / "cerebramo"))
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_ORDER = ["anthropic", "minimax", "openrouter"]

PROVIDER_ALIASES = {
    "claude": "anthropic",
    "anthropic": "anthropic",
    "minimax": "minimax",
    "openrouter": "openrouter",
}

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass
class Attempt:
    provider: str
    model: str | None
    ok: bool
    detail: str


@dataclass
class ResourceSnapshot:
    id: str
    name: str
    category: str
    state: str
    available: float | None = None
    maximum: float | None = None
    unit: str | None = None
    expires_at: str | None = None
    source: str = "unknown"
    checked_at: str | None = None
    detail: str | None = None

    @property
    def remaining_percent(self) -> float | None:
        if self.available is None or self.maximum in (None, 0):
            return None
        return max(0.0, min(100.0, self.available / self.maximum * 100.0))

    def as_dict(self) -> dict:
        data = asdict(self)
        data["remaining_percent"] = self.remaining_percent
        return data


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_config() -> dict:
    return {
        "version": 2,
        "provider_order": DEFAULT_ORDER.copy(),
        "models": {},
        "resources": {},
    }


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return _default_config()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_config()
    order = data.get("provider_order")
    if not isinstance(order, list) or not order:
        data["provider_order"] = DEFAULT_ORDER.copy()
    if not isinstance(data.get("models"), dict):
        data["models"] = {}
    if not isinstance(data.get("resources"), dict):
        data["resources"] = {}
    data["version"] = 2
    return data


def save_config(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(CONFIG_FILE)
    os.chmod(CONFIG_FILE, 0o600)


def normalize_provider(name: str) -> str:
    key = name.strip().lower()
    if key not in PROVIDER_ALIASES:
        raise ValueError(f"Proveedor no soportado: {name}")
    return PROVIDER_ALIASES[key]


def default_runner(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )


def opencode_exists() -> bool:
    return shutil.which("opencode") is not None


def provider_models(provider: str, runner: Runner = default_runner) -> list[str]:
    cp = runner(["opencode", "models", provider])
    if cp.returncode != 0:
        return []
    models: list[str] = []
    for raw in cp.stdout.splitlines():
        line = raw.strip()
        if not line or "/" not in line:
            continue
        token = line.split()[0]
        if token.startswith(provider + "/"):
            models.append(token)
    return models


def auth_list(runner: Runner = default_runner) -> str:
    cp = runner(["opencode", "auth", "list"])
    return ((cp.stdout or "") + (cp.stderr or "")).strip()


def auth_provider(provider: str) -> int:
    if not opencode_exists():
        print("ERROR: OpenCode no está instalado o no está en PATH.", file=sys.stderr)
        return 2
    provider = normalize_provider(provider)
    return subprocess.run(["opencode", "auth", "login", "--provider", provider], check=False).returncode


def set_order(names: Iterable[str]) -> None:
    order = [normalize_provider(x) for x in names]
    if len(set(order)) != len(order):
        raise ValueError("El orden contiene proveedores repetidos.")
    cfg = load_config()
    cfg["provider_order"] = order
    save_config(cfg)


def set_model(provider: str, model: str) -> None:
    provider = normalize_provider(provider)
    if not model.startswith(provider + "/"):
        raise ValueError(f"El modelo debe comenzar por '{provider}/'.")
    cfg = load_config()
    cfg["models"][provider] = model
    save_config(cfg)


def choose_model(provider: str, cfg: dict, runner: Runner = default_runner) -> str | None:
    configured = cfg.get("models", {}).get(provider)
    if configured:
        return configured
    models = provider_models(provider, runner)
    return models[0] if models else None


def run_prompt(prompt: str, *, provider: str | None = None, model: str | None = None,
               runner: Runner = default_runner) -> tuple[int, list[Attempt], str]:
    cfg = load_config()
    providers = [normalize_provider(provider)] if provider else list(cfg["provider_order"])
    attempts: list[Attempt] = []
    for current in providers:
        chosen = model if provider and model else choose_model(current, cfg, runner)
        if not chosen:
            attempts.append(Attempt(current, None, False, "sin modelo disponible"))
            continue
        cp = runner(["opencode", "run", "--model", chosen, "--format", "json", prompt])
        if cp.returncode == 0:
            attempts.append(Attempt(current, chosen, True, "ok"))
            return 0, attempts, cp.stdout
        detail = (cp.stderr or cp.stdout or f"exit {cp.returncode}").strip()
        attempts.append(Attempt(current, chosen, False, detail[-500:]))
    return 1, attempts, ""


def _meminfo(path: Path = Path("/proc/meminfo")) -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            amount = int(raw.strip().split()[0])
            values[key] = amount * 1024
    except (OSError, ValueError, IndexError):
        return {}
    return values


def collect_local_resources(*, root: str = "/", meminfo_path: Path = Path("/proc/meminfo"),
                            uptime_path: Path = Path("/proc/uptime")) -> list[ResourceSnapshot]:
    checked = utc_now()
    out: list[ResourceSnapshot] = []
    mem = _meminfo(meminfo_path)
    if mem.get("MemTotal"):
        total = float(mem["MemTotal"])
        available = float(mem.get("MemAvailable", mem.get("MemFree", 0)))
        out.append(ResourceSnapshot("host.ram", "RAM host", "host", "ok", available, total,
                                    "bytes", source="local:/proc/meminfo", checked_at=checked))
    if mem.get("SwapTotal"):
        total = float(mem["SwapTotal"])
        free = float(mem.get("SwapFree", 0))
        out.append(ResourceSnapshot("host.swap", "Swap host", "host", "ok", free, total,
                                    "bytes", source="local:/proc/meminfo", checked_at=checked))
    try:
        disk = shutil.disk_usage(root)
        out.append(ResourceSnapshot("host.disk", "Disco host", "host", "ok", float(disk.free),
                                    float(disk.total), "bytes", source=f"local:{root}", checked_at=checked))
    except OSError as exc:
        out.append(ResourceSnapshot("host.disk", "Disco host", "host", "unknown",
                                    source=f"local:{root}", checked_at=checked, detail=str(exc)))
    try:
        uptime = float(uptime_path.read_text(encoding="utf-8").split()[0])
        out.append(ResourceSnapshot("host.uptime", "Uptime host", "host", "ok", uptime,
                                    unit="seconds", source="local:/proc/uptime", checked_at=checked))
    except (OSError, ValueError, IndexError):
        pass
    try:
        load1, load5, load15 = os.getloadavg()
        out.append(ResourceSnapshot("host.load", "Carga host (1m)", "host", "ok", load1,
                                    unit="load", source="local:getloadavg", checked_at=checked,
                                    detail=f"5m={load5:.2f}; 15m={load15:.2f}"))
    except (AttributeError, OSError):
        pass
    return out


def set_resource(resource_id: str, *, name: str, category: str, available: float | None,
                 maximum: float | None, unit: str | None, expires_at: str | None,
                 source: str, state: str = "ok", detail: str | None = None) -> None:
    if state not in {"ok", "warning", "critical", "unknown", "offline"}:
        raise ValueError("Estado inválido.")
    cfg = load_config()
    cfg["resources"][resource_id] = {
        "name": name,
        "category": category,
        "state": state,
        "available": available,
        "maximum": maximum,
        "unit": unit,
        "expires_at": expires_at,
        "source": source,
        "checked_at": utc_now(),
        "detail": detail,
    }
    save_config(cfg)


def configured_resources(cfg: dict | None = None) -> list[ResourceSnapshot]:
    cfg = cfg or load_config()
    out: list[ResourceSnapshot] = []
    for resource_id, raw in sorted(cfg.get("resources", {}).items()):
        if not isinstance(raw, dict):
            continue
        out.append(ResourceSnapshot(
            id=resource_id,
            name=str(raw.get("name") or resource_id),
            category=str(raw.get("category") or "other"),
            state=str(raw.get("state") or "unknown"),
            available=raw.get("available"),
            maximum=raw.get("maximum"),
            unit=raw.get("unit"),
            expires_at=raw.get("expires_at"),
            source=str(raw.get("source") or "unknown"),
            checked_at=raw.get("checked_at"),
            detail=raw.get("detail"),
        ))
    return out


def resource_inventory(*, include_local: bool = True) -> list[ResourceSnapshot]:
    items = configured_resources()
    if include_local:
        items = collect_local_resources() + items
    return items


def _human_amount(value: float | None, unit: str | None) -> str:
    if value is None:
        return "?"
    if unit == "bytes":
        size = float(value)
        for suffix in ("B", "KB", "MB", "GB", "TB"):
            if abs(size) < 1024 or suffix == "TB":
                return f"{size:.1f} {suffix}"
            size /= 1024
    if unit == "seconds":
        return f"{value / 86400:.1f} d"
    return f"{value:g}" + (f" {unit}" if unit else "")


def cmd_resources(json_output: bool = False, include_local: bool = True) -> int:
    items = resource_inventory(include_local=include_local)
    if json_output:
        print(json.dumps({"schema": "cerebramo.resources.v1", "generated_at": utc_now(),
                          "resources": [x.as_dict() for x in items]}, ensure_ascii=False, indent=2))
        return 0
    print(f"CerebrAMO {VERSION} · Recursos")
    if not items:
        print("(sin recursos configurados)")
        return 0
    for item in items:
        pct = item.remaining_percent
        ratio = _human_amount(item.available, item.unit)
        if item.maximum is not None:
            ratio += " / " + _human_amount(item.maximum, item.unit)
        pct_text = f" · {pct:.0f}%" if pct is not None else ""
        expiry = f" · vence/reset {item.expires_at}" if item.expires_at else ""
        print(f"[{item.state.upper()}] {item.name}: {ratio}{pct_text}{expiry}")
        print(f"  fuente: {item.source}" + (f" · {item.detail}" if item.detail else ""))
    return 0


def cmd_status(runner: Runner = default_runner) -> int:
    print(f"CerebrAMO {VERSION}")
    print(f"OpenCode: {'OK' if opencode_exists() else 'NO ENCONTRADO'}")
    cfg = load_config()
    print("Orden:", " → ".join(cfg["provider_order"]))
    print(f"Recursos configurados: {len(cfg.get('resources', {}))}")
    if not opencode_exists():
        return 2
    text = auth_list(runner)
    print("\nCredenciales registradas en OpenCode:")
    print(text if text else "(ninguna detectada)")
    print("\nModelos visibles:")
    for provider in cfg["provider_order"]:
        models = provider_models(provider, runner)
        selected = cfg.get("models", {}).get(provider)
        suffix = f" | fijado: {selected}" if selected else ""
        print(f"- {provider}: {len(models)}{suffix}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cerebramo",
                                description="Router multi-IA y tablero de recursos de DesarrollAMO.")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("auth", help="Agregar credenciales de IA mediante OpenCode.")
    a.add_argument("provider", choices=sorted(PROVIDER_ALIASES))
    sub.add_parser("status", help="Mostrar estado del router y conectores configurados.")
    o = sub.add_parser("set-order", help="Definir el orden de failover.")
    o.add_argument("providers", nargs="+")
    m = sub.add_parser("set-model", help="Fijar un modelo para un proveedor.")
    m.add_argument("provider", choices=sorted(PROVIDER_ALIASES))
    m.add_argument("model")
    r = sub.add_parser("run", help="Ejecutar un prompt con failover automático.")
    r.add_argument("prompt")
    r.add_argument("--provider", choices=sorted(PROVIDER_ALIASES))
    r.add_argument("--model")
    resources = sub.add_parser("resources", help="Mostrar combustible y salud disponibles.")
    resources.add_argument("--json", action="store_true")
    resources.add_argument("--no-local", action="store_true")
    rs = sub.add_parser("resource-set", help="Registrar una fuente/cuota sin guardar secretos.")
    rs.add_argument("id")
    rs.add_argument("--name", required=True)
    rs.add_argument("--category", required=True)
    rs.add_argument("--available", type=float)
    rs.add_argument("--maximum", type=float)
    rs.add_argument("--unit")
    rs.add_argument("--expires-at")
    rs.add_argument("--source", required=True)
    rs.add_argument("--state", default="ok")
    rs.add_argument("--detail")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "auth":
            return auth_provider(args.provider)
        if args.command == "status":
            return cmd_status()
        if args.command == "set-order":
            set_order(args.providers)
            print("Orden guardado:", " → ".join(load_config()["provider_order"]))
            return 0
        if args.command == "set-model":
            set_model(args.provider, args.model)
            print("Modelo guardado.")
            return 0
        if args.command == "resources":
            return cmd_resources(args.json, not args.no_local)
        if args.command == "resource-set":
            set_resource(args.id, name=args.name, category=args.category,
                         available=args.available, maximum=args.maximum, unit=args.unit,
                         expires_at=args.expires_at, source=args.source, state=args.state,
                         detail=args.detail)
            print("Recurso guardado sin credenciales.")
            return 0
        if args.command == "run":
            if not opencode_exists():
                print("ERROR: OpenCode no está instalado o no está en PATH.", file=sys.stderr)
                return 2
            rc, attempts, output = run_prompt(args.prompt, provider=args.provider, model=args.model)
            for attempt in attempts:
                marker = "OK" if attempt.ok else "FAIL"
                print(f"[{marker}] {attempt.provider}" +
                      (f" -> {attempt.model}" if attempt.model else ""), file=sys.stderr)
            if output:
                print(output, end="" if output.endswith("\n") else "\n")
            return rc
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
