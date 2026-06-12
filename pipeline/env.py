"""Tiny .env loader — zero dependencies.

Looks for .env in the current directory, then next to the pipeline package
(project root). Real environment variables always win; empty values in the
file are ignored so placeholder lines like KEY="" don't shadow anything.
"""
import os
from pathlib import Path


def load_env() -> None:
    for candidate in (Path.cwd() / ".env",
                      Path(__file__).resolve().parent.parent / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and value:
                os.environ.setdefault(key, value)
        return


def dashscope_base_url() -> str:
    """DashScope endpoint: workspace URL if configured, else the intl default."""
    url = (os.environ.get("DASHSCOPE_API_URL")
           or os.environ.get("DASHSCOPE_BASE_URL")
           or "https://dashscope-intl.aliyuncs.com/api/v1")
    return url.rstrip("/")
