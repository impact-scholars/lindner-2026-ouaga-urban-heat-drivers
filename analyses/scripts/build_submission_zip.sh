#!/usr/bin/env bash
# Build a self-contained submission zip.
#
# Combines git-tracked files (via git archive) with the data files needed
# to reproduce all figures without re-running the GEE pipeline.
#
# Usage:
#   bash scripts/build_submission_zip.sh
#
# Output:
#   submission.zip in the repository root

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

OUT="submission.zip"

# `zip -u` returns exit code 12 ("nothing to do") when every listed file is
# already up-to-date in the archive. Under `set -e` that aborts the script,
# which silently truncated the bundle in past runs. This wrapper treats
# exit-12 as success while still propagating real failures.
add_to_zip() {
    zip -u "$OUT" "$@" || [ $? -eq 12 ]
}

echo "Building $OUT ..."

# Step 1: git archive (respects .gitattributes export-ignore)
git archive -o "$OUT" HEAD

# Step 2: Add the processed raster stack (data/ is gitignored, so the raster
# is not in the git archive output)
add_to_zip data/processed/ouaga_aligned_stack.tif

# Step 3: Add GCCM results (CSVs only — notebooks regenerate the PNGs).
# These are tracked via git, so they are already in the archive; the
# explicit zip -u is a safety net for the case where they're somehow not.
add_to_zip \
    outputs/gccm/main_E3_tau1/results.csv \
    outputs/gccm/main_E3_tau1/summary.csv

echo ""
echo "Done. Contents:"
unzip -l "$OUT" | tail -3
echo ""
echo "Total size: $(du -h "$OUT" | cut -f1)"
