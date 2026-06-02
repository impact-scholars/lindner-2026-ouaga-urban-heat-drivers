"""
GCCM convergence plots — SHAP-style publication quality.

Reads results.csv from each GCCM run and produces faceted convergence
plots in matplotlib matching SHAP's visual style exactly.

Output
------
    figures/pub/gccm_convergence_tau1.png
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from figure_style import apply_style, style_ax, COLORS, FONT, FIG_DIR, GCCM_DATA

apply_style()

# Predictor display order (causal first, then associative)
PRED_ORDER = [
    "built_density", "green_density", "distance_to_roads",
    "distance_to_water", "DEM",
    "NDVI", "NDBI", "BSI",
]


def plot_convergence(results_path, title, output_path):
    """
    Plot GCCM convergence curves for all predictors in a faceted grid.

    Parameters
    ----------
    results_path : Path
        Path to results.csv.
    title : str
        Figure suptitle.
    output_path : Path
        Where to save the PNG.
    """
    df = pd.read_csv(results_path)

    df["is_pred_to_lst"] = df["is_pred_to_lst"].map(
        {"TRUE": True, "FALSE": False, True: True, False: False}
    )

    predictors = [p for p in PRED_ORDER if p in df["predictor"].unique()]
    n = len(predictors)
    ncols = min(4, n)
    nrows = int(np.ceil(n / ncols))

    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(12 * ncols, 10 * nrows),
        squeeze=False,
    )

    for idx, pred in enumerate(predictors):
        ax = axes[idx // ncols][idx % ncols]
        sub = df[df["predictor"] == pred]

        for is_fwd, label, color, ls in [
            (True, r"pred $\rightarrow$ LST", COLORS["forward"], "-"),
            (False, r"LST $\rightarrow$ pred", COLORS["reverse"], "--"),
        ]:
            d = sub[sub["is_pred_to_lst"] == is_fwd].sort_values("libsize")
            ax.fill_between(
                d["libsize"], d["ci_lower"], d["ci_upper"],
                color=color, alpha=0.12,
            )
            ax.plot(
                d["libsize"], d["rho"],
                color=color, linestyle=ls, marker="o",
                linewidth=8, markersize=18,
                label=label,
            )

        ax.set_title(pred, fontsize=58, fontweight="bold")
        ax.set_ylim(0, 0.8)
        ax.axhline(0, color=COLORS["hline"], linewidth=0.5)

        row_idx = idx // ncols
        col_idx = idx % ncols
        # x-axis label only on bottom row
        if row_idx == nrows - 1:
            ax.set_xlabel("Library size (pixels)", fontsize=52)
        else:
            ax.set_xlabel("")
        # SHAP-style subtle horizontal reference lines
        for yval in np.arange(0.1, 0.8, 0.1):
            ax.axhline(yval, color=COLORS["hline"], linewidth=0.5,
                        dashes=(1, 5), zorder=-1)

        style_ax(ax)
        ax.tick_params(axis="y", labelsize=42)
        ax.tick_params(axis="x", labelsize=42)

        # Set axis labels AFTER style_ax to avoid rcParams override
        if col_idx == 0:
            ax.set_ylabel(r"Cross-map skill ($\rho$)", fontsize=56)
        else:
            ax.set_ylabel("")

    # Hide unused axes
    for idx in range(n, nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    # Single shared legend at bottom
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(
        handles, labels,
        loc="lower center",
        ncol=2,
        fontsize=40,
        frameon=True,
        bbox_to_anchor=(0.5, -0.035),
    )

    fig.suptitle("GCCM Convergence", fontsize=70, fontweight="bold", y=1.01)
    plt.tight_layout(rect=[0, 0.04, 1, 0.98], h_pad=4, w_pad=4)
    plt.savefig(output_path)
    plt.close()
    print(f"Saved: {output_path}")


FILENAME_MAP = {
    "E=3, tau=1 (block scale)": "gccm_convergence_tau1.png",
}

for config_label, paths in GCCM_DATA.items():
    results_path = paths["results"]
    if not results_path.exists():
        print(f"Skipping {config_label}: {results_path} not found")
        continue

    plot_convergence(
        results_path,
        title=f"GCCM Convergence: {config_label}",
        output_path=FIG_DIR / FILENAME_MAP[config_label],
    )
