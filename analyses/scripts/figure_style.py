"""
Shared figure style — mimics SHAP's internal styling exactly.

Usage
-----
    from figure_style import apply_style, COLORS, FIG_DIR

    apply_style()  # call once at top of script

Replicates the SHAP library's visual style: clean white background,
no gridlines, hidden top/right spines, matching font sizes and colors.
Font sizes are scaled UP so panels remain legible when composited at
~1/4 page height.
"""

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = PROJECT_ROOT / "figures" / "pub"
FIG_DIR.mkdir(parents=True, exist_ok=True)

GCCM_DATA = {
    "E=3, tau=1 (block scale)": {
        "results": PROJECT_ROOT / "outputs/gccm/main_E3_tau1/results.csv",
        "summary": PROJECT_ROOT / "outputs/gccm/main_E3_tau1/summary.csv",
    },
}

# ---------------------------------------------------------------------------
# Colors — exact SHAP palette (computed from LCH colour space)
# ---------------------------------------------------------------------------
COLORS = {
    # Primary SHAP blue/red (from shap.plots.colors._colors)
    "blue": "#008afa",
    "red": "#ff0051",
    # Light variants
    "light_blue": "#7fc4fc",
    "light_red": "#ff7fa7",
    # Semantic aliases for GCCM plots
    "forward": "#008afa",       # pred causes LST (SHAP blue)
    "reverse": "#ff0051",       # LST causes pred (SHAP red)
    # Asymmetry annotations
    "positive": "#008afa",      # positive asymmetry (blue = expected)
    "negative": "#ff0051",      # negative asymmetry (red = unexpected)
    # SHAP grays
    "axis": "#333333",
    "tick_label": "#999999",
    "hline": "#cccccc",
    "vline": "#999999",
}

# ---------------------------------------------------------------------------
# Font sizes — SHAP uses 13/12/11. We scale 2× so text survives
# compositing at ~1/4 page height. SHAP uses default sans-serif.
# ---------------------------------------------------------------------------
FONT = {
    "family": "sans-serif",
    "feature_name": 22,    # SHAP: 13 → 2× for composite
    "axis_label": 22,      # SHAP: 13 → 2×
    "tick": 18,            # SHAP: 11 → ~2×
    "legend": 18,          # SHAP: 12 → ~2×
    "colorbar_label": 20,  # SHAP: 12 → ~2×
    "title": 24,           # panel titles
    "annotation": 16,      # asymmetry value labels
    "panel_label": 28,     # (a), (b), etc.
}

DPI = 300


def apply_style():
    """Apply SHAP-matching matplotlib rcParams."""
    mpl.rcParams.update({
        # Font
        "font.family": FONT["family"],
        "font.sans-serif": ["DejaVu Sans"],  # SHAP's default
        "font.size": FONT["tick"],

        # Axes — SHAP style: clean, minimal
        "axes.titlesize": FONT["title"],
        "axes.titleweight": "bold",
        "axes.labelsize": FONT["axis_label"],
        "axes.labelcolor": COLORS["axis"],
        "axes.linewidth": 0.8,
        "axes.edgecolor": COLORS["axis"],
        "axes.grid": False,           # SHAP has NO grid
        "axes.spines.top": False,     # SHAP hides top spine
        "axes.spines.right": False,   # SHAP hides right spine
        "axes.facecolor": "white",

        # Ticks
        "xtick.labelsize": FONT["tick"],
        "ytick.labelsize": FONT["tick"],
        "xtick.color": COLORS["axis"],
        "ytick.color": COLORS["axis"],
        "xtick.direction": "out",
        "ytick.direction": "out",

        # Legend
        "legend.fontsize": FONT["legend"],
        "legend.framealpha": 0.9,
        "legend.edgecolor": "0.8",
        "legend.fancybox": True,

        # Figure
        "figure.facecolor": "white",
        "figure.dpi": DPI,
        "savefig.dpi": DPI,
        "savefig.bbox": "tight",
        "savefig.facecolor": "white",
        "savefig.pad_inches": 0.15,

        # Lines
        "lines.linewidth": 2.0,
        "lines.markersize": 6,
    })


def style_ax(ax, ylabel=True):
    """
    Apply SHAP-style finishing touches to an axes.

    Hides spines, adds subtle reference lines, sets tick style.
    Call this after plotting data.
    """
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", labelsize=FONT["tick"])
    if not ylabel:
        ax.set_ylabel("")
