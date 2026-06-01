#!/usr/bin/env bash
# Regenerate every panel-level PNG used in the publication.
#
# Reproducer script for reviewers: assumes the Zenodo bundle has been
# downloaded (data/processed/ouaga_aligned_stack.tif and the unzipped
# models/{xgb,rf,svm}_model.pkl pickles) and that the Python + R
# environments are installed.
#
# Outputs:
#   figures/pub/ouaga_median_lst_2022-2024.png   (LST hotspot map)
#   figures/pub/shap_*.png                       (SHAP feature importance)
#   figures/pub/susceptibility_maps.png          (model susceptibility maps)
#   figures/pub/gccm_convergence_tau1.png        (GCCM convergence)
#   figures/pub/gccm_asymmetry_tau1.png          (GCCM asymmetry)
#   figures/pub/supplementary/figS1-S4*.png      (supplementary figures)
#   figures/pub/supplementary/{hyperparameters.json,test_metrics.csv}
#
# The composite Figure 1 in the publication is assembled externally
# (PowerPoint / Keynote / Affinity) from the panel PNGs above; that
# composition step is manual and not part of this script.
#
# Usage:
#   bash scripts/regenerate_panels.sh

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Throw-away directory for executed notebook copies so we don't dirty
# the tracked .ipynb files with new cell outputs.
NB_OUT_DIR="$(mktemp -d -t ouaga-nbexec-XXXXXX)"

# Empty Jupyter config dir so nbconvert ignores any user-level config
# that may reference unavailable preprocessors / templates. Reviewers
# with custom Jupyter setups will not have their environments interfere.
JUPYTER_CONFIG_DIR="$(mktemp -d -t ouaga-jupyterconf-XXXXXX)"
export JUPYTER_CONFIG_DIR
trap 'rm -rf "$NB_OUT_DIR" "$JUPYTER_CONFIG_DIR"' EXIT

echo "[1/5] LST hotspot map (notebook 02)..."
jupyter nbconvert --to notebook --execute notebooks/02_hotspot_detection.ipynb \
    --output-dir "$NB_OUT_DIR" --output 02_hotspot_detection.ipynb

echo "[2/5] ML models, SHAP, susceptibility maps (notebook 03)..."
jupyter nbconvert --to notebook --execute notebooks/03_models.ipynb \
    --output-dir "$NB_OUT_DIR" --output 03_models.ipynb

echo "[3/5] GCCM analysis (R, ~10 min on a laptop)..."
Rscript R/gccm_analysis.R --fixed-E=3 --tau=1

echo "[4/5] GCCM convergence + asymmetry pub figures..."
python scripts/make_gccm_convergence_pub.py
python scripts/make_gccm_asymmetry_pub.py

echo "[5/5] Supplementary figures S1-S4 + tables..."
python scripts/generate_supplementary_figures.py

echo ""
echo "Done. All panels regenerated in figures/pub/ and figures/pub/supplementary/."
