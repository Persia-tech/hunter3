from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import matplotlib
import pytest

matplotlib.use("Agg")


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "plot_bitcoin_cycle_research.py"
SPEC = importlib.util.spec_from_file_location("plot_bitcoin_cycle_research", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_sample_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "date",
                "price",
                "opportunity_score",
                "overheat_score",
                "future_return_365d_pct",
            ]
        )
        writer.writerows(
            [
                ("2020-01-01", "7000", "20", "10", "50"),
                ("2020-02-01", "9000", "65", "15", "25"),
                ("2020-03-01", "5000", "85", "5", "100"),
                ("2021-01-01", "30000", "10", "70", "-20"),
                ("2021-02-01", "45000", "5", "85", ""),
            ]
        )


def test_generate_all_charts_creates_four_nonempty_pngs(tmp_path: Path) -> None:
    csv_path = tmp_path / "bitcoin_cycle_backtest.csv"
    reports_dir = tmp_path / "reports"
    _write_sample_csv(csv_path)

    outputs = MODULE.generate_all_charts(csv_path, reports_dir)

    assert len(outputs) == 4
    for output in outputs:
        assert output.exists()
        assert output.stat().st_size > 0


def test_missing_csv_has_helpful_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError) as exc_info:
        MODULE.load_backtest_csv(missing)

    message = str(exc_info.value)
    assert "Backtest CSV not found" in message
    assert "backtest_bitcoin_cycle.py" in message
