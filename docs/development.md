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
- **USGS NWIS downloader** — WaterServices instantaneous-values parsing (day mean of the discharge, day peak of the gauge height, non-numeric readings skipped, one row per configured parameter), NWS flood-category reference maintenance (`data/usgs_flood_categories.csv`, one gauge request, existing gauges untouched, unknown gauges logged) and the `no_flooding` … `major` classification of a day's peak stage.
- **IBTrACS downloader** — CSV parsing with units row skip, `ISO_TIME` column resolution by header name (regression: a fixed column index dropped every record), date filtering, custom dataset selection, error handling.
- **USGS Volcano downloader** — HANS API response parsing, alert filtering, notice URL construction, notice-detail lookup maintenance (`data/usgs_volcano_notices.csv`, one fetch per new notice) and stamping of `notice_type_name`, `latitude`, `longitude`, `region`, `synopsis`; plus the NCEI eruption enrichment (`data/usgs_volcano_ncei_eruptions.csv`, built once from the NCEI HazEL endpoint) stamped as `vei` (max over the volcano's significant eruptions), `casualties` (total deaths) and `damage` (total damage, million USD).
- **NIFC downloader** — ArcGIS FeatureServer query, `outFields`/centroid handling, ArcGIS error-payload detection, date/time filtering, unit-name lookup maintenance (`data/nifc_unit_names.csv`, refresh when the data carries an unknown code) and `unit_name` stamping with raw-code fallback.
- **Reverse geocoding** — `reverse_geocode.py` (coordinate keying, Nominatim response parsing, lookup round-trip, strict fetch-then-persist) and `stamp_geocode()` across the eight geocoding downloaders: appended column placement, per-source fetch filters (blank `state`, unknown `place` suffix, `DIST2LAND ≤ 100` with cached far-row answers), failed-fetch propagation, and test isolation — a missing point in a test must never reach the real API or extend the repository's lookup.
- **Avalanche downloader** — GeoJSON record building, area weighted zone polygon centroid (holes subtracted), notices lookup merge keyed zone name + state (keeps zones that leave the feed, skips records without geometry).
- **Source inventory** — `run_source_counts.py` (record counting with the csv parser, per-source file/record totals, missing folders, the `source_counts.csv` output and the README section between the `source_counts` markers).
- **Run orchestration** — `save_csv()` (file written / no data / failed write) and the [failure contract](architecture.md#exit-codes) of `download_source()` and `main()` (files saved → returns normally, no files → `RuntimeError`, local data already current → `0`).


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

- `line-length = 120`, `target-version = "py311"`; `data/`, `logs/`, `__pycache__`, `.idea` are excluded.
- Enabled families: `E,W` (pycodestyle), `F` (pyflakes), `I` (import sorting), `B` (bugbear), `UP` (pyupgrade), `C4` (comprehensions), `SIM` (simplify), `RUF` (ruff-specific).
- Exceptions: `SIM108` ignored (ternary rewrites), `F401` ignored in `__init__.py`, `B011` ignored in `test/**`.

Current state: `ruff check .` → **0 findings**. `ruff format --check .` → **0 files need reformatting (49 already formatted)** — the formatter is applied repo-wide, so any new or edited file should be passed through `tox -e format-fix` before committing.

### tox — run the pipeline

`tox` with no arguments runs the default `envlist` from `tox.ini` (`lint, py311`).

| Command | What runs | Status |
|---------|-----------|--------|
| `tox` | default gate = `lint` + `py311` | ✅ |
| `tox -e lint` | `ruff check --output-format=concise .` | ✅ |
| `tox -e py311` | full pytest suite (319 tests) | ✅ |
| `tox -e typecheck` | `mypy model downloader downloader_factory.py util.py run_download.py run_openmeteo_thresholds.py run_source_counts.py reverse_geocode.py` | ✅ |
| `tox -e warnings` | `pytest -W error::DeprecationWarning` | ✅ |
| `tox -e format` | `ruff format --check .` | ✅ 0 files |
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
- **Inspection profile:** the project uses `.idea/inspectionProfiles/Project_Default.xml` (`USE_PROJECT_PROFILE=true`), where spell-check, HTTP-URL, Markdown-table and `__init__`-signature (`PyInitNewSignature`) inspections are disabled and the stub-package prompt is muted for `celery` and `pandas`. The folders `data/`, `logs/` and `__pycache__` are excluded from analysis in `.idea/GEODownload.iml`, not in the profile.
- **Headless check** (CI-style, PyCharm must be closed):

  ```bash
  /snap/pycharm-community/676/bin/inspect.sh "<project-path>" -e <output-dir> -format json -v1
  ```

  The project currently reports **0 problems**.
