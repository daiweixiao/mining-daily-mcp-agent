from __future__ import annotations

import os
from pathlib import Path


_LOADED = False


def load_dotenv(path: str | Path | None = None) -> list[Path]:
    """Load simple KEY=VALUE pairs from .env without overriding real env vars."""

    global _LOADED
    if _LOADED and path is None:
        return []

    loaded: list[Path] = []
    for candidate in _candidate_paths(path):
        if not candidate.exists() or not candidate.is_file():
            continue
        _load_file(candidate)
        loaded.append(candidate)
        if path is not None or os.getenv("ENV_FILE"):
            break
    _LOADED = True
    return loaded


def _candidate_paths(path: str | Path | None) -> list[Path]:
    if path:
        return [Path(path).expanduser()]
    if os.getenv("ENV_FILE"):
        return [Path(os.environ["ENV_FILE"]).expanduser()]

    candidates: list[Path] = []
    cwd = Path.cwd().resolve()
    candidates.extend(parent / ".env" for parent in [cwd, *cwd.parents])
    repo_root = Path(__file__).resolve().parent
    candidates.append(repo_root / ".env")

    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(resolved)
    return deduped


def _load_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _clean_value(value.strip())


def _clean_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value

