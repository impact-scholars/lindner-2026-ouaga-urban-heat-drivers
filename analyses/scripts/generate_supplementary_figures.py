#!/usr/bin/env python3
"""Generate supplementary figures and tables for the micropublication.

Produces six artifacts under ``figures/pub/supplementary/``:

* ``figS1_spatial_features.png`` — per-band maps of all 10 raster bands. Code
  ported verbatim from notebook ``02_eda.ipynb`` cell 14 so the supplementary
  figure is the same one the EDA notebook produces.
* ``figS2_methods_workflow.png`` — high-resolution rasterisation of the
  hand-designed workflow diagram authored in slideware (PowerPoint / Keynote)
  and exported to ``figures/methods_workflow.svg``. There is no upstream
  Python code that produces this figure; the SVG is the source of truth and
  ``rsvg-convert`` is the build step. Whitespace around the content is
  trimmed automatically.
* ``figS3_heatwave_analysis.png`` — high-resolution rasterisation of the
  multi-panel heatwave analysis composite at
  ``figures/ouagadougou-heatwaves-example-days-wide.svg``. Like the methods
  diagram, the SVG is a hand-composed multi-panel layout. The underlying
  per-panel analyses live in ``notebooks/Heatwave/Heatwave_Analysis_Ouagadougou.ipynb``
  (which ships in the submission alongside the source data
  ``Ouagadougou_2001_2024_daily_tmax.nc``). Whitespace trimmed.
* ``figS4_pearson_correlation.png`` — pairwise Pearson correlation among the
  nine continuous features, computed from the same dataset notebook 03 uses.
* ``hyperparameters.json`` — selected hyperparameters per model, read directly
  from the pickled estimators rather than the hardcoded ``BEST_PARAMS_*``
  dicts in the notebook.
* ``test_metrics.csv`` — accuracy / precision / recall / F1 / Cohen's kappa
  per model on the test split, computed by predicting once with each pickled
  estimator. Doubles as a sanity-check artifact: the script aborts if any
  metric drifts from the values published in Table 4 of the paper.

After producing the test-metrics CSV the script compares F1 and kappa for
each model against the values published in the paper (Table 4) with a 1%
tolerance and exits with a non-zero status if any row drifts. This catches
silent library-version drift before any downstream artifact is consumed.

Prerequisites
-------------
* Pickled models extracted into ``models/`` (flat layout, no subdirectory):
  ``unzip -n models/Hotspotters_Models.zip -d models/``.
* ``rsvg-convert`` on ``PATH`` (``brew install librsvg``).
* The processed raster stack at ``data/processed/ouaga_aligned_stack.tif``
  (regenerable via ``notebooks/01_processing_pipeline.ipynb`` or downloadable
  from Zenodo).

Usage
-----
::

    python scripts/generate_supplementary_figures.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from mpl_toolkits.axes_grid1 import make_axes_locatable
from PIL import Image, ImageChops
from sklearn.metrics import (
    accuracy_score,
    cohen_kappa_score,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data import load_dataset  # noqa: E402  (after sys.path tweak)

CONFIG_PATH = PROJECT_ROOT / "config" / "processing.yaml"
SUPP_DIR = PROJECT_ROOT / "figures" / "pub" / "supplementary"
MODELS_DIR = PROJECT_ROOT / "models"

# Published model performance from the micropublication's Table 4. Used as
# a sanity-check target for the regenerated test_metrics.csv.
PAPER_METRICS = {
    "XGBoost":       {"F1": 0.700, "Kappa": 0.671},
    "Random Forest": {"F1": 0.610, "Kappa": 0.579},
    "SVM":           {"F1": 0.408, "Kappa": 0.376},
}

# Hyperparameters worth surfacing per model. ``model.get_params()`` returns
# many uninformative keys (e.g., ``n_jobs``); we filter to the configuration
# parameters that drove the published results.
HYPERPARAM_KEYS = {
    "XGBoost":       ["n_estimators", "max_depth", "learning_rate",
                      "reg_alpha", "reg_lambda", "random_state"],
    "Random Forest": ["n_estimators", "max_depth", "random_state"],
    "SVM":           ["C", "kernel", "gamma", "probability", "random_state"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_rsvg() -> None:
    """Fail loudly if ``rsvg-convert`` isn't on PATH."""
    if shutil.which("rsvg-convert") is None:
        raise RuntimeError(
            "rsvg-convert not found on PATH. Install with: brew install librsvg"
        )


def _trim_png_whitespace(path: Path, padding: int = 20) -> None:
    """Crop a PNG to its non-white content bounding box, in place.

    The slideware-exported SVGs include large blank canvas around the
    content. After ``rsvg-convert`` rasterises them, the resulting PNG has
    the same blank borders. This function flattens the image onto a white
    background, locates the bounding box of non-white pixels, and crops to
    that box (plus a small padding so content doesn't touch the edge).

    The output is RGB (no alpha). The source SVGs use a white background
    with no meaningful transparency, so dropping alpha is intentional.
    """
    img = Image.open(path)
    # Flatten to RGB on a white background so transparent pixels are treated
    # as white for the bounding-box search.
    if img.mode == "RGBA":
        rgb = Image.new("RGB", img.size, (255, 255, 255))
        rgb.paste(img, mask=img.split()[-1])
        img_rgb = rgb
    else:
        img_rgb = img.convert("RGB")
    bg = Image.new("RGB", img_rgb.size, (255, 255, 255))
    bbox = ImageChops.difference(img_rgb, bg).getbbox()
    if bbox is None:
        return  # all-white image, nothing to crop
    x0 = max(bbox[0] - padding, 0)
    y0 = max(bbox[1] - padding, 0)
    x1 = min(bbox[2] + padding, img_rgb.width)
    y1 = min(bbox[3] + padding, img_rgb.height)
    img_rgb.crop((x0, y0, x1, y1)).save(path)


def _convert_svg_to_png(src: Path, dst: Path, height: int = 2400) -> None:
    """Rasterise an SVG to PNG using ``rsvg-convert``, then trim whitespace."""
    if not src.exists():
        raise FileNotFoundError(f"SVG not found: {src}")
    subprocess.run(
        ["rsvg-convert", "-h", str(height), str(src), "-o", str(dst)],
        check=True,
    )
    _trim_png_whitespace(dst)
    print(f"  Saved: {dst.relative_to(PROJECT_ROOT)}")


def _metrics_from_predictions(y_test, y_pred, name: str) -> dict:
    """Compute classification metrics from precomputed predictions.

    ``precision_score``, ``recall_score`` and ``f1_score`` use the default
    ``average='binary'``, which is correct because hotspot is a binary 0/1
    target. If this script is ever extended to multi-class outputs, those
    averaging defaults need to change.
    """
    return {
        "Model": name,
        "Accuracy":  accuracy_score(y_test, y_pred),
        "Precision": precision_score(y_test, y_pred, zero_division=0),
        "Recall":    recall_score(y_test, y_pred, zero_division=0),
        "F1":        f1_score(y_test, y_pred, zero_division=0),
        "Kappa":     cohen_kappa_score(y_test, y_pred),
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def gen_fig_s1_spatial_features(config: dict) -> Path:
    """Per-band maps of all 10 raster bands (port of ``02_eda.ipynb`` cell 14)."""
    print("Fig. S1 — spatial distribution maps...")
    raster_data = config["raster_info"]["data_3d"]

    # Custom colormaps matching the GEE visualization palettes.
    cmap_ndvi = LinearSegmentedColormap.from_list(
        "ndvi", ["red", "gold", "green"]
    )
    cmap_ndbi_bsi = LinearSegmentedColormap.from_list(
        "ndbi_bsi", ["blue", "darkcyan", "gold", "red", "darkred"]
    )
    cmap_dist_water = LinearSegmentedColormap.from_list(
        "dist_water", ["blue", "cyan", "limegreen"]
    )
    cmap_built = LinearSegmentedColormap.from_list(
        "built", ["royalblue", "khaki", "red"]
    )
    cmap_green = LinearSegmentedColormap.from_list(
        "green", ["navy", "turquoise", "greenyellow"]
    )
    cmap_hotspot = LinearSegmentedColormap.from_list(
        "hotspot", ["cyan", "red"]
    )

    spatial_vis = {
        "NDVI":              (cmap_ndvi,        -0.5, 1),
        "NDBI":              (cmap_ndbi_bsi,    -0.5, 1),
        "BSI":               (cmap_ndbi_bsi,    -0.5, 1),
        "DEM":               ("terrain",         None, None),
        "distance_to_water": (cmap_dist_water,   None, None),
        "distance_to_roads": ("turbo",           None, None),
        "built_density":     (cmap_built,        0,    1),
        "green_density":     (cmap_green,        0,    1),
        "LST":               ("turbo",           25,   55),
        "hotspot":           (cmap_hotspot,      0,    1),
    }

    n_bands = len(config["band_names"])
    ncols = 4
    nrows = (n_bands + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 5 * nrows))
    axes = axes.flatten()

    for i, col in enumerate(config["band_names"]):
        ax = axes[i]
        band_idx = config["band_index"][col] - 1  # 1-indexed → 0-indexed
        band_data = np.ma.masked_invalid(raster_data[band_idx])

        cmap, vmin, vmax = spatial_vis[col]
        im = ax.imshow(band_data, cmap=cmap, vmin=vmin, vmax=vmax)
        ax.set_title(col, fontsize=12, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])

        divider = make_axes_locatable(ax)
        cax = divider.append_axes("right", size="5%", pad=0.05)
        if col == "LST":
            fig.colorbar(im, label="°C", cax=cax)
        elif col == "hotspot":
            fig.colorbar(im, label="1=hotspot / 0=non-hotspot", cax=cax)
        elif col == "DEM" or col.startswith("distance"):
            fig.colorbar(im, label="meters", cax=cax)
        elif col.endswith("density"):
            fig.colorbar(im, label="fraction", cax=cax)
        else:
            fig.colorbar(im, cax=cax)

    for j in range(n_bands, len(axes)):
        axes[j].set_visible(False)

    plt.suptitle(
        "Spatial Distribution of Variables", fontsize=14, fontweight="bold"
    )
    plt.tight_layout()
    out = SUPP_DIR / "figS1_spatial_features.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out.relative_to(PROJECT_ROOT)}")
    return out


def gen_fig_s2_methods_workflow() -> Path:
    """Rasterise the methods workflow SVG."""
    print("Fig. S2 — methods workflow (SVG → PNG)...")
    src = PROJECT_ROOT / "figures" / "methods_workflow.svg"
    dst = SUPP_DIR / "figS2_methods_workflow.png"
    _convert_svg_to_png(src, dst)
    return dst


def gen_fig_s3_heatwave() -> Path:
    """Rasterise the heatwave analysis composite SVG (wide variant)."""
    print("Fig. S3 — heatwave analysis (SVG → PNG)...")
    src = PROJECT_ROOT / "figures" / "ouagadougou-heatwaves-example-days-wide.svg"
    dst = SUPP_DIR / "figS3_heatwave_analysis.png"
    _convert_svg_to_png(src, dst)
    return dst


def gen_fig_s4_pearson(df: pd.DataFrame, band_names: list[str]) -> Path:
    """Pairwise Pearson correlation matrix of the nine continuous features."""
    print("Fig. S4 — Pearson correlation heatmap...")
    cols = [c for c in band_names if c != "hotspot"]  # drop the binary target
    pearson = df[cols].corr(method="pearson")

    # Styling matches the existing Spearman heatmap from notebook 02_eda
    # cell 20, so the two figures share a visual language.
    fig, ax = plt.subplots(figsize=(12, 10))
    mask = np.triu(np.ones_like(pearson, dtype=bool), k=1)
    cmap = sns.diverging_palette(
        250, 15, s=75, l=40, n=9, center="light", as_cmap=True
    )
    sns.heatmap(
        pearson, mask=mask, cmap=cmap, center=0,
        annot=True, fmt=".2f", square=True, linewidths=0.5,
        cbar_kws={"shrink": 0.8, "label": "Pearson r"},
        ax=ax,
    )
    ax.set_title(
        "Pairwise Pearson correlation of predictors and LST",
        fontsize=14, fontweight="bold"
    )
    plt.tight_layout()
    out = SUPP_DIR / "figS4_pearson_correlation.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out.relative_to(PROJECT_ROOT)}")
    return out


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _final_estimator(model):
    """Return the final estimator inside a sklearn Pipeline, or the model itself.

    The published SVM pipeline wraps ``StandardScaler`` + ``SVC``, so calling
    ``get_params()`` directly returns Pipeline-level keys (``svc__C`` etc.)
    rather than the SVC's natural keys. Drilling into the final step gives
    the readable ``C``, ``kernel``, ``gamma`` keys we want for the table.
    """
    if hasattr(model, "named_steps"):
        return list(model.named_steps.values())[-1]
    return model


def gen_table_s1_hyperparameters(models: dict) -> Path:
    """Selected hyperparameters per model, read from the pickled estimators."""
    print("Table S1 — hyperparameters...")
    summary = {
        name: {
            k: _final_estimator(model).get_params().get(k)
            for k in HYPERPARAM_KEYS[name]
        }
        for name, model in models.items()
    }
    out = SUPP_DIR / "hyperparameters.json"
    with open(out, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"  Saved: {out.relative_to(PROJECT_ROOT)}")
    return out


def gen_table_s2_test_metrics(y_test, y_preds: dict) -> pd.DataFrame:
    """Classification metrics on the test split, from precomputed predictions."""
    print("Table S2 — test metrics...")
    rows = [
        _metrics_from_predictions(y_test, y_pred, name)
        for name, y_pred in y_preds.items()
    ]
    df = pd.DataFrame(rows)
    out = SUPP_DIR / "test_metrics.csv"
    df.to_csv(out, index=False, float_format="%.4f")
    print(f"  Saved: {out.relative_to(PROJECT_ROOT)}")
    return df


# ---------------------------------------------------------------------------
# Sanity check
# ---------------------------------------------------------------------------

def sanity_check_metrics(metrics_df: pd.DataFrame, tol: float = 0.01) -> None:
    """Compare regenerated metrics to the published Table 4 values."""
    print("Sanity check — comparing test metrics to paper Table 4...")
    fail = False
    for _, row in metrics_df.iterrows():
        name = row["Model"]
        f1, kappa = row["F1"], row["Kappa"]
        target = PAPER_METRICS.get(name)
        if target is None:
            print(f"  ? {name}: no paper target; skipping check")
            continue
        f1_drift = abs(f1 - target["F1"])
        k_drift = abs(kappa - target["Kappa"])
        if f1_drift > tol or k_drift > tol:
            print(
                f"  ✗ {name}: F1={f1:.3f} (paper {target['F1']:.3f}, "
                f"Δ={f1_drift:.3f}); Kappa={kappa:.3f} "
                f"(paper {target['Kappa']:.3f}, Δ={k_drift:.3f})"
            )
            fail = True
        else:
            print(f"  ✓ {name}: F1={f1:.3f}, Kappa={kappa:.3f}")

    if fail:
        print()
        print("METRICS DRIFT EXCEEDS TOLERANCE.")
        print("Likely causes:")
        print("  * Library version drift (xgboost / sklearn newer than at paper-time)")
        print("  * Pickled models in models/ aren't the ones that produced the paper")
        print("  * Data path or split logic has changed")
        print("Investigate before consuming any of the outputs.")
        sys.exit(1)
    print("All metrics match paper within tolerance.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _skip_or_run(out_path: Path, label: str, fn) -> None:
    """Skip generation if the artifact already exists; print a notice."""
    if out_path.exists():
        print(f"{label} — already exists, skipping. ({out_path.relative_to(PROJECT_ROOT)})")
        return
    fn()


def main() -> None:
    SUPP_DIR.mkdir(parents=True, exist_ok=True)
    _check_rsvg()

    print(f"Loading dataset from {CONFIG_PATH.relative_to(PROJECT_ROOT)}...")
    df, config = load_dataset(str(CONFIG_PATH))

    # Figures S1–S4 (no models needed). Skip if already on disk to make
    # re-runs cheap when only the model-dependent outputs change.
    _skip_or_run(
        SUPP_DIR / "figS1_spatial_features.png",
        "Fig. S1",
        lambda: gen_fig_s1_spatial_features(config),
    )
    _skip_or_run(
        SUPP_DIR / "figS2_methods_workflow.png",
        "Fig. S2",
        gen_fig_s2_methods_workflow,
    )
    _skip_or_run(
        SUPP_DIR / "figS3_heatwave_analysis.png",
        "Fig. S3",
        gen_fig_s3_heatwave,
    )
    _skip_or_run(
        SUPP_DIR / "figS4_pearson_correlation.png",
        "Fig. S4",
        lambda: gen_fig_s4_pearson(df, config["band_names"]),
    )

    # Figures + tables that depend on the pickled models. We always
    # regenerate these because they share a single round of predictions.
    models = {
        "XGBoost":       joblib.load(MODELS_DIR / "xgb_model.pkl"),
        "Random Forest": joblib.load(MODELS_DIR / "rf_model.pkl"),
        "SVM":           joblib.load(MODELS_DIR / "svm_model.pkl"),
    }
    # The eight predictor columns are everything in band_names except the last
    # two (LST and hotspot). This MUST match notebook 03's slice exactly so the
    # column ordering fed to model.predict() matches what the models were
    # trained on.
    feature_cols = config["band_names"][:-2]
    X = df[feature_cols].values
    y = df["hotspot"].values
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42
    )

    # Predict once per model (RF is the slow one — ~5 minutes on 184k pixels
    # with the 1.28 GB pickled estimator).
    print("Predicting on test split (RF is the slow one)...")
    y_preds = {}
    for name, model in models.items():
        print(f"  {name}...")
        y_preds[name] = model.predict(X_test)

    gen_table_s1_hyperparameters(models)
    metrics_df = gen_table_s2_test_metrics(y_test, y_preds)

    sanity_check_metrics(metrics_df)

    print()
    print(f"Done. Supplementary outputs at {SUPP_DIR.relative_to(PROJECT_ROOT)}.")


if __name__ == "__main__":
    main()
