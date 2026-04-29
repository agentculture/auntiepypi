# Maturity rubric

`auntiepypi packages overview <pkg>` evaluates seven independent signals
and reports a green / yellow / red light per signal. Each light is
informational — see `docs/about.md` for why nothing here is gating.

The thresholds below are the ones encoded in `auntiepypi/_rubric/`
today. The modules are the source of truth; this page is a reader's
reference. If a number here disagrees with the code, the code wins —
fix this page.

| Signal | Source | Green | Yellow | Red |
|---|---|---|---|---|
| recency | days since last non-yanked release | < 30d | 30–90d | > 90d |
| cadence | median gap between last 5 non-yanked releases | < 15d | 15–60d | > 60d (or only 1 release ever → red) |
| downloads | pypistats `last_week` count | ≥ 10/wk | 3–9/wk | < 3/wk |
| lifecycle | Trove `Development Status` classifier | 4 / 5 / 6 (Beta / Production-Stable / Mature) | 3 (Alpha) | 1 / 2 (Planning / Pre-Alpha) — or absent |
| distribution | current-release artifacts | wheel **and** sdist | only one of {wheel, sdist} | neither |
| metadata | five fields present | 5/5 | 3-4/5 | 0-2/5 |
| versioning | PEP 440 maturity | major ≥ 1 and not a pre-release | 0.x or pre-release with > 5 releases | 0.x or pre-release with ≤ 5 releases |

## Notes

- **recency** and **cadence** both look at non-yanked uploads only,
  using one timestamp per version (the latest upload across that
  version's files). This avoids skew from versions that publish many
  near-simultaneous wheels.
- **downloads** is `unknown` (not red) when pypistats has no data
  yet — common for fresh packages.
- **lifecycle** treats a missing `Development Status` classifier as
  red. An unrecognised classifier label also lands as red because the
  rubric uses a closed set.
- **metadata** counts: `info.license`, `info.requires_python`,
  `project_urls.Homepage`, `project_urls.Source`, and
  `description` longer than 200 characters (proxy for "has a real
  README").
- **versioning** uses a loose PEP 440 regex; non-PEP-440 strings come
  back as `unknown`, not red.

## Adding a dimension

Each dimension lives in its own file under `auntiepypi/_rubric/`,
exporting a module-level `DIMENSION = Dimension(...)`. The
`overview` verb discovers them through
`auntiepypi/_rubric/__init__.py`. Adding a new signal means:

1. Drop a new `_rubric/<name>.py` exporting `DIMENSION`.
2. Register it in `auntiepypi/_rubric/__init__.py`.
3. Update this page's table.
4. Update `tests/` — every dimension has unit tests covering green,
   yellow, red, and unknown branches.

The rubric is intentionally extensible; the seven above are the v0.1.0
set, not a closed contract.
