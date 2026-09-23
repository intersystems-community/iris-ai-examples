"""Service configuration: one YAML file declares backends, tools, agents, policy.

The file is the whole deployment surface. Moving CareConnect from in-place to
sidecar is a different file, not different code — see examples/careconnect/.

Strings may reference the environment as ``${VAR}`` or ``${VAR:-default}``, the
same idiom the compose files use, so a Kubernetes Secret or a compose ``.env``
supplies credentials without the YAML carrying them.
"""

from __future__ import annotations

import hmac
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ENV = re.compile(r"\$\{(?P<name>[A-Z_][A-Z0-9_]*)(?::-(?P<default>[^}]*))?\}")


class ConfigError(ValueError):
    """The service config is wrong in a way the operator has to fix."""


def expand_env(value: Any, environ: dict | None = None) -> Any:
    """Expand ``${VAR:-default}`` in every string, recursively."""
    env = os.environ if environ is None else environ
    if isinstance(value, str):

        def sub(m: re.Match) -> str:
            name, default = m.group("name"), m.group("default")
            if name in env and env[name] != "":
                return env[name]
            if default is not None:
                return default
            raise ConfigError(f"environment variable {name} is not set and has no default")

        return _ENV.sub(sub, value)
    if isinstance(value, list):
        return [expand_env(v, env) for v in value]
    if isinstance(value, dict):
        return {k: expand_env(v, env) for k, v in value.items()}
    return value


@dataclass
class Principal:
    name: str
    roles: frozenset


@dataclass
class ServiceConfig:
    name: str
    mode: str
    backends: dict
    tools: list
    agents: dict
    auth: dict
    policy: dict
    source: Path | None = None
    raw: dict = field(default_factory=dict)

    # -- auth ------------------------------------------------------------

    def principal_for_key(self, key: str | None) -> Principal | None:
        if not key:
            return None
        found = None
        for entry in self.auth.get("api_keys", []):
            # Constant-time, and every entry compared, so timing says nothing
            # about how much of a key was right or which entry it was.
            if hmac.compare_digest(str(entry.get("key", "")).encode(), key.encode()) and found is None:
                found = Principal(entry["principal"], frozenset(entry.get("roles", [])))
        return found


def load_config(path: str | os.PathLike, environ: dict | None = None) -> ServiceConfig:
    path = Path(path).resolve()
    return build_config(_load_raw(path), source=path, environ=environ)


def _load_raw(path: Path, seen: tuple = ()) -> dict:
    """Read one file, resolving ``extends: other.yaml`` (relative to it) first.

    A deployment mode is a small file that extends a shared base: the three
    CareConnect modes share agents, policy and tool effects, and differ only in
    which backend each tool is bound to.
    """
    if path in seen:
        raise ConfigError(f"extends cycle: {' -> '.join(str(p) for p in (*seen, path))}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    parent = raw.pop("extends", None)
    if not parent:
        return raw
    base = _load_raw((path.parent / parent).resolve(), (*seen, path))
    return merge(base, raw)


def merge(base: dict, over: dict) -> dict:
    """Deep-merge ``over`` onto ``base``. Lists of named items (tools) merge by
    name, so a mode file can rebind one tool without restating the rest."""
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        elif _named_list(value) and _named_list(out.get(key)):
            merged = {item["name"]: item for item in out[key]}
            for item in value:
                merged[item["name"]] = merge(merged.get(item["name"], {}), item)
            out[key] = list(merged.values())
        else:
            out[key] = value
    return out


def _named_list(value) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(v, dict) and "name" in v for v in value
    )


def build_config(raw: dict, source: Path | None = None, environ: dict | None = None) -> ServiceConfig:
    data = expand_env(raw, environ)
    base = source.parent if source else Path.cwd()

    # Config-relative import roots, so a deployment can ship its own formatters
    # and Python tool modules next to its YAML.
    for entry in data.get("python_path", []):
        p = str((base / entry).resolve())
        if p not in sys.path:
            sys.path.insert(0, p)

    service = data.get("service", {})
    cfg = ServiceConfig(
        name=service.get("name", "aihub-service"),
        mode=service.get("mode", "custom"),
        backends=data.get("backends", {}),
        tools=data.get("tools", []),
        agents=data.get("agents", {}),
        auth=data.get("auth", {}),
        policy=data.get("policy", {}),
        source=source,
        raw=data,
    )
    _validate(cfg)
    return cfg


def _validate(cfg: ServiceConfig) -> None:
    names = [t.get("name") for t in cfg.tools]
    if any(not n for n in names):
        raise ConfigError("every tool needs a name")
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ConfigError(f"duplicate tool names: {', '.join(dupes)}")
    for tool in cfg.tools:
        if tool.get("backend") not in cfg.backends:
            raise ConfigError(
                f"tool {tool['name']} names backend {tool.get('backend')!r}, "
                f"which is not declared (have: {', '.join(sorted(cfg.backends))})"
            )
        if tool.get("effect", "read") not in ("read", "write"):
            raise ConfigError(f"tool {tool['name']}: effect must be read or write")
    for agent_name, agent in cfg.agents.items():
        unknown = [t for t in agent.get("tools", []) if t not in names]
        if unknown:
            raise ConfigError(f"agent {agent_name} lists unknown tools: {', '.join(unknown)}")
        if agent.get("engine", "playbook") == "playbook":
            for step in agent.get("playbook", {}).get("steps", []):
                if step.get("tool") not in agent.get("tools", []):
                    raise ConfigError(
                        f"agent {agent_name}: playbook step calls {step.get('tool')!r}, "
                        "which is not in the agent's tools list"
                    )
