# Quality pipeline

Wire this **before** the first PR. The `version-check` job blocks merges
when `pyproject.toml`'s version equals `main`'s, and the `publish.yml`
TestPyPI step needs Trusted Publishing already configured by the time a
PR opens.

The shape below mirrors `../steward/` (the canonical Culture-sibling
template) with adjustments for agentpypi's own opinions in
`../CLAUDE.md` (pre-commit hooks; `flake8-bandit` + `flake8-bugbear`;
`pylint --errors-only`).

## 1. `pyproject.toml`

Paste-ready template. Adjust only the marked lines and the dev-dep set
if `../CLAUDE.md` later tightens the toolchain.

```toml
[project]
name = "agentpypi"
version = "0.0.1"
description = "agentpypi — both ends of the Python distribution pipe for the AgentCulture mesh."
readme = "README.md"
license = "MIT"
requires-python = ">=3.12"
authors = [{name = "AgentCulture"}]
classifiers = [
    "Development Status :: 2 - Pre-Alpha",
    "Programming Language :: Python :: 3.12",
    "License :: OSI Approved :: MIT License",
    "Topic :: Software Development",
    "Intended Audience :: Developers",
]
dependencies = [
    # Keep zero runtime deps where possible. Add only when a verb needs
    # something the stdlib can't do.
]

[project.urls]
Homepage = "https://github.com/agentculture/agentpypi"
Issues = "https://github.com/agentculture/agentpypi/issues"

[project.scripts]
agentpypi = "agentpypi.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["agentpypi"]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-xdist>=3.0",
    "pytest-cov>=4.1",
    "bandit>=1.7.5",
    "flake8>=6.1",
    "flake8-bugbear>=24.0",
    "flake8-bandit>=4.1",
    "isort>=5.12.0",
    "black>=23.7.0",
    "pylint>=3.0",
    "pre-commit>=3.6",
]

[tool.coverage.run]
source = ["agentpypi"]
omit = ["agentpypi/__pycache__/*"]

[tool.coverage.report]
fail_under = 60
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if __name__ == .__main__.",
    "if TYPE_CHECKING:",
]

[tool.isort]
profile = "black"
line_length = 100
known_first_party = ["agentpypi"]

[tool.black]
line-length = 100
target-version = ["py312"]

[tool.bandit]
exclude_dirs = ["tests"]
skips = ["B101", "B404", "B603"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
```

Notes:

- **`name = "agentpypi"`** matches the README's `uv tool install agentpypi`.
  If PyPI returns a name conflict at first publish, rename to
  `agentpypi-cli` and update `[project.scripts]` accordingly.
- **No runtime deps** at v0.0.1. Add only when a verb needs something
  stdlib can't do.
- **`fail_under = 60`** is steward's threshold; tighten as coverage
  organically grows.

## 2. Lint configs

### `.flake8` (repo-local)

```ini
[flake8]
# Match black's line length so flake8 and black agree.
max-line-length = 100

# E203: whitespace before ':' — conflicts with black's slice formatting.
# W503: line break before binary operator — black does the opposite (W504-style).
extend-ignore = E203, W503
```

If a test file legitimately needs a per-file ignore (e.g. `tests/*:S101`
for `assert` statements when bandit is run via flake8-bandit), add it
narrowly. Per `../CLAUDE.md`: "Don't broaden it to silence real
findings — delete or fix the offending code."

### `.markdownlint-cli2.yaml` (repo-local)

Vendored verbatim from steward — keeps formatting consistent across
the mesh:

```yaml
# markdownlint-cli2 config for agentpypi.
# markdownlint-cli2 stops walking at the git root, so a per-user global
# config in the home directory isn't picked up from inside the repo.
# Mirrors the afi-cli / cfafi / steward preset for workspace consistency.

config:
  default: true
  # MD013: Line length — disabled. Prose lines wrap at the reader.
  MD013: false
  # MD060: Table pipe spacing — disabled (stylistic preference).
  MD060: false
  # MD024: Duplicate headings — allow under different parents so Keep a
  # Changelog entries can each have ### Added / ### Changed / ### Fixed.
  MD024:
    siblings_only: true

ignores:
  - "node_modules/**"
  - ".local/**"
```

## 3. `CHANGELOG.md`

Keep-a-Changelog header. The `version-bump` skill prepends entries on
every PR.

```markdown
# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/). This project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.1] - YYYY-MM-DD

### Added

- Initial scaffold.
```

## 4. `.github/workflows/tests.yml`

Three jobs: `test`, `lint`, `version-check`. Adapt steward's verbatim,
substituting `steward` → `agentpypi` everywhere:

```yaml
name: Tests

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
      - uses: astral-sh/setup-uv@38f3f104447c67c051c4a08e39b64a148898af3a # v4
      - run: uv python install 3.12
      - run: uv sync
      - run: uv run pytest -n auto --cov=agentpypi --cov-report=xml:coverage.xml --cov-report=term -v

  lint:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
      - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4
        with:
          node-version: '20'
      - uses: astral-sh/setup-uv@38f3f104447c67c051c4a08e39b64a148898af3a # v4
      - run: uv python install 3.12
      - run: uv sync
      - name: black --check
        run: uv run black --check agentpypi tests
      - name: isort --check
        run: uv run isort --check-only agentpypi tests
      - name: flake8
        run: uv run flake8 agentpypi tests
      - name: pylint --errors-only
        run: uv run pylint --errors-only agentpypi
      - name: bandit
        run: uv run bandit -c pyproject.toml -r agentpypi
      - name: markdownlint-cli2
        run: |
          npm install -g markdownlint-cli2@0.21.0
          markdownlint-cli2 "**/*.md" "#node_modules" "#.local"
      - name: portability-lint
        run: bash .claude/skills/pr-review/scripts/portability-lint.sh

  version-check:
    # Only run on PR events. On push to main after merge, HEAD == origin/main
    # and the comparison would always fail.
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
        with:
          fetch-depth: 0
      - run: git fetch origin main
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5
        with:
          python-version: "3.12"
      - name: Check version bump
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          # AgentCulture rule: every PR bumps the version — even docs/config/CI.
          PR_VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
          MAIN_VERSION=$(git show origin/main:pyproject.toml 2>/dev/null | python3 -c "import sys,tomllib; print(tomllib.loads(sys.stdin.read())['project']['version'])" 2>/dev/null || echo "")

          if [ -z "$MAIN_VERSION" ]; then
            echo "No pyproject.toml on main yet — skipping version check (initial scaffold)."
            exit 0
          fi

          if [ "$PR_VERSION" = "$MAIN_VERSION" ]; then
            MARKER="<!-- version-check -->"
            BODY="⚠️ **Version not bumped** — \`pyproject.toml\` still has \`$PR_VERSION\` (same as main). Bump before merging to avoid a failed PyPI publish.

          $MARKER"
            EXISTING=$(gh api repos/${{ github.repository }}/issues/${{ github.event.pull_request.number }}/comments \
              --jq '.[] | select(.body | contains("<!-- version-check -->")) | .id' | head -1)
            if [ -n "$EXISTING" ]; then
              gh api repos/${{ github.repository }}/issues/comments/$EXISTING -X PATCH -f body="$BODY" > /dev/null
            else
              gh pr comment ${{ github.event.pull_request.number }} --body "$BODY" || true
            fi
            echo "::error::Version $PR_VERSION matches main. Bump before merging."
            exit 1
          else
            echo "Version bumped: $MAIN_VERSION -> $PR_VERSION"
          fi
```

## 5. `.github/workflows/publish.yml`

PRs publish a `.dev<run_number>` to TestPyPI; merges to `main` publish
to PyPI. Both via OIDC Trusted Publishing — no API tokens.

`ghafi` provisions the `pypi` and `testpypi` GitHub Environments and
the Trusted Publishing claims pointing at `agentculture/agentpypi`.
That setup must be in place before this workflow can succeed; if you
own the repo, run `ghafi` first (see `../ghafi/README.md`).

```yaml
name: Publish to PyPI

on:
  push:
    branches: [main]
    paths:
      - "pyproject.toml"
      - "agentpypi/**"
  pull_request:
    branches: [main]
    paths:
      - "pyproject.toml"
      - "agentpypi/**"

jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
      - uses: astral-sh/setup-uv@38f3f104447c67c051c4a08e39b64a148898af3a # v4
      - run: uv python install 3.12
      - run: uv sync
      - run: uv run pytest -n auto -v

  test-publish:
    # Skip on fork PRs — no OIDC context, the publish step would fail.
    if: github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository
    needs: test
    runs-on: ubuntu-latest
    environment: testpypi
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
      - uses: astral-sh/setup-uv@38f3f104447c67c051c4a08e39b64a148898af3a # v4
      - run: uv python install 3.12
      - run: uv sync
      - name: Set dev version
        run: |
          BASE=$(uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
          DEV_VERSION="${BASE}.dev${{ github.run_number }}"
          sed -i "s/^version = .*/version = \"${DEV_VERSION}\"/" pyproject.toml
          echo "DEV_VERSION=${DEV_VERSION}" >> "$GITHUB_ENV"
          echo "Publishing ${DEV_VERSION} to TestPyPI"
      - name: Build and publish to TestPyPI
        run: |
          uv build
          uv publish --publish-url https://test.pypi.org/legacy/ --trusted-publishing always --check-url https://test.pypi.org/simple/
      - name: Print install commands
        if: always()
        run: |
          echo "::notice::Test with: uv tool install --index-url https://test.pypi.org/simple/ --index-strategy unsafe-best-match agentpypi==${DEV_VERSION}"

  publish:
    if: github.event_name == 'push'
    needs: test
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
      - uses: astral-sh/setup-uv@38f3f104447c67c051c4a08e39b64a148898af3a # v4
      - run: uv python install 3.12
      - run: uv sync
      - name: Build and publish to PyPI
        run: |
          uv build
          uv publish --trusted-publishing always --check-url https://pypi.org/simple/
```

## 6. Pre-commit (optional but expected)

`../CLAUDE.md` mentions a pre-commit hook set every sibling ships with.
Steward doesn't ship one yet, so look at `../shushu/.pre-commit-config.yaml`
or `../ghafi/.pre-commit-config.yaml` for the canonical layout. Wire
`black`, `isort`, `flake8`, `bandit`, `markdownlint-cli2` (in
check-only mode), and the portability lint.

## Verification

After committing all of the above:

```bash
# Local end-to-end smoke
uv sync
uv run pytest -n auto -v
uv run black --check agentpypi tests
uv run isort --check-only agentpypi tests
uv run flake8 agentpypi tests
uv run bandit -c pyproject.toml -r agentpypi
markdownlint-cli2 "**/*.md" "#node_modules"
bash .claude/skills/pr-review/scripts/portability-lint.sh

# Steward's external diagnosis
(cd ../steward && uv run steward doctor --scope self ../agentpypi)
```

Open a no-op PR (typo fix in README) once Trusted Publishing is wired,
and confirm:

1. `tests`, `lint`, `version-check` all run.
2. `version-check` *fails* until you bump the version (run
   `python3 .claude/skills/version-bump/scripts/bump.py patch`).
3. `test-publish` succeeds and a `0.0.1.dev<n>` shows up on TestPyPI.

If all three are green, the pipeline is wired.
