from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.adapters.postgres.context_repository import PostgresContextRepository
from app.domain.intent_resolver import resolve_intent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    args = parser.parse_args()

    payload = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases = payload["cases"]

    repo = PostgresContextRepository(
        dsn=os.environ["CONTEXT_POSTGRES_DSN"],
        semantic_agent_version=os.environ["SEMANTIC_AGENT_VERSION"],
        context_schema=os.environ.get(
            "POSTGRES_CONTEXT_SCHEMA",
            "semantic_context",
        ),
    )
    snapshot = repo.load_active_context(
        user_profile="runtime_validation"
    )
    ctx = snapshot["intent_resolution"]

    print("SUITE:", payload.get("suite", "semantic-validation"))
    print("VERSION:", snapshot["version"])
    print("FINGERPRINT:", snapshot["fingerprint"])

    failures = 0
    for index, case in enumerate(cases, start=1):
        question = case["question"]
        expected_intent = case["expected_intent"]

        result = resolve_intent(question, ctx)
        obtained_intent = result.get("intent")
        passed = (
            result.get("applied") is True
            and obtained_intent == expected_intent
        )
        if not passed:
            failures += 1

        best = result.get("best_candidate")
        second = result.get("second_candidate")
        print()
        print("=" * 80)
        print("CASE:", index)
        print("QUESTION:", question)
        print("EXPECTED:", expected_intent)
        print("APPLIED:", result.get("applied"))
        print("OBTAINED:", obtained_intent)
        print("REASON:", result.get("reason"))
        print(
            "BEST:",
            None
            if best is None
            else (best["intent_name"], best["score"]),
        )
        print(
            "SECOND:",
            None
            if second is None
            else (second["intent_name"], second["score"]),
        )
        print("RESULT:", "PASS" if passed else "FAIL")

    print()
    print(
        "SUMMARY:",
        f"{len(cases) - failures}/{len(cases)} PASS",
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
