#!/usr/bin/env python3
"""CerebrAMO: provider-independent LLM router built around OpenCode.

Credentials are delegated to OpenCode whenever possible. CerebrAMO never reads
or copies OpenCode's auth.json secrets.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

VERSION = "0.1.0"
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


def _default_config() -> dict:
    return {
        "version": 1,
        "provider_order": DEFAULT_ORDER.copy(),
        "models": {},
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
        list(args),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
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
    text = (cp.stdout or "") + (cp.stderr or "")
    return text.strip()


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


def run_prompt(
    prompt: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    runner: Runner = default_runner,
) -> tuple[int, list[Attempt], str]:
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


def cmd_status(runner: Runner = default_runner) -> int:
    print(f"CerebrAMO {VERSION}")
    print(f"OpenCode: {'OK' if opencode_exists() else 'NO ENCONTRADO'}")
    cfg = load_config()
    print("Orden:", " → ".join(cfg["provider_order"]))
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
    p = argparse.ArgumentParser(
        prog="cerebramo",
        description="Router multi-IA con failover usando OpenCode.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("auth", help="Agregar credenciales de un proveedor mediante OpenCode.")
    a.add_argument("provider", choices=sorted(PROVIDER_ALIASES))

    sub.add_parser("status", help="Mostrar proveedores, credenciales y modelos visibles.")

    o = sub.add_parser("set-order", help="Definir el orden de failover.")
    o.add_argument("providers", nargs="+", help="Ej: claude minimax openrouter")

    m = sub.add_parser("set-model", help="Fijar un modelo para un proveedor.")
    m.add_argument("provider", choices=sorted(PROVIDER_ALIASES))
    m.add_argument("model", help="Ej: anthropic/claude-sonnet-4-5")

    r = sub.add_parser("run", help="Ejecutar un prompt con failover automático.")
    r.add_argument("prompt")
    r.add_argument("--provider", choices=sorted(PROVIDER_ALIASES))
    r.add_argument("--model")

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
        if args.command == "run":
            if not opencode_exists():
                print("ERROR: OpenCode no está instalado o no está en PATH.", file=sys.stderr)
                return 2
            rc, attempts, output = run_prompt(
                args.prompt, provider=args.provider, model=args.model
            )
            for attempt in attempts:
                marker = "OK" if attempt.ok else "FAIL"
                print(
                    f"[{marker}] {attempt.provider}"
                    + (f" -> {attempt.model}" if attempt.model else ""),
                    file=sys.stderr,
                )
            if output:
                print(output, end="" if output.endswith("\n") else "\n")
            return rc
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
