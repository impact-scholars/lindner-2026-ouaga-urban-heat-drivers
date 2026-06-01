"""
GCCM directional asymmetry bar chart — SHAP-style publication quality.

Reads summary.csv from each GCCM run and produces horizontal bar charts
matching SHAP's visual style.

Output
------
    figures/pub/gccm_asymmetry_tau1.png    (single panel for composite)
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from figure_style import apply_style, style_ax, COLORS, FONT, FIG_DIR, GCCM_DATA

apply_style()

# Predictor group labels
GROUPS = {
    "built_density": "C", "green_density": "C", "distance_to_water": "C",
    "distance_to_roads": "C", "DEM": "C",
    "NDBI": "A", "BSI": "A", "NDVI": "A",
}


def plot_asymmetry(summary_path, title, ax):
    """
    Draw a single asymmetry bar panel on the given axes.

    Parameters
    ----------
    summary_path : Path
        Path to summary.csv.
    title : str
        Panel title.
    ax : matplotlib.axes.Axes
        Target axes.
    """
    df = pd.read_csv(summary_path)
    df["asymmetry"] = df["rho_pred_to_LST"] - df["rho_LST_to_pred"]
    df["label"] = df["predictor"]

    df = df.sort_values("asymmetry", ascending=True)

    y = np.arange(len(df))
    bar_height = 0.42

    ax.barh(
        y + bar_height / 2, df["rho_pred_to_LST"], bar_height,
        color=COLORS["forward"],
        label=r"pred $\rightarrow$ LST (forward)",
        edgecolor="white", linewidth=0.5,
    )
    ax.barh(
        y - bar_height / 2, df["rho_LST_to_pred"], bar_height,
        color=COLORS["reverse"], alpha=0.75,
        label=r"LST $\rightarrow$ pred (reverse)",
        edgecolor="white", linewidth=0.5,
    )

    # Annotate asymmetry values
    for i, (_, row) in enumerate(df.iterrows()):
        asym = row["asymmetry"]
        x_pos = max(row["rho_pred_to_LST"], row["rho_LST_to_pred"]) + 0.01
        color = COLORS["positive"] if asym > 0 else COLORS["negative"]
        ax.text(
            x_pos, i, f"{asym:+.3f}",
            va="center", fontsize=FONT["annotation"],
            fontweight="bold", color=color,
        )

    ax.set_yticks(y)
    ax.set_yticklabels(df["label"], fontsize=FONT["feature_name"])
    ax.set_xlabel(r"Cross-mapping skill ($\rho$)", fontsize=FONT["axis_label"])
    ax.set_title(title, fontsize=FONT["title"], fontweight="bold")
    ax.legend(
        fontsize=14, loc="upper left",
        bbox_to_anchor=(0.6, 0.85), frameon=True, ncol=1,
    )
    ax.set_xlim(0, ax.get_xlim()[1] + 0.08)

    # SHAP-style: subtle vertical reference lines instead of grid
    for xval in np.arange(0.1, 0.9, 0.1):
        ax.axvline(xval, color=COLORS["hline"], linewidth=0.5,
                    dashes=(1, 5), zorder=-1)

    # SHAP-style: subtle horizontal lines between features
    for yval in y:
        ax.axhline(yval, color=COLORS["hline"], linewidth=0.5,
                    dashes=(1, 5), zorder=-1)

    style_ax(ax)
    ax.spines["left"].set_visible(False)


# ---------------------------------------------------------------------------
# Single-panel figure (tau=1 only, for composite)
# ---------------------------------------------------------------------------
tau1_key = "E=3, tau=1 (block scale)"
tau1_summary = GCCM_DATA[tau1_key]["summary"]

if tau1_summary.exists():
    fig, ax = plt.subplots(figsize=(10, 8))
    plot_asymmetry(tau1_summary, "GCCM Directional Asymmetry", ax)
    plt.tight_layout()
    out_single = FIG_DIR / "gccm_asymmetry_tau1.png"
    plt.savefig(out_single)
    plt.close()
    print(f"Saved: {out_single}")
