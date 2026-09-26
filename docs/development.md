← [README](../README.md)

# Testing & Code Quality

## Testing

```bash
pytest                 # config comes from pyproject.toml (testpaths = test, -q)
tox -e py311           # same suite, in an isolated tox environment
tox -e py311 -- -k usgs   # filtered run (arguments after -- go to pytest)
```

Tests cover:
- **Base downloader** — ABC instantiation guard, session creation with retry, `_get_json()` success/error.
- **Model validation** — `SourceConfig`, `AppConfig`, `LoadParams` (historical vs incremental logic, `is_date_to_previous_day` flag).
- **Factory pattern** — registration, creation, overwrite, error cases.
- **Utilities** — `date_range()` generator, `get_recent_file_date()` file scanning.
- **Earthquake downloader** — mocked HTTP for success, empty, HTTP error, connection error, URL construction.
- **GDACS downloader** — record building from GeoJSON, pagination, empty/no-data handling.
- **EONET downloader** — event parsing (Point/Polygon geometry), closed events, missing geometry, empty/no-data handling.
- **Open-Meteo Flood downloader** — river discharge queries, null value handling, multi-river aggregation.
- **USGS NWIS downloader** — legacy WaterServices API, time series parsing, site metadata extraction.
- **IBTrACS downloader** — CSV parsing with units row skip, date filtering, custom dataset selection, error handling.
- **USGS Volcano downloader** — HANS API response parsing, alert filtering, notice URL construction.
- **NIFC downloader** — ArcGIS FeatureServer query, polygon geometry parsing, date/time filtering.


## Code Quality — Ruff + tox

Linting, formatting, type checking and tests are driven by **[Ruff](https://docs.astral.sh/ruff/)** and **[tox](https://tox.wiki/)**. Both are installed from the `pip:` section of `environment.yml`:

```bash
conda activate geo_download_311
conda env update -f environment.yml   # only needed once if the env already existed
```

| Tool | Role | Where it is configured |
|------|------|------------------------|
| **Ruff** | Linter + formatter + import sorter (replaces flake8 / isort / black / autoflake) | `pyproject.toml` → `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.format]` |
| **tox** | Runs every check in a throwaway virtualenv with its own dependencies, so results don't depend on your shell | `tox.ini` |
| **pytest** | Test suite | `pyproject.toml` → `[tool.pytest.ini_options]` (`testpaths`, `-q`) |
| **mypy** | Static type checking (installed by the tox `typecheck` env) | `tox.ini` → `[testenv:typecheck]` |

### Ruff — run it directly

Fast, in-loop commands while editing:

```bash
ruff check .                            # lint everything, writes nothing
ruff check downloader/eonet.py          # lint a single file
ruff check --fix .                      # apply safe autofixes in place (imports, modernization, unused code)
ruff check --output-format=concise .    # one line per finding — good for CI logs
ruff format --check .                   # list files that are not canonically formatted
ruff format .                           # rewrite files in style (line length 120)
ruff rule SIM108                        # print the docs for a single rule
```

Rules are configured in `pyproject.toml`:

- `line-length = 120`, `target-version = "py311"`; `data/`, `logs/`, `__pycache__` are excluded.
- Enabled families: `E,W` (pycodestyle), `F` (pyflakes), `I` (import sorting), `B` (bugbear), `UP` (pyupgrade), `C4` (comprehensions), `SIM` (simplify), `RUF` (ruff-specific).
- Exceptions: `SIM108` ignored (ternary rewrites), `F401` ignored in `__init__.py`, `B011` ignored in `test/**`.

Current state: `ruff check .` → **0 findings**. `ruff format --check .` still reports 21 files — the formatter has intentionally **not** been applied repo-wide to keep the diff reviewable; run `tox -e format-fix` if you decide to adopt it.

### tox — run the pipeline

`tox` with no arguments runs the default `envlist` from `tox.ini` (`lint, py311`).

| Command | What runs | Status |
|---------|-----------|--------|
| `tox` | default gate = `lint` + `py311` | ✅ |
| `tox -e lint` | `ruff check --output-format=concise .` | ✅ |
| `tox -e py311` | full pytest suite (96 tests) | ✅ |
| `tox -e typecheck` | `mypy model downloader downloader_factory.py util.py run_download.py` | ✅ |
| `tox -e warnings` | `pytest -W error::DeprecationWarning` | ✅ |
| `tox -e format` | `ruff format --check .` | ❌ 21 files (see above) |
| `tox -e format-fix` | `ruff format .` — writes the changes | – |
| `tox -e lint,py311,typecheck` | any list of environments in one invocation | – |

Arguments after `--` are passed to pytest (the `py311` env uses `{posargs}`):

```bash
tox -e py311 -- -k usgs                               # only USGS tests
tox -e py311 -- test/downloader/test_eonet_downloader.py -v
```

Notes:

- tox creates its environments under `.tox/` (git-ignored) and installs each env's `deps` from `tox.ini`; your shell only needs `tox` itself. No conda activation is required to run it.
- `skip_install = true` everywhere — the project is not installed as a package, tests import it from the working directory.
- To add a new check, add a `[testenv:xxx]` block; append `xxx` to `envlist` to make it part of the default `tox` run.

### PyCharm integration

- **Ruff in the IDE:** `Settings → Python → Tools → External Tools → Ruff` (PyCharm 2026.2 ships native support) — enable *Inspections*, *Formatting* and *Import optimizer*, and point it at the `ruff` binary of the `geo_download_311` env. It reads the same `pyproject.toml` rules, so IDE and CLI agree.
- **Inspection profile:** the project uses `.idea/inspectionProfiles/Project_Default.xml` (`USE_PROJECT_PROFILE=true`), where only spell-check, HTTP-URL and Markdown-table noise is disabled and `data/`, `logs/`, `__pycache__` are excluded from analysis.
- **Headless check** (CI-style, PyCharm must be closed):

  ```bash
  /snap/pycharm-community/676/bin/inspect.sh "<project-path>" -e <output-dir> -format json -v1
  ```

  The project currently reports **0 problems**.
