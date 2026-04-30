"""Registry for `--decide` ambiguity-resolution flags.

Format (repeatable): ``--decide=<key>:<name>=<value>``

v0.4.0 ships exactly one decision type — ``duplicate:<name>=<index>``.
Future PRs add entries to ``KNOWN_DECISIONS`` without changing the surface.

Stale decision values (well-formed but referencing an ambiguity that's
no longer present) are silently ignored — the lookup function only
returns the value when callers ask for that specific key+name pair, and
callers only ask when the ambiguity is actually present in the current
run. This keeps re-runs idempotent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from auntiepypi.cli._errors import EXIT_USER_ERROR, AfiError

KNOWN_DECISIONS: frozenset[str] = frozenset({"duplicate"})


def _validate_duplicate_value(name: str, value: str) -> None:
    """Raise AfiError on bad ``duplicate:NAME=<value>`` (must be positive int)."""
    try:
        idx = int(value)
    except ValueError as err:
        raise AfiError(
            code=EXIT_USER_ERROR,
            message=f"--decide=duplicate:{name}={value!r}: must be a positive integer",
            remediation="example: --decide=duplicate:main=1   (keep first occurrence)",
        ) from err
    if idx < 1:
        raise AfiError(
            code=EXIT_USER_ERROR,
            message=f"--decide=duplicate:{name}={value!r}: must be >= 1 (got {idx})",
            remediation="example: --decide=duplicate:main=1   (keep first occurrence)",
        )


_VALIDATORS: dict[str, Callable[[str, str], None]] = {
    "duplicate": _validate_duplicate_value,
}


@dataclass(frozen=True)
class Decisions:
    """Parsed ``--decide`` values, keyed by (decision_kind, target_name)."""

    by_kind_name: dict[tuple[str, str], str] = field(default_factory=dict)

    def for_key(self, kind: str, name: str) -> str | None:
        return self.by_kind_name.get((kind, name))


def parse_decisions(raw: list[str]) -> Decisions:
    """Parse a list of `--decide` arg values into a ``Decisions`` map."""
    if not raw:
        return Decisions()

    out: dict[tuple[str, str], str] = {}
    for item in raw:
        if "=" not in item:
            raise AfiError(
                code=EXIT_USER_ERROR,
                message=f"--decide: malformed value {item!r}",
                remediation=(
                    "format: --decide=<kind>:<name>=<value> (e.g. --decide=duplicate:main=1)"
                ),
            )
        lhs, value = item.split("=", 1)
        if ":" not in lhs:
            raise AfiError(
                code=EXIT_USER_ERROR,
                message=f"--decide: malformed key {lhs!r}",
                remediation=(
                    "format: --decide=<kind>:<name>=<value> (e.g. --decide=duplicate:main=1)"
                ),
            )
        kind, name = lhs.split(":", 1)
        if kind not in KNOWN_DECISIONS:
            raise AfiError(
                code=EXIT_USER_ERROR,
                message=f"--decide: unknown decision kind {kind!r}",
                remediation=f"known kinds: {sorted(KNOWN_DECISIONS)}",
            )
        validator = _VALIDATORS.get(kind)
        if validator is not None:
            validator(name, value)
        out[(kind, name)] = value
    return Decisions(by_kind_name=out)
