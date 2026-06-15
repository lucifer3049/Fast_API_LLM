#!/usr/bin/env python3
"""Redact secrets from Claude Code JSONL transcripts before submission.

The graded deliverable includes the raw conversation transcripts (JSONL). Those
logs inevitably captured real credentials — the Groq API key, the JWT signing
secret, the Postgres and super-admin passwords, freshly minted JWTs, and the
developer's home path. This script produces *redacted copies* so the originals
on disk are never mutated.

Two layers of redaction:

1. **Exact secret values**, read from the local ``.env`` at runtime (so no real
   secret is ever hardcoded into this repo). Every literal occurrence of each
   secret's value is replaced with a ``<REDACTED:KEY>`` placeholder.
2. **Pattern-based**, for things that have a recognizable shape regardless of
   the current ``.env`` — Groq keys (``gsk_…``), bearer JWTs (``eyJ…``), and the
   developer home path (``C:\\Users\\<name>``).

Usage::

    python scripts/redact_transcripts.py \
        --src "C:/Users/<you>/.claude/projects/D--FastAPi-LLM" \
        --out ./transcripts \
        --env ./.env

Run with ``--check`` to scan the *redacted* output and fail (exit 1) if any
known secret value still leaks through — a guard you can wire into a pre-submit
check.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Keys in .env whose *values* are secrets and must be scrubbed from transcripts.
# (Usernames / hosts / model names are not secrets and are left intact.)
SECRET_ENV_KEYS = {
    "GROQ_API_KEY": "GROQ_API_KEY",
    "JWT_SECRET": "JWT_SECRET",
    "POSTGRES_PASSWORD": "POSTGRES_PASSWORD",
    "SUPER_ADMIN_PASSWORD": "SUPER_ADMIN_PASSWORD",
}

# Pattern-based redactions applied after exact-value replacement.
# (label, compiled regex, replacement)
PATTERNS = [
    ("groq-key", re.compile(r"gsk_[A-Za-z0-9]{20,}"), "<REDACTED:GROQ_API_KEY>"),
    # JWT: three base64url segments separated by dots, header always starts "eyJ".
    (
        "jwt",
        re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
        "<REDACTED:JWT>",
    ),
    # Developer home path → generic placeholder (covers C:\Users\<name> and the
    # JSON-escaped C:\\Users\\<name> form found inside the JSONL strings).
    (
        "home-path",
        re.compile(r"C:\\{1,2}Users\\{1,2}[^\\\"/]+"),
        r"C:\\\\Users\\\\<USER>",
    ),
]

MIN_SECRET_LEN = 6  # don't scrub trivially short / placeholder values


def load_env_secrets(env_path: Path) -> dict[str, str]:
    """Return {placeholder_label: secret_value} for secret keys present in .env."""
    secrets: dict[str, str] = {}
    if not env_path.exists():
        print(f"warning: {env_path} not found; skipping exact-value redaction", file=sys.stderr)
        return secrets
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key in SECRET_ENV_KEYS and len(value) >= MIN_SECRET_LEN:
            secrets[SECRET_ENV_KEYS[key]] = value
    return secrets


def redact_text(text: str, secrets: dict[str, str]) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    # 1) exact secret values (longest first so substrings don't shadow)
    for label, value in sorted(secrets.items(), key=lambda kv: -len(kv[1])):
        if value in text:
            counts[label] = counts.get(label, 0) + text.count(value)
            text = text.replace(value, f"<REDACTED:{label}>")
    # 2) pattern-based
    for label, pattern, replacement in PATTERNS:
        text, n = pattern.subn(replacement, text)
        if n:
            counts[label] = counts.get(label, 0) + n
    return text, counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True, type=Path, help="dir containing the source .jsonl transcripts")
    ap.add_argument("--out", required=True, type=Path, help="dir to write redacted copies into")
    ap.add_argument("--env", default=Path(".env"), type=Path, help="path to .env with the real secret values")
    ap.add_argument("--check", action="store_true", help="after writing, fail if any known secret still appears")
    args = ap.parse_args()

    secrets = load_env_secrets(args.env)
    src_files = sorted(args.src.glob("*.jsonl"))
    if not src_files:
        print(f"no .jsonl files found in {args.src}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)

    grand_total: dict[str, int] = {}
    leaks = 0
    for src in src_files:
        text = src.read_text(encoding="utf-8")
        redacted, counts = redact_text(text, secrets)
        dest = args.out / src.name
        dest.write_text(redacted, encoding="utf-8")
        for k, v in counts.items():
            grand_total[k] = grand_total.get(k, 0) + v
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "nothing matched"
        print(f"{src.name}: {summary}")

        if args.check:
            for label, value in secrets.items():
                if value in redacted:
                    print(f"  LEAK: {label} still present in {dest.name}", file=sys.stderr)
                    leaks += 1

    print("\nredaction totals: " + (", ".join(f"{k}={v}" for k, v in sorted(grand_total.items())) or "none"))
    if args.check and leaks:
        print(f"FAILED: {leaks} secret leak(s) detected", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
