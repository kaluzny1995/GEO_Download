import csv
from pathlib import Path

import pytest

from model import AppConfig, SourceConfig
from run_source_counts import (
    END_MARKER,
    FIELDNAMES,
    START_MARKER,
    SourceCount,
    build_counts,
    count_records,
    count_source,
    render_table,
    update_readme,
    write_counts,
)


def _source(folder: str, pattern: str = "events_{date}.csv") -> SourceConfig:
    return SourceConfig(
        type="test",
        enabled=True,
        api_url="https://example.com/api",
        start_date="2026-09-01",
        output_folder=folder,
        output_file_pattern=pattern,
    )


def _write(path, content: str) -> str:
    path.write_text(content, encoding="utf-8")
    return str(path)


class TestCountRecords:
    @pytest.mark.parametrize(
        ("filename", "content", "expected"),
        [
            ("events_2026-09-01.csv", "id,name\n1,a\n2,b\n3,c\n", 3),
            ("empty.csv", "id,name\n", 0),
            ("blank.csv", "", 0),
            ("quoted.csv", 'id,note\n1,"line one\nline two"\n2,x\n', 2),
        ],
    )
    def test_counts_records(self, tmp_path, filename, content, expected):
        assert count_records(_write(tmp_path / filename, content)) == expected


class TestCountSource:
    def test_sums_the_files_matching_the_pattern(self, tmp_path):
        folder = tmp_path / "Source"
        folder.mkdir()
        _write(folder / "events_2026-09-01.csv", "id\n1\n2\n")
        _write(folder / "events_2026-09-02.csv", "id\n3\n")
        _write(folder / "other.csv", "id\n9\n9\n9\n")

        count = count_source("Source", _source(str(folder)))

        assert count == SourceCount(source="Source", files=2, records=3)

    @pytest.mark.parametrize("folder", ["does_not_exist", "."])
    def test_missing_or_empty_folder_counts_zero(self, tmp_path, folder):
        count = count_source("Source", _source(str(tmp_path / folder)))

        assert count == SourceCount(source="Source", files=0, records=0)


class TestBuildCounts:
    def test_counts_every_source_in_config_order(self, tmp_path):
        first = tmp_path / "First"
        first.mkdir()
        _write(first / "events_2026-09-01.csv", "id\n1\n")
        config = AppConfig(sources={"First": _source(str(first)), "Second": _source(str(tmp_path / "Missing"))})

        counts = build_counts(config)

        assert [count.source for count in counts] == ["First", "Second"]
        assert counts[0] == SourceCount(source="First", files=1, records=1)
        assert counts[1] == SourceCount(source="Second", files=0, records=0)


class TestWriteCounts:
    def test_writes_header_and_rows(self, tmp_path):
        output = tmp_path / "source_counts.csv"
        counts = [SourceCount(source="A", files=2, records=10), SourceCount(source="B", files=0, records=0)]

        write_counts(counts, str(output))

        with open(output, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert rows == [FIELDNAMES, ["A", "2", "10"], ["B", "0", "0"]]


class TestRenderTable:
    def test_renders_rows_grouped_numbers_and_a_total_row(self):
        counts = [SourceCount(source="A", files=2, records=1234), SourceCount(source="B", files=1, records=7)]
        table = render_table(counts)

        lines = table.splitlines()
        assert lines[0] == "| Source | Files | Records |"
        assert lines[1] == "|--------|------:|--------:|"
        assert lines[2] == "| A | 2 | 1,234 |"
        assert lines[3] == "| B | 1 | 7 |"
        assert lines[4] == "| **Total** | **3** | **1,241** |"

    def test_table_without_sources_is_just_the_header_and_a_zero_total(self):
        assert render_table([]).splitlines()[2] == "| **Total** | **0** | **0** |"


class TestUpdateReadme:
    def _readme(self, tmp_path) -> str:
        return _write(
            tmp_path / "README.md",
            f"# Title\n\nbefore\n\n{START_MARKER}\n| stale |\n{END_MARKER}\n\nafter\n",
        )

    def test_replaces_only_the_marked_section(self, tmp_path):
        readme = self._readme(tmp_path)

        update_readme([SourceCount(source="A", files=1, records=2)], readme)

        text = Path(readme).read_text(encoding="utf-8")
        assert text.startswith("# Title\n\nbefore\n\n")
        assert text.endswith("\n\nafter\n")
        assert text.count(START_MARKER) == 1
        assert "| A | 1 | 2 |" in text
        assert "| **Total** | **1** | **2** |" in text
        assert "| stale |" not in text

    def test_running_twice_leaves_one_section(self, tmp_path):
        readme = self._readme(tmp_path)
        counts = [SourceCount(source="A", files=1, records=2)]

        update_readme(counts, readme)
        update_readme(counts, readme)

        text = Path(readme).read_text(encoding="utf-8")
        assert text.count(START_MARKER) == 1
        assert text.count(END_MARKER) == 1

    def test_missing_markers_raise(self, tmp_path):
        readme = _write(tmp_path / "README.md", "# Title\n")

        with pytest.raises(ValueError, match="not found"):
            update_readme([], readme)
