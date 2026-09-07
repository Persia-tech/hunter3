"""Generate research charts from the Bitcoin cycle backtest CSV."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

import matplotlib.dates as mdates
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "reports" / "bitcoin_cycle_backtest.csv"
DEFAULT_REPORTS_DIR = ROOT / "reports"
SCORE_BANDS = (
    (0, 19, "00-19"),
    (20, 39, "20-39"),
    (40, 59, "40-59"),
    (60, 79, "60-79"),
    (80, 100, "80-100"),
)


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return float(value)


def load_backtest_csv(path: Path) -> list[dict[str, object]]:
    """Load and validate the backtest CSV used by the research plots."""
    if not path.exists():
        raise FileNotFoundError(
            f"Backtest CSV not found: {path}\n"
            "Run this first:\n"
            "python scripts\\backtest_bitcoin_cycle.py"
        )

    required = {
        "date",
        "price",
        "opportunity_score",
        "overheat_score",
        "future_return_365d_pct",
    }
    rows: list[dict[str, object]] = []

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(
                "Backtest CSV is missing required columns: " + ", ".join(sorted(missing))
            )

        for raw in reader:
            rows.append(
                {
                    "date": datetime.strptime(raw["date"], "%Y-%m-%d"),
                    "price": float(raw["price"]),
                    "opportunity_score": int(raw["opportunity_score"]),
                    "overheat_score": int(raw["overheat_score"]),
                    "future_return_365d_pct": _to_float(raw.get("future_return_365d_pct")),
                }
            )

    if not rows:
        raise ValueError("Backtest CSV contains no data rows")
    return rows


def _save(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=160, bbox_inches="tight")
    plt.close()


def independent_episode_rows(
    rows: list[dict[str, object]],
    *,
    score_key: str,
    threshold: int,
    cooldown_days: int = 90,
) -> list[dict[str, object]]:
    """Return first upward threshold crossings separated by a cooldown window."""
    if score_key not in {"opportunity_score", "overheat_score"}:
        raise ValueError("score_key must be opportunity_score or overheat_score")
    if cooldown_days < 0:
        raise ValueError("cooldown_days must be non-negative")

    selected: list[dict[str, object]] = []
    previous_score: int | None = None
    last_selected_date: datetime | None = None

    for row in sorted(rows, key=lambda item: item["date"]):
        score = int(row[score_key])
        crossed = score >= threshold and (previous_score is None or previous_score < threshold)
        row_date = row["date"]
        assert isinstance(row_date, datetime)

        cooldown_ok = (
            last_selected_date is None
            or row_date >= last_selected_date + timedelta(days=cooldown_days)
        )
        if crossed and cooldown_ok:
            selected.append(row)
            last_selected_date = row_date

        previous_score = score

    return selected


def plot_price_with_signals(rows: list[dict[str, object]], output_path: Path) -> None:
    dates = [row["date"] for row in rows]
    prices = [row["price"] for row in rows]

    plt.figure(figsize=(14, 7))
    plt.plot(dates, prices, linewidth=1.4, label="BTC price")
    plt.yscale("log")

    signal_specs = (
        ("Opportunity >= 60", "opportunity_score", 60, 16),
        ("Opportunity >= 80", "opportunity_score", 80, 30),
        ("Overheat >= 60", "overheat_score", 60, 16),
        ("Overheat >= 80", "overheat_score", 80, 30),
    )
    for label, key, threshold, size in signal_specs:
        selected = [row for row in rows if int(row[key]) >= threshold]
        if selected:
            plt.scatter(
                [row["date"] for row in selected],
                [row["price"] for row in selected],
                s=size,
                label=label,
            )

    plt.title("Bitcoin Price with Opportunity / Overheat Signals")
    plt.xlabel("Date")
    plt.ylabel("BTC price (log scale)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _save(output_path)


def plot_independent_episodes(rows: list[dict[str, object]], output_path: Path) -> None:
    """Plot only independent threshold-crossing episodes, not every high-score day."""
    dates = [row["date"] for row in rows]
    prices = [row["price"] for row in rows]

    plt.figure(figsize=(14, 7))
    plt.plot(dates, prices, linewidth=1.4, label="BTC price")
    plt.yscale("log")

    specs = (
        ("Opportunity crossing >= 60", "opportunity_score", 60, 45),
        ("Opportunity crossing >= 80", "opportunity_score", 80, 75),
        ("Overheat crossing >= 60", "overheat_score", 60, 45),
        ("Overheat crossing >= 80", "overheat_score", 80, 75),
    )
    for label, key, threshold, size in specs:
        selected = independent_episode_rows(
            rows,
            score_key=key,
            threshold=threshold,
            cooldown_days=90,
        )
        if selected:
            plt.scatter(
                [row["date"] for row in selected],
                [row["price"] for row in selected],
                s=size,
                label=label,
            )

    plt.title("Bitcoin Independent Cycle Signal Episodes (90-Day Cooldown)")
    plt.xlabel("Date")
    plt.ylabel("BTC price (log scale)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _save(output_path)


def plot_scores_over_time(rows: list[dict[str, object]], output_path: Path) -> None:
    dates = [row["date"] for row in rows]
    opportunity = [row["opportunity_score"] for row in rows]
    overheat = [row["overheat_score"] for row in rows]

    plt.figure(figsize=(14, 6))
    plt.plot(dates, opportunity, linewidth=1.4, label="Opportunity Score")
    plt.plot(dates, overheat, linewidth=1.4, label="Overheat Score")
    plt.axhline(60, linewidth=1, linestyle="--", label="Threshold 60")
    plt.axhline(80, linewidth=1, linestyle=":", label="Threshold 80")
    plt.ylim(0, 100)
    plt.title("Bitcoin Cycle Scores Over Time")
    plt.xlabel("Date")
    plt.ylabel("Score")
    plt.grid(True, alpha=0.3)
    plt.legend()
    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _save(output_path)


def _plot_score_vs_return(
    rows: list[dict[str, object]],
    *,
    score_key: str,
    title: str,
    x_label: str,
    output_path: Path,
) -> None:
    filtered = [row for row in rows if row["future_return_365d_pct"] is not None]
    x = [row[score_key] for row in filtered]
    y = [row["future_return_365d_pct"] for row in filtered]

    plt.figure(figsize=(9, 6))
    plt.scatter(x, y, s=10, alpha=0.5)
    plt.axhline(0, linewidth=1, linestyle="--")
    plt.axvline(60, linewidth=1, linestyle="--")
    plt.axvline(80, linewidth=1, linestyle=":")
    plt.title(title)
    plt.xlabel(x_label)
    plt.ylabel("Future 365-day return (%)")
    plt.grid(True, alpha=0.3)
    _save(output_path)


def plot_opportunity_scatter(rows: list[dict[str, object]], output_path: Path) -> None:
    _plot_score_vs_return(
        rows,
        score_key="opportunity_score",
        title="Opportunity Score vs Future 365-Day BTC Return",
        x_label="Opportunity Score",
        output_path=output_path,
    )


def plot_overheat_scatter(rows: list[dict[str, object]], output_path: Path) -> None:
    _plot_score_vs_return(
        rows,
        score_key="overheat_score",
        title="Overheat Score vs Future 365-Day BTC Return",
        x_label="Overheat Score",
        output_path=output_path,
    )


def score_band_medians(
    rows: list[dict[str, object]],
    *,
    score_key: str,
) -> list[tuple[str, float | None, int]]:
    """Return fixed score-band median 365-day returns and valid sample counts."""
    result: list[tuple[str, float | None, int]] = []
    for low, high, label in SCORE_BANDS:
        values = [
            float(row["future_return_365d_pct"])
            for row in rows
            if low <= int(row[score_key]) <= high
            and row["future_return_365d_pct"] is not None
        ]
        result.append((label, median(values) if values else None, len(values)))
    return result


def plot_score_band_returns(
    rows: list[dict[str, object]],
    *,
    score_key: str,
    title: str,
    output_path: Path,
) -> None:
    summaries = score_band_medians(rows, score_key=score_key)
    labels = [label for label, _, _ in summaries]
    medians = [value if value is not None else 0.0 for _, value, _ in summaries]
    counts = [count for _, _, count in summaries]

    plt.figure(figsize=(9, 6))
    bars = plt.bar(labels, medians)
    plt.axhline(0, linewidth=1, linestyle="--")
    plt.title(title)
    plt.xlabel("Score band")
    plt.ylabel("Median future 365-day return (%)")
    plt.grid(True, axis="y", alpha=0.3)

    for bar, count, value in zip(bars, counts, medians):
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"n={count}",
            ha="center",
            va="bottom" if value >= 0 else "top",
            fontsize=9,
        )

    _save(output_path)


def generate_all_charts(
    input_csv: Path = DEFAULT_INPUT,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
) -> list[Path]:
    rows = load_backtest_csv(input_csv)
    outputs = [
        reports_dir / "bitcoin_price_with_signals.png",
        reports_dir / "bitcoin_cycle_scores.png",
        reports_dir / "opportunity_vs_future_365d.png",
        reports_dir / "overheat_vs_future_365d.png",
        reports_dir / "bitcoin_independent_signal_episodes.png",
        reports_dir / "opportunity_band_median_365d.png",
        reports_dir / "overheat_band_median_365d.png",
    ]

    plot_price_with_signals(rows, outputs[0])
    plot_scores_over_time(rows, outputs[1])
    plot_opportunity_scatter(rows, outputs[2])
    plot_overheat_scatter(rows, outputs[3])
    plot_independent_episodes(rows, outputs[4])
    plot_score_band_returns(
        rows,
        score_key="opportunity_score",
        title="Opportunity Score Bands vs Median Future 365-Day BTC Return",
        output_path=outputs[5],
    )
    plot_score_band_returns(
        rows,
        score_key="overheat_score",
        title="Overheat Score Bands vs Median Future 365-Day BTC Return",
        output_path=outputs[6],
    )
    return outputs


def main() -> None:
    outputs = generate_all_charts()
    print(f"Loaded backtest data from: {DEFAULT_INPUT}")
    for path in outputs:
        print(f"Saved: {path}")
    print("Done.")


if __name__ == "__main__":
    main()
