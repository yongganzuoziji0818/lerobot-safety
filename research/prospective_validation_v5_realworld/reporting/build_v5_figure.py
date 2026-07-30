"""Create the prespecified V5 external-validation figure from frozen JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np


POLICIES = ("pi0", "pi0.5", "grootn1.7")
POLICY_LABELS = {
    "pi0": r"$\pi_0$",
    "pi0.5": r"$\pi_{0.5}$",
    "grootn1.7": "GR00T N1.7",
}
CONTRACTS = (
    "RW0_failure_only",
    "RW1_half_suboptimal",
    "RW2_non_success",
)
CONTRACT_LABELS = ("RW0", "RW1", "RW2")
COLORS = {
    "pi0": "#0072B2",
    "pi0.5": "#009E73",
    "grootn1.7": "#D55E00",
}
MARKERS = {"pi0": "o", "pi0.5": "s", "grootn1.7": "^"}


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans"],
            "font.size": 8,
            "axes.labelsize": 8,
            "axes.titlesize": 9,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "legend.fontsize": 7,
            "axes.linewidth": 0.8,
            "lines.linewidth": 1.3,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    outputs = [
        args.output_prefix.with_suffix(".pdf"),
        args.output_prefix.with_suffix(".png"),
        args.output_prefix.with_suffix(".tiff"),
    ]
    if any(path.exists() for path in outputs):
        raise SystemExit("REFUSE_EXISTING_V5_FIGURE_OUTPUT")
    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)

    result = json.loads(args.result.read_text(encoding="utf-8"))
    points = result["primary_point_estimands"]
    intervals = result["bootstrap"]["pairwise_contrasts"]

    configure_style()
    fig, (ax_a, ax_b) = plt.subplots(
        1,
        2,
        figsize=(7.2, 3.45),
        gridspec_kw={"width_ratios": [0.9, 1.35]},
    )

    x = np.asarray([0.0, 0.5, 1.0])
    for policy in POLICIES:
        y = np.asarray(
            [
                points[contract]["macro_task_equal_risk"][policy]
                for contract in CONTRACTS
            ]
        )
        ax_a.plot(
            x,
            y,
            color=COLORS[policy],
            marker=MARKERS[policy],
            markersize=4.5,
            label=POLICY_LABELS[policy],
        )
    ax_a.set_xlim(-0.04, 1.04)
    ax_a.set_ylim(0.0, 1.0)
    ax_a.set_xticks(x, CONTRACT_LABELS)
    ax_a.set_xlabel("Outcome contract")
    ax_a.set_ylabel("Equal-task macro risk")
    ax_a.set_title("Physical SO-101 outcome risk")
    ax_a.legend(frameon=False, loc="upper left")

    pairs = [
        ("pi0", "pi0.5"),
        ("pi0", "grootn1.7"),
        ("pi0.5", "grootn1.7"),
    ]
    pair_colors = ("#0072B2", "#CC79A7", "#D55E00")
    rows = []
    for contract_index, contract in enumerate(CONTRACTS):
        for pair_index, (a, b) in enumerate(pairs):
            key = f"{contract}:{a}_minus_{b}"
            item = intervals[key]
            point = points[contract]["pairwise_macro_differences"][
                f"{a}_minus_{b}"
            ]
            rows.append(
                (
                    contract_index,
                    pair_index,
                    point,
                    item["simultaneous_95_low"],
                    item["simultaneous_95_high"],
                    f"{CONTRACT_LABELS[contract_index]}  "
                    f"{POLICY_LABELS[a]} - {POLICY_LABELS[b]}",
                )
            )
    y_positions = np.arange(len(rows))[::-1]
    for y_position, row in zip(y_positions, rows):
        _, pair_index, point, low, high, _ = row
        ax_b.hlines(
            y_position,
            low,
            high,
            color=pair_colors[pair_index],
            linewidth=1,
        )
        ax_b.plot(
            point,
            y_position,
            marker=("o", "s", "^")[pair_index],
            color=pair_colors[pair_index],
            markersize=4,
            linestyle="none",
        )
    ax_b.axvline(0.0, color="#555555", linewidth=0.8, linestyle="--")
    ax_b.set_yticks(y_positions, [row[-1] for row in rows])
    ax_b.set_xlabel("Pairwise macro-risk difference")
    ax_b.set_title("Bonferroni-adjusted simultaneous 95% intervals")

    for ax, label in ((ax_a, "A"), (ax_b, "B")):
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.text(
            -0.14,
            1.05,
            label,
            transform=ax.transAxes,
            fontsize=10,
            fontweight="bold",
            va="top",
        )
    fig.tight_layout(w_pad=1.4)
    fig.savefig(outputs[0], bbox_inches="tight")
    fig.savefig(outputs[1], dpi=500, bbox_inches="tight")
    fig.savefig(outputs[2], dpi=500, bbox_inches="tight")
    plt.close(fig)
    print("PASS_V5_PUBLICATION_FIGURE")


if __name__ == "__main__":
    main()
