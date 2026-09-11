"""Load a local .env file into os.environ.

Existing environment variables are not overwritten, so GitHub Actions
secrets win over a checked-out file if both are present.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path) -> None:
    """Read KEY=value pairs from path into os.environ.

    Blank values, comments, and missing files are ignored. Quotes around
    values are stripped. This is enough for local testing without extra
    dependencies.
    """
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if not key or key in os.environ:
            continue
        os.environ[key] = value
