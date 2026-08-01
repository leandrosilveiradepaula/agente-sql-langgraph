from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".env",
    ".example",
}

SECRET_PATTERNS = [
    re.compile(
        r"\b(?:postgresql|postgres|mysql|mssql)://[^:\s/@]+:[^@\s]+@",
        re.IGNORECASE,
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(
        r"\b(?:api[_-]?key|token|secret|password)\s*=\s*['\"]"
        r"(?!\s*(?:changeme|example|placeholder|dummy|test|xxx))"
        r"[^'\"]{12,}['\"]",
        re.IGNORECASE,
    ),
    re.compile(r"\bIBM[-_A-Za-z0-9]{30,}\b"),
    re.compile(
        r"\bBearer\s+(?!<access_token>|example|dummy|test)[A-Za-z0-9._-]{12,}",
        re.IGNORECASE,
    ),
    re.compile(
        r"\baccess_token\s*[:=]\s*['\"]"
        r"(?!<access_token>|example|dummy|test|placeholder)"
        r"[^'\"]{8,}['\"]",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bAuthorization\s*[:=]\s*['\"]Bearer\s+"
        r"(?!<access_token>|example|dummy|test|placeholder)"
        r"[^'\"]{8,}['\"]",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bapikey\s*[:=]\s*['\"]"
        r"(?!<configuracao segura>|example|dummy|test|placeholder)"
        r"[^'\"]{8,}['\"]",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:supabase_api|huggingface_api|rivatti_lakehouse_api)\b",
        re.IGNORECASE,
    ),
]


def _candidate_files() -> list[str]:
    completed = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return [
        line.strip().replace("\\", "/")
        for line in completed.stdout.splitlines()
        if line.strip()
    ]


def _is_text_candidate(relative_path: str) -> bool:
    path = Path(relative_path)
    suffixes = set(path.suffixes)
    if path.name == ".env.example":
        return True
    return bool(suffixes & TEXT_SUFFIXES)


def main() -> int:
    findings: list[str] = []

    for relative_path in _candidate_files():
        if relative_path == "scripts/check_secrets.py":
            continue
        if not _is_text_candidate(relative_path):
            continue

        path = ROOT / relative_path
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(relative_path)
                break

    if findings:
        print("Possiveis segredos preenchidos encontrados:")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("Nenhum segredo preenchido encontrado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
