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
                ("2020-02-02", "9100", "66", "15", "20"),
                ("2020-03-01", "5000", "85", "5", "100"),
                ("2020-07-15", "9500", "55", "10", "30"),
                ("2020-08-01", "10000", "65", "10", "35"),
                ("2021-01-01", "30000", "10", "70", "-20"),
                ("2021-01-02", "31000", "10", "72", "-25"),
                ("2021-05-01", "45000", "5", "85", ""),
            ]
        )


def test_generate_all_charts_creates_seven_nonempty_pngs(tmp_path: Path) -> None:
    csv_path = tmp_path / "bitcoin_cycle_backtest.csv"
    reports_dir = tmp_path / "reports"
    _write_sample_csv(csv_path)

    outputs = MODULE.generate_all_charts(csv_path, reports_dir)

    assert len(outputs) == 7
    for output in outputs:
        assert output.exists()
        assert output.stat().st_size > 0


def test_independent_episode_rows_counts_crossings_not_consecutive_days(tmp_path: Path) -> None:
    csv_path = tmp_path / "bitcoin_cycle_backtest.csv"
    _write_sample_csv(csv_path)
    rows = MODULE.load_backtest_csv(csv_path)

    episodes = MODULE.independent_episode_rows(
        rows,
        score_key="opportunity_score",
        threshold=60,
        cooldown_days=90,
    )

    assert len(episodes) == 2
    assert episodes[0]["date"].strftime("%Y-%m-%d") == "2020-02-01"
    assert episodes[1]["date"].strftime("%Y-%m-%d") == "2020-08-01"


def test_score_band_medians_uses_only_valid_future_returns(tmp_path: Path) -> None:
    csv_path = tmp_path / "bitcoin_cycle_backtest.csv"
    _write_sample_csv(csv_path)
    rows = MODULE.load_backtest_csv(csv_path)

    summaries = MODULE.score_band_medians(rows, score_key="overheat_score")
    high_band = summaries[-1]

    assert high_band[0] == "80-100"
    assert high_band[1] is None
    assert high_band[2] == 0


def test_missing_csv_has_helpful_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError) as exc_info:
        MODULE.load_backtest_csv(missing)

    message = str(exc_info.value)
    assert "Backtest CSV not found" in message
    assert "backtest_bitcoin_cycle.py" in message
