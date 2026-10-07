"""Report how much data GEO_Download keeps on disk: files and records per source.

For every source configured in ``config.json`` the script counts the CSV files
in its ``output_folder`` that match ``output_file_pattern`` (the ``{date}``
placeholder becomes a wildcard) and how many data rows they hold together, and
writes the rows to ``source_counts.csv`` at the repository root. The same rows
are rendered as a markdown table — files, records and a total row — into the
*Data inventory* section of ``README.md``, between the ``source_counts``
markers, so the README shows the cardinalities of the last run.

``data/`` is gitignored, therefore the counts are a snapshot: re-run the
script after a download to refresh both the CSV and the README table. Sources
that were never downloaded (or whose folder is missing) count as ``0``/``0``;
disabled sources are counted too, since their files stay on disk.

Usage::

    python run_source_counts.py
    python run_source_counts.py --counts source_counts.csv --readme README.md
    python run_source_counts.py --no-readme
"""

import argparse
import csv
import glob
import os

from pydantic import BaseModel, ConfigDict

from model import AppConfig, SourceConfig

COUNTS_FILE = "source_counts.csv"
"""Counts CSV written by default, at the repository root next to the README."""

README_FILE = "README.md"
"""README whose *Data inventory* section is rewritten by default."""

START_MARKER = "<!-- source_counts:start -->"
"""Opening HTML comment of the generated README section."""

END_MARKER = "<!-- source_counts:end -->"
"""Closing HTML comment of the generated README section."""

FIELDNAMES: list[str] = ["source", "files", "records"]
"""Columns written to the counts CSV."""


class SourceCount(BaseModel):
    """Cardinalities of a single source's output folder"""

    source: str
    files: int
    records: int

    model_config = ConfigDict(frozen=True)


def count_records(file_path: str) -> int:
    """Number of data rows in a CSV file — the header row is not counted

    Quoted fields may contain newlines; the csv module parses the rows, so
    they are not mistaken for extra records."""
    with open(file_path, newline="", encoding="utf-8") as f:
        row_count = sum(1 for _ in csv.reader(f))
    return max(row_count - 1, 0)


def count_source(name: str, source: SourceConfig) -> SourceCount:
    """Counts the files matching the source pattern and the records inside them

    A missing output folder (source never downloaded) counts as no files
    and no records."""
    pattern = source.output_file_pattern.replace("{date}", "*")
    files = sorted(glob.glob(os.path.join(source.output_folder, pattern)))
    return SourceCount(source=name, files=len(files), records=sum(count_records(file) for file in files))


def build_counts(config: AppConfig) -> list[SourceCount]:
    """Counts every source of the config, in config order"""
    return [count_source(name, source) for name, source in config.sources.items()]


def write_counts(counts: list[SourceCount], output_path: str = COUNTS_FILE) -> None:
    """Writes the counts as a CSV with the ``FIELDNAMES`` header"""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(count.model_dump() for count in counts)


def render_table(counts: list[SourceCount]) -> str:
    """Renders the counts as a markdown table with a total row"""
    lines = ["| Source | Files | Records |", "|--------|------:|--------:|"]
    lines += [f"| {count.source} | {count.files:,} | {count.records:,} |" for count in counts]
    files = sum(count.files for count in counts)
    records = sum(count.records for count in counts)
    lines.append(f"| **Total** | **{files:,}** | **{records:,}** |")
    return "\n".join(lines)


def update_readme(counts: list[SourceCount], readme_path: str = README_FILE) -> None:
    """Replaces the marked section of the README with the rendered table

    Raises:
        ValueError: When either marker is missing from the README."""
    with open(readme_path, encoding="utf-8") as f:
        text = f.read()

    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"Markers {START_MARKER!r} / {END_MARKER!r} not found in {readme_path}")

    section = f"{START_MARKER}\n{render_table(counts)}\n{END_MARKER}"
    updated = text[:start] + section + text[end + len(END_MARKER) :]

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(updated)


def parse_args() -> argparse.Namespace:
    """Parses command line arguments"""
    parser = argparse.ArgumentParser(description="Count the CSV files and records of every configured data source.")
    parser.add_argument("--counts", default=COUNTS_FILE, help=f"counts CSV to write (default: {COUNTS_FILE})")
    parser.add_argument("--readme", default=README_FILE, help=f"README to update (default: {README_FILE})")
    parser.add_argument("--no-readme", action="store_true", help="write the counts CSV only, leave the README alone")
    return parser.parse_args()


def main() -> None:
    """Counts every configured source, writes the CSV and refreshes the README"""
    args = parse_args()
    config = AppConfig.from_json()
    counts = build_counts(config)

    write_counts(counts, args.counts)
    if not args.no_readme:
        update_readme(counts, args.readme)

    print(render_table(counts))
    written = [args.counts] + ([] if args.no_readme else [args.readme])
    print(f"\nWrote {', '.join(written)}.")


if __name__ == "__main__":
    main()
