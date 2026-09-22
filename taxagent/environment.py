from __future__ import annotations

import os
from pathlib import Path

from .paths import REPO_ROOT


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in (Path.cwd() / ".env", REPO_ROOT / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
            return


def load_neo4j_env() -> None:
    try:
        from dotenv import dotenv_values
    except ImportError:
        return
    for candidate in (Path.cwd() / ".env", REPO_ROOT / ".env", REPO_ROOT.parent / ".env"):
        if candidate.exists():
            for k, v in dotenv_values(candidate).items():
                if k.startswith("NEO4J_") and v and k not in os.environ:
                    os.environ[k] = v
