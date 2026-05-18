"""
Prompt validator for the Technical Architect skill.

Called by the framework's SkillValidator before a draft is published.
Exit code 0 = valid.  Non-zero = validation failed; stderr contains reasons.

Usage (framework calls this automatically):
    python validate_prompt.py <agent_key> <prompt_file>

Each agent has its own set of required sections and guardrails.
Add rules here as the skill evolves.
"""

from __future__ import annotations

import sys


# ── Rules ─────────────────────────────────────────────────────────────────────

REQUIRED_SECTIONS: dict[str, list[str]] = {
    "discovery": [
        "OUTPUT FORMAT",
        "GROUPING RULE",
        "STEP 1",
        "STEP 2",
        "STEP 3",
        "STEP 4",
    ],
    "review": [
        "REVIEW CHECKLIST",
        "TECHNICAL ACCURACY",
        "COMPLETENESS",
    ],
    "approval": [
        "7-LENS",
        "VERDICT",
    ],
    "research-search": [
        "OFFICIAL SOURCES",
    ],
    "research-reasoning": [
        "OFFICIAL SOURCES",
    ],
}

FORBIDDEN_PHRASES: dict[str, list[str]] = {
    # Research agents must not instruct the LLM to use unofficial sources
    "research-search": [
        "blog post",
        "stackoverflow",
        "medium.com",
        "reddit",
    ],
    "research-reasoning": [
        "blog post",
        "stackoverflow",
    ],
}


# ── Validation ────────────────────────────────────────────────────────────────

def validate(agent_key: str, content: str) -> list[str]:
    """Return a list of validation errors (empty = valid)."""
    errors: list[str] = []
    lower  = content.lower()

    for section in REQUIRED_SECTIONS.get(agent_key, []):
        if section.lower() not in lower:
            errors.append(f"Missing required section: '{section}'")

    for phrase in FORBIDDEN_PHRASES.get(agent_key, []):
        if phrase.lower() in lower:
            errors.append(f"Forbidden phrase found: '{phrase}'")

    if len(content.strip()) < 100:
        errors.append("Prompt is too short (< 100 characters) — likely incomplete.")

    return errors


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: validate_prompt.py <agent_key> <prompt_file>", file=sys.stderr)
        sys.exit(2)

    agent_key   = sys.argv[1]
    prompt_file = sys.argv[2]

    try:
        content = open(prompt_file, encoding="utf-8").read()
    except OSError as exc:
        print(f"Cannot read prompt file: {exc}", file=sys.stderr)
        sys.exit(2)

    errors = validate(agent_key, content)

    if errors:
        print(f"Validation FAILED for agent '{agent_key}':", file=sys.stderr)
        for err in errors:
            print(f"  • {err}", file=sys.stderr)
        sys.exit(1)

    print(f"Validation PASSED for agent '{agent_key}'.")
    sys.exit(0)


if __name__ == "__main__":
    main()
