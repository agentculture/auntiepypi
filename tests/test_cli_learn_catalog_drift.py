"""Drift-detection tests for `auntie learn` vs the explain catalog.

`learn`'s `commands` list is intentionally hand-curated (the value of
``learn`` is the agent-prompt framing, not a raw catalog dump), but the
two surfaces must stay in sync — every verb that ``learn`` claims
exists must also exist in :data:`auntiepypi.explain.catalog.ENTRIES`,
and every top-level verb in the catalog must appear in ``learn``.

Resolves the drift concern from PR #6 review (Qodo comment #2) without
coupling the two surfaces — they remain independent, but a divergence
fails this test.
"""

from __future__ import annotations

from auntiepypi.cli._commands.learn import _as_json_payload
from auntiepypi.explain.catalog import ENTRIES

# Catalog tuples that are NOT first-class verbs. These exist for routing
# (`auntie` is a console-script alias; `auntiepypi` is the package name) or
# for the root help page (the empty tuple), so they should NOT appear in
# ``learn``'s commands list.
_CATALOG_NON_VERBS: frozenset[tuple[str, ...]] = frozenset(
    {
        (),
        ("auntiepypi",),
        ("auntie",),
    }
)


def _learn_paths() -> set[tuple[str, ...]]:
    payload = _as_json_payload()
    return {tuple(cmd["path"]) for cmd in payload["commands"]}


def _catalog_verb_paths() -> set[tuple[str, ...]]:
    return {path for path in ENTRIES if path not in _CATALOG_NON_VERBS}


def test_every_learn_verb_exists_in_catalog():
    """No `learn` entry may reference a verb that has no catalog entry."""
    learn_paths = _learn_paths()
    catalog_paths = set(ENTRIES.keys())
    missing_in_catalog = learn_paths - catalog_paths
    assert missing_in_catalog == set(), (
        f"learn references verbs not in the explain catalog: {missing_in_catalog}. "
        f"Either add catalog entries or drop the verbs from learn."
    )


def test_every_catalog_verb_exists_in_learn():
    """No top-level catalog verb may be missing from `learn`'s commands list."""
    learn_paths = _learn_paths()
    catalog_paths = _catalog_verb_paths()
    missing_in_learn = catalog_paths - learn_paths
    assert missing_in_learn == set(), (
        f"catalog has verbs not described by learn: {missing_in_learn}. "
        f"Either add to learn's commands list or remove from the catalog."
    )
