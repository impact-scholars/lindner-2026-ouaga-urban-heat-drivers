# =============================================================================
# GCCM Analysis: Geographical Convergent Cross Mapping
# =============================================================================
#
# Tests causal relationships between urban land surface predictors and LST
# in Ouagadougou using the spEDM package (Lyu W., 2026; Gao et al., 2023).
#
# Usage:
#   Rscript R/gccm_analysis.R --fixed-E=3 --tau=1    # publication run -> outputs/gccm/main_E3_tau1/
#   Rscript R/gccm_analysis.R --outdir=custom/path   # write to a custom directory
#   Rscript R/gccm_analysis.R --tau=5 --preds=DEM,BSI --outdir=outputs/gccm/sensitivity/tau/tau5
#   Rscript R/gccm_analysis.R --force                # override fingerprint check
#
# The default --outdir is outputs/gccm/main_E3_tau1/ (the publication run).
# If you intend to explore alternative parameters, pass --outdir explicitly to
# avoid overwriting the canonical run.
#
# The script is resumable: intermediate results are checkpointed to
# {outdir}/checkpoints/ as .rds files. Re-running skips completed steps.
# Checkpoints include a parameter fingerprint — if you change parameters,
# stale checkpoints are detected and recomputed automatically.
#
# Outputs (in outdir, default outputs/gccm/main_E3_tau1/):
#   summary.csv              - summary table with convergence tests
#   results.csv              - convergence results with Fisher-z CIs
#   convergence.png          - convergence plot grid with CI ribbons
#   simplex_selection.csv    - optimal E per variable
#   simplex_full.csv         - full rho-vs-E curves for robustness
#   run_metadata.yaml        - provenance: params, versions, git hash
#   checkpoints/             - .rds files for resuming interrupted runs
#
# References:
#   - Gao, B. et al. (2023). Causal inference from cross-sectional earth system
#   data with geographical convergent cross mapping. Nature Communications, 14.
#   - Lyu W (2026). spEDM: Spatial Empirical Dynamic Modeling.
#   doi:10.32614/CRAN.package.spEDM, R package.
# =============================================================================

library(spEDM)
library(terra)
library(ggplot2)
library(SpatialPack)
library(yaml)

# -- CLI arguments -------------------------------------------------------------
# Optional: Rscript R/gccm_analysis.R --tau=5 --preds=DEM,BSI --outdir=path
args <- commandArgs(trailingOnly = TRUE)
tau_arg <- grep("^--tau=", args, value = TRUE)
CLI_TAU <- if (length(tau_arg) > 0) as.integer(sub("^--tau=", "", tau_arg)) else NULL
preds_arg <- grep("^--preds=", args, value = TRUE)
CLI_PREDS <- if (length(preds_arg) > 0) {
  strsplit(sub("^--preds=", "", preds_arg), ",")[[1]]
} else NULL
outdir_arg <- grep("^--outdir=", args, value = TRUE)
CLI_OUTDIR <- if (length(outdir_arg) > 0) sub("^--outdir=", "", outdir_arg) else NULL
CLI_NO_DETREND <- "--no-detrend" %in% args
CLI_FORCE <- "--force" %in% args
fixed_e_arg <- grep("^--fixed-E=", args, value = TRUE)
CLI_FIXED_E <- if (length(fixed_e_arg) > 0) as.integer(sub("^--fixed-E=", "", fixed_e_arg)) else NULL

# -- Helper functions --------------------------------------------------------
# Ported from Gao et al. (2023) reference code (basic.r) for computing
# significance and confidence intervals on Pearson rho.

pearson_significance <- function(r, n) {
  # Two-tailed t-test for H0: rho = 0
  #
  # Parameters
  # ----------
  # r : numeric
  #     Pearson correlation coefficient.
  # n : integer
  #     Number of prediction points.
  #
  # Returns
  # -------
  # numeric
  #     Two-tailed p-value.
  r <- pmax(pmin(r, 1 - 1e-10), -1 + 1e-10)
  t_stat <- r * sqrt((n - 2) / (1 - r^2))
  2 * (1 - pt(abs(t_stat), n - 2))
}

fisher_z_ci <- function(r, n, level = 0.05) {
  # 95% confidence interval for Pearson rho via Fisher-z transform.
  #
  # Parameters
  # ----------
  # r : numeric
  #     Pearson correlation coefficient.
  # n : integer
  #     Number of prediction points.
  # level : numeric
  #     Significance level (default 0.05 for 95% CI).
  #
  # Returns
  # -------
  # data.frame
  #     Columns ci_lower, ci_upper.
  r <- pmax(pmin(r, 1 - 1e-10), -1 + 1e-10)
  z <- 0.5 * log((1 + r) / (1 - r))
  se <- 1 / sqrt(n - 3)
  q <- qnorm(1 - level / 2)
  z_upper <- z + q * se
  z_lower <- z - q * se
  r_upper <- (exp(2 * z_upper) - 1) / (exp(2 * z_upper) + 1)
  r_lower <- (exp(2 * z_lower) - 1) / (exp(2 * z_lower) + 1)
  data.frame(ci_lower = r_lower, ci_upper = r_upper)
}

# -- Configuration -----------------------------------------------------------
# Shared parameters are in R/gccm_config.R (sourced by both this script
# and gccm_tau_sensitivity.R). Change parameters there.

source("R/gccm_config.R")

PREDICTORS <- ALL_PREDICTORS

# Override via CLI: Rscript R/gccm_analysis.R --preds=DEM,BSI
if (!is.null(CLI_PREDS)) {
  invalid <- setdiff(CLI_PREDS, ALL_PREDICTORS)
  if (length(invalid) > 0) stop("Unknown predictors: ", paste(invalid, collapse = ", "))
  PREDICTORS <- CLI_PREDS
}

# Spatial lag for state-space embedding.
# tau=1 uses 150m lags. Semivariogram ranges are 5-8 km, so larger values
# may better capture the relevant spatial scale.
# Override via CLI: Rscript R/gccm_analysis.R --tau=5
TAU <- if (!is.null(CLI_TAU)) CLI_TAU else 1L

# Detrend: remove linear spatial trend before embedding (default TRUE).
# Override via CLI: Rscript R/gccm_analysis.R --no-detrend
DETREND <- !CLI_NO_DETREND

# Fixed E: use a single embedding dimension for all variables instead of
# per-variable simplex selection. Useful for sensitivity analysis.
# Override via CLI: Rscript R/gccm_analysis.R --fixed-E=3
FIXED_E <- CLI_FIXED_E

PARAM_FINGERPRINT <- make_fingerprint(PREDICTORS, TAU, DETREND, FIXED_E)

# Auto-generated label for run provenance (stored in run_metadata.yaml).
e_label <- if (!is.null(FIXED_E)) sprintf("Efixed%d", FIXED_E) else sprintf("E%d-%d", min(E_RANGE), max(E_RANGE))
RUN_LABEL <- sprintf("agg%d_tau%d_%s_%dpred",
                      AGG_FACTOR, TAU, e_label, length(PREDICTORS))

# Output directory: --outdir overrides, default is outputs/gccm/main_E3_tau1/
RUN_DIR <- if (!is.null(CLI_OUTDIR)) CLI_OUTDIR else file.path("outputs", "gccm", "main_E3_tau1")
CHECKPOINT_DIR <- file.path(RUN_DIR, "checkpoints")

# -- Pre-flight fingerprint check ----------------------------------------------
# If checkpoints already exist with a different fingerprint, the CLI arguments
# are probably wrong. Abort before writing anything to avoid silently overwriting
# metadata and triggering expensive GCCM recomputation.

existing_rds <- list.files(CHECKPOINT_DIR, pattern = "^gccm_.*\\.rds$",
                           full.names = TRUE)
if (length(existing_rds) > 0) {
  saved <- readRDS(existing_rds[1])
  if (!is.data.frame(saved) && !is.null(saved$fingerprint) &&
      saved$fingerprint != PARAM_FINGERPRINT) {
    if (!CLI_FORCE) {
      stop(sprintf(paste0(
        "\nFINGERPRINT MISMATCH — refusing to overwrite existing checkpoints.\n",
        "  Directory:  %s\n",
        "  Existing:   %s\n",
        "  Current:    %s\n\n",
        "Pass --force to override.\n"),
        RUN_DIR, saved$fingerprint, PARAM_FINGERPRINT))
    }
    cat("WARNING: --force used, proceeding despite fingerprint mismatch.\n")
  }
}

# -- Log run metadata ----------------------------------------------------------

run_metadata <- list(
  timestamp     = format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"),
  run_label     = RUN_LABEL,
  git_hash      = tryCatch(
    trimws(system("git rev-parse --short HEAD", intern = TRUE)),
    error = function(e) "unknown"
  ),
  git_dirty     = tryCatch({
    out <- system("git status --porcelain R/gccm_analysis.R", intern = TRUE)
    if (length(out) == 0) "clean" else trimws(out)
  }, error = function(e) "unknown"),
  r_version     = paste0(R.version$major, ".", R.version$minor),
  spEDM_version = as.character(packageVersion("spEDM")),
  terra_version = as.character(packageVersion("terra")),
  params = list(
    AGG_FACTOR = AGG_FACTOR,
    E_RANGE    = paste(range(E_RANGE), collapse = ":"),
    LIB_SIZES  = paste0("seq(", min(LIB_SIZES), ",", max(LIB_SIZES), ",",
                         unique(diff(LIB_SIZES)), ")"),
    N_PRED     = N_PRED,
    SEED       = SEED,
    THREADS    = THREADS,
    tau        = TAU,
    detrend    = DETREND,
    fixed_E    = if (!is.null(FIXED_E)) FIXED_E else "per-variable (simplex)",
    predictors = PREDICTORS,
    target     = TARGET
  ),
  notes = list(
    lib_pred_split = "lib includes all valid pixels (Gao protocol)",
    e_selection    = if (!is.null(FIXED_E)) sprintf("fixed E=%d for all variables", FIXED_E) else "simplex with k=E+2 filter (standard simplex protocol)",
    ci_method      = "nominal N (Gao et al. 2023); Clifford/Dutilleul N_eff stored as supplementary"
  ),
  fingerprint = PARAM_FINGERPRINT
)

dir.create(RUN_DIR, recursive = TRUE, showWarnings = FALSE)
dir.create(CHECKPOINT_DIR, recursive = TRUE, showWarnings = FALSE)
meta_path <- file.path(RUN_DIR, "run_metadata.yaml")
writeLines(as.yaml(run_metadata), meta_path)


# -- Load and prepare data ---------------------------------------------------

cat("=== GCCM Analysis ===\n\n")
cat(sprintf("Run label: %s\n", RUN_LABEL))
cat(sprintf("Output:    %s\n", RUN_DIR))
cat(sprintf("tau = %d (spatial lag ~ %dm at %dx aggregation)\n", TAU, TAU * 30 * AGG_FACTOR, AGG_FACTOR))
cat(sprintf("detrend = %s\n", if (DETREND) "TRUE" else "FALSE"))
if (!is.null(FIXED_E)) cat(sprintf("fixed E = %d (simplex skipped)\n", FIXED_E))

if (!file.exists(RASTER_PATH)) {
  stop("Raster not found: ", RASTER_PATH,
       "\nRun from project root or check the path.")
}

cat("Loading raster:", RASTER_PATH, "\n")
stack <- rast(RASTER_PATH)

# Validate band count matches config
if (nlyr(stack) != length(BAND_NAMES)) {
  stop(sprintf("Raster has %d bands but BAND_NAMES has %d. Check config/processing.yaml.",
               nlyr(stack), length(BAND_NAMES)))
}
# Band order is enforced by pipeline.py stack_layers(); must match
# config/processing.yaml band_names.
names(stack) <- BAND_NAMES

cat(sprintf("  Original: %d bands, %d x %d pixels (%.0fm)\n",
            nlyr(stack), nrow(stack), ncol(stack), res(stack)[1]))

# Aggregate to reduce computation (150m is close to Landsat TIRS native 100m)
# NOTE: Mean aggregation is applied uniformly. Two known caveats:
#   - Distance variables: mean of a 5x5 block != distance from centroid.
#     Distortion is largest near features (roads/water) and decays quickly.
#   - Density variables (built_density, green_density): already 90m neighborhood
#     means from the pipeline, so 5x aggregation produces ~450m effective means.
# These are second-order effects on rho magnitude, not on causal direction.
stack_agg <- aggregate(stack, fact = AGG_FACTOR, fun = "mean", na.rm = TRUE)

cat(sprintf("  Aggregated (x%d): %d x %d pixels (%.0fm)\n",
            AGG_FACTOR, nrow(stack_agg), ncol(stack_agg), res(stack_agg)[1]))

# Extract non-NA indices (row, col matrix)
# Use LST band as the reference for valid pixels
ref_mat <- as.matrix(stack_agg[[TARGET]], wide = TRUE)
nna_indice <- which(!is.na(ref_mat), arr.ind = TRUE)
cat(sprintf("  Valid pixels: %d / %d (%.1f%%)\n",
            nrow(nna_indice),
            nrow(ref_mat) * ncol(ref_mat),
            100 * nrow(nna_indice) / (nrow(ref_mat) * ncol(ref_mat))))

# Library = all valid pixels; prediction = random subsample.
# GCCM's sliding window and leave-one-out handle separation internally.
# This matches Gao et al. reference code where lib includes pred points.
set.seed(SEED)
pred_idx <- sample(nrow(nna_indice), size = min(N_PRED, nrow(nna_indice)),
                   replace = FALSE)
pred_indice <- nna_indice[pred_idx, ]
lib_indice <- nna_indice  # full manifold (GCCM protocol)

cat(sprintf("  Library: %d pixels, Prediction: %d pixels\n\n",
            nrow(lib_indice), nrow(pred_indice)))

# -- Step 1: Simplex E-selection ---------------------------------------------

if (!is.null(FIXED_E)) {
  # Fixed E mode: skip simplex, use the same E for all variables
  cat(sprintf("=== Step 1: Fixed E = %d (simplex skipped) ===\n\n", FIXED_E))

  all_vars <- c(PREDICTORS, TARGET)
  simplex_results <- data.frame(
    variable = all_vars,
    best_E = rep(FIXED_E, length(all_vars)),
    stringsAsFactors = FALSE
  )
  simplex_full <- data.frame()

  simplex_path <- file.path(RUN_DIR, "simplex_selection.csv")
  write.csv(simplex_results, simplex_path, row.names = FALSE)
  cat(sprintf("Saved: %s\n\n", simplex_path))

} else {
  cat("=== Step 1: Simplex E-selection ===\n\n")

  simplex_checkpoint <- file.path(CHECKPOINT_DIR, "simplex.rds")

  simplex_cached <- FALSE
  if (file.exists(simplex_checkpoint)) {
    simplex_saved <- readRDS(simplex_checkpoint)
    if (is.null(simplex_saved$fingerprint) ||
        simplex_saved$fingerprint != PARAM_FINGERPRINT) {
      cat("  WARNING: Stale simplex checkpoint (parameters changed). Recomputing.\n")
    } else {
      cat("  Loading from checkpoint...\n")
      simplex_results <- simplex_saved$results
      simplex_full <- simplex_saved$full
      simplex_cached <- TRUE
      for (i in seq_len(nrow(simplex_results))) {
        cat(sprintf("  simplex(%s): E = %d (cached)\n",
                    simplex_results$variable[i], simplex_results$best_E[i]))
      }
    }
  }

  if (!simplex_cached) {
    # Select optimal E for each variable (including target)
    all_vars <- c(PREDICTORS, TARGET)
    simplex_results <- data.frame(
      variable = character(),
      best_E = integer(),
      stringsAsFactors = FALSE
    )
    simplex_full <- data.frame()

    for (var in all_vars) {
      cat(sprintf("  simplex(%s): ", var))

      set.seed(SEED)
      result <- simplex(stack_agg, var, var,
                        E = E_RANGE, tau = TAU,
                        lib = lib_indice, pred = pred_indice,
                        threads = THREADS,
                        detrend = DETREND)

      # Filter to the natural k = E + 2 (standard simplex protocol) so that
      # E selection is not conflated with k selection
      natural_rows <- result$xmap[result$xmap$k == result$xmap$E + 2, ]
      best_row <- which.max(natural_rows$rho)
      best_E <- natural_rows$E[best_row]
      best_rho <- natural_rows$rho[best_row]

      cat(sprintf("E = %d (rho = %.3f)\n", best_E, best_rho))

      simplex_results <- rbind(simplex_results,
                               data.frame(variable = var, best_E = best_E))

      # Store full rho-vs-E curve for robustness assessment
      simplex_full <- rbind(simplex_full,
                            data.frame(variable = var, result$xmap))
    }

    # Checkpoint with parameter fingerprint
    saveRDS(list(results = simplex_results, full = simplex_full,
                 fingerprint = PARAM_FINGERPRINT),
            simplex_checkpoint)
    cat("  Checkpointed simplex results.\n")
  }

  # Save CSVs (always, even on resume -- cheap and keeps CSVs current)
  simplex_path <- file.path(RUN_DIR, "simplex_selection.csv")
  write.csv(simplex_results, simplex_path, row.names = FALSE)
  cat(sprintf("\nSaved: %s\n", simplex_path))

  simplex_full_path <- file.path(RUN_DIR, "simplex_full.csv")
  write.csv(simplex_full, simplex_full_path, row.names = FALSE)
  cat(sprintf("Saved: %s\n\n", simplex_full_path))
}

# -- Step 2: GCCM for each predictor vs LST ---------------------------------
# spEDM column naming convention (Sugihara CCM convention):
#   gccm(cause=X, effect=Y) returns:
#     y_xmap_x_mean: Y cross-maps X -> high rho means X causes Y (forward)
#     x_xmap_y_mean: X cross-maps Y -> high rho means Y causes X (reverse)
#   So for gccm(cause=pred, effect=LST):
#     y_xmap_x_mean = pred -> LST (pred causes LST)
#     x_xmap_y_mean = LST -> pred (LST causes pred)

cat("=== Step 2: GCCM analysis ===\n\n")

# Library sizes as matrix: col 1 = row window size, col 2 = col window size
libsizes_mat <- matrix(rep(LIB_SIZES, 2), ncol = 2)

# Load any previously checkpointed results (with fingerprint validation)
all_results <- list()
for (pred in PREDICTORS) {
  rds_path <- file.path(CHECKPOINT_DIR, paste0("gccm_", pred, ".rds"))
  if (file.exists(rds_path)) {
    saved <- readRDS(rds_path)
    if (is.data.frame(saved)) {
      # Old format (raw data.frame, no fingerprint) -- treat as stale
      cat(sprintf("  WARNING: %s has old checkpoint format. Recomputing.\n", pred))
    } else if (is.null(saved$fingerprint) ||
               saved$fingerprint != PARAM_FINGERPRINT) {
      cat(sprintf("  WARNING: %s checkpoint stale (params changed). Recomputing.\n",
                  pred))
    } else {
      all_results[[pred]] <- saved$data
    }
  }
}

if (length(all_results) > 0) {
  cat(sprintf("  Loaded %d cached predictor(s): %s\n\n",
              length(all_results), paste(names(all_results), collapse = ", ")))
}

for (pred in PREDICTORS) {
  rds_path <- file.path(CHECKPOINT_DIR, paste0("gccm_", pred, ".rds"))

  if (pred %in% names(all_results)) {
    res_df <- all_results[[pred]]
    cat(sprintf("--- %s <-> %s --- (cached, rho = %.3f / %.3f)\n",
                pred, TARGET,
                tail(res_df$y_xmap_x_mean, 1),
                tail(res_df$x_xmap_y_mean, 1)))
    next
  }

  cat(sprintf("--- %s <-> %s ---\n", pred, TARGET))

  # Look up optimal E for this pair
  E_pred <- simplex_results$best_E[simplex_results$variable == pred]
  E_target <- simplex_results$best_E[simplex_results$variable == TARGET]

  cat(sprintf("  E = c(%d, %d)\n", E_pred, E_target))

  # Run bidirectional GCCM
  set.seed(SEED)
  gccm_res <- gccm(
    data         = stack_agg,
    cause        = pred,
    effect       = TARGET,
    libsizes     = libsizes_mat,
    E            = c(E_pred, E_target),
    tau          = TAU,
    lib          = lib_indice,
    pred         = pred_indice,
    threads      = THREADS,
    detrend      = DETREND,
    bidirectional = TRUE,
    progressbar  = TRUE
  )

  # Extract the results dataframe
  res_df <- gccm_res$xmap
  res_df$predictor <- pred

  cat(sprintf("  %s -> %s: rho = %.3f (final)\n",
              pred, TARGET,
              tail(res_df$y_xmap_x_mean, 1)))
  cat(sprintf("  %s -> %s: rho = %.3f (final)\n\n",
              TARGET, pred,
              tail(res_df$x_xmap_y_mean, 1)))

  # Checkpoint with parameter fingerprint
  all_results[[pred]] <- res_df
  saveRDS(list(data = res_df, fingerprint = PARAM_FINGERPRINT), rds_path)
  cat(sprintf("  Checkpointed: %s\n", rds_path))
}

n_completed <- length(all_results)
cat(sprintf("\nCompleted %d / %d predictors.\n\n", n_completed, length(PREDICTORS)))

if (n_completed == 0) {
  stop("No GCCM results available. Cannot proceed to analysis.")
}

# Steps 3-5 run on whatever predictors have completed
completed_preds <- intersect(PREDICTORS, names(all_results))
if (n_completed < length(PREDICTORS)) {
  cat(sprintf("NOTE: Partial run (%d/%d). Stats and plots use completed predictors only.\n",
              n_completed, length(PREDICTORS)))
  cat(sprintf("  Missing: %s\n",
              paste(setdiff(PREDICTORS, completed_preds), collapse = ", ")))
  cat("  Re-run script to resume remaining predictors.\n\n")
}


# -- Step 2b: Effective N via Clifford/Dutilleul (supplementary) -------------
# We use nominal N for p-values and CIs, following Gao et al. (2023).
# However, we also compute effective N via Clifford/Dutilleul correction
# (Clifford & Richardson, 1989) and store it as a supplementary column.
# This documents the degree of spatial autocorrelation in the data without
# affecting the statistical inference.
#
# When GCCM runs with detrend=TRUE, we detrend manually here using the same
# approach (OLS residuals in row/col coordinates) so that N_eff reflects
# autocorrelation in the detrended residuals, not the raw spatial trend.

cat("=== Step 2b: Effective N (Clifford/Dutilleul, supplementary) ===\n\n")

n_pred_actual <- nrow(pred_indice)
cat(sprintf("  Nominal N = %d (used for p-values and CIs following Gao et al.)\n\n",
            n_pred_actual))
pred_coords <- pred_indice  # 2-column matrix (row, col) in pixel units

# LST values at prediction points (detrend to match GCCM if applicable)
lst_mat <- as.matrix(stack_agg[[TARGET]], wide = TRUE)
lst_raw <- lst_mat[pred_indice]
lst_vals <- if (DETREND) {
  residuals(lm(lst_raw ~ pred_coords[, 1] + pred_coords[, 2]))
} else {
  lst_raw
}

n_eff_clifford <- list()

for (pred in completed_preds) {
  pred_mat <- as.matrix(stack_agg[[pred]], wide = TRUE)
  pred_raw <- pred_mat[pred_indice]

  # Match detrending to what GCCM sees
  pred_vals <- if (DETREND) {
    residuals(lm(pred_raw ~ pred_coords[, 1] + pred_coords[, 2]))
  } else {
    pred_raw
  }

  mt <- tryCatch(
    modified.ttest(pred_vals, lst_vals, pred_coords, nclass = 13),
    error = function(e) {
      cat(sprintf("  WARNING: modified.ttest failed for %s: %s\n", pred, e$message))
      cat(sprintf("  Falling back to nominal N = %d.\n", n_pred_actual))
      NULL
    }
  )

  if (!is.null(mt)) {
    # dof = N_eff - 2 for Pearson correlation
    n_eff <- max(mt$dof + 2, 4)  # floor at 4 (Fisher-z needs n >= 4)
    n_eff_clifford[[pred]] <- n_eff
    cat(sprintf("  %s: N_eff = %.0f (nominal = %d, ratio = %.3f)\n",
                pred, n_eff, n_pred_actual, n_eff / n_pred_actual))
  } else {
    n_eff_clifford[[pred]] <- n_pred_actual
  }
}

cat("\n")


# -- Step 3: Build long-format results with CIs -----------------------------

cat("=== Step 3: Build results with CIs ===\n\n")
plot_data <- data.frame()

for (pred in completed_preds) {
  res_df <- all_results[[pred]]

  # Map spEDM columns to human-readable direction labels
  # y_xmap_x_mean: pred -> LST (pred causes LST)
  # x_xmap_y_mean: LST -> pred (LST causes pred)
  for (xmap_col in c("y_xmap_x_mean", "x_xmap_y_mean")) {
    dir_label <- if (xmap_col == "y_xmap_x_mean") {
      paste0(pred, "->", TARGET)
    } else {
      paste0(TARGET, "->", pred)
    }

    rho_vals <- res_df[[xmap_col]]
    ci <- fisher_z_ci(rho_vals, n_pred_actual)
    p_vals <- pearson_significance(rho_vals, n_pred_actual)

    plot_data <- rbind(plot_data, data.frame(
      predictor = pred,
      libsize = res_df$libsizes,
      direction = dir_label,
      rho = rho_vals,
      ci_lower = ci$ci_lower,
      ci_upper = ci$ci_upper,
      p_value = p_vals,
      n_nominal = n_pred_actual,
      n_eff_clifford = n_eff_clifford[[pred]]
    ))
  }
}

# Flag direction for plotting
plot_data$is_pred_to_lst <- grepl(paste0("->", TARGET, "$"), plot_data$direction)

# Save long-format results
results_path <- file.path(RUN_DIR, "results.csv")
write.csv(plot_data, results_path, row.names = FALSE)
cat(sprintf("Saved: %s\n\n", results_path))


# -- Step 4: Convergence plots with CI ribbons -------------------------------

cat("=== Step 4: Convergence plots ===\n\n")

p <- ggplot(plot_data, aes(x = libsize, y = rho,
                           colour = is_pred_to_lst,
                           fill = is_pred_to_lst,
                           linetype = is_pred_to_lst,
                           group = direction)) +
  geom_ribbon(aes(ymin = ci_lower, ymax = ci_upper),
              alpha = 0.15, colour = NA) +
  geom_line(linewidth = 0.8) +
  geom_point(size = 1.5) +
  facet_wrap(~ predictor, ncol = min(4, length(completed_preds)), scales = "free_y") +
  scale_colour_manual(values = c("TRUE" = "steelblue", "FALSE" = "coral"),
                      labels = c("TRUE" = "pred -> LST  (LST xmap pred)",
                                 "FALSE" = "LST -> pred  (pred xmap LST)"),
                      name = "Causal direction") +
  scale_fill_manual(values = c("TRUE" = "steelblue", "FALSE" = "coral"),
                    labels = c("TRUE" = "pred -> LST  (LST xmap pred)",
                               "FALSE" = "LST -> pred  (pred xmap LST)"),
                    name = "Causal direction") +
  scale_linetype_manual(values = c("TRUE" = "solid", "FALSE" = "dashed"),
                        labels = c("TRUE" = "pred -> LST  (LST xmap pred)",
                                   "FALSE" = "LST -> pred  (pred xmap LST)"),
                        name = "Causal direction") +
  geom_hline(yintercept = 0, colour = "gray50", linewidth = 0.3) +
  labs(x = "Library size (pixels)",
       y = expression("Cross-mapping skill (" * rho * ")"),
       title = sprintf("GCCM Convergence: Predictor <-> LST (spEDM, %s, tau=%d)",
                       if (DETREND) "detrended" else "raw", TAU)) +
  theme_minimal(base_size = 11) +
  theme(
    strip.text = element_text(face = "bold"),
    legend.position = "bottom"
  )

plot_path <- file.path(RUN_DIR, "convergence.png")
ggsave(plot_path, p, width = 16, height = 8, dpi = 300)
cat(sprintf("Saved: %s\n\n", plot_path))


# -- Step 5: Statistical summary ---------------------------------------------
# Causal direction is determined by three criteria (Gao et al., 2023):
#   1. Convergence: Kendall's tau > 0 (rho increases with library size)
#   2. Significance: p < 0.05 at the largest library size
#   3. Direction: 95% CIs for the two directions are non-overlapping

cat("=== GCCM Summary ===\n\n")
cat(sprintf("  Using nominal N = %d for p-values and CIs (Gao et al. 2023)\n\n",
            n_pred_actual))
cat(sprintf("%-22s %5s %8s %8s [%14s] %8s %8s [%14s] %5s %5s %s\n",
            "Predictor", "N",
            "pred>LST", "p_fwd", "CI_fwd",
            "LST>pred", "p_rev", "CI_rev",
            "K_fwd", "K_rev", "Direction"))
cat(strrep("-", 120), "\n")

summary_rows <- list()

for (pred in completed_preds) {
  res_df <- all_results[[pred]]

  # y_xmap_x_mean: pred -> LST (forward), x_xmap_y_mean: LST -> pred (reverse)
  rho_fwd <- res_df$y_xmap_x_mean
  rho_rev <- res_df$x_xmap_y_mean

  # Final rho at largest library size
  rho_fwd_final <- tail(rho_fwd, 1)
  rho_rev_final <- tail(rho_rev, 1)

  # Significance and CIs at the largest library size (nominal N, Gao approach)
  p_fwd <- pearson_significance(rho_fwd_final, n_pred_actual)
  p_rev <- pearson_significance(rho_rev_final, n_pred_actual)
  ci_fwd <- fisher_z_ci(rho_fwd_final, n_pred_actual)
  ci_rev <- fisher_z_ci(rho_rev_final, n_pred_actual)

  # Convergence test: Kendall's tau of rho vs library size
  kt_fwd <- cor.test(res_df$libsizes, rho_fwd, method = "kendall")
  kt_rev <- cor.test(res_df$libsizes, rho_rev, method = "kendall")

  # Direction determination via CI non-overlap
  fwd_converges <- kt_fwd$estimate > 0 && kt_fwd$p.value < 0.05
  rev_converges <- kt_rev$estimate > 0 && kt_rev$p.value < 0.05
  fwd_sig <- p_fwd < 0.05
  rev_sig <- p_rev < 0.05

  # CIs non-overlapping = one direction's lower bound exceeds the other's upper
  fwd_stronger <- ci_fwd$ci_lower > ci_rev$ci_upper
  rev_stronger <- ci_rev$ci_lower > ci_fwd$ci_upper

  if (fwd_converges && fwd_sig && fwd_stronger) {
    dir_label <- paste(pred, "-> LST")
  } else if (rev_converges && rev_sig && rev_stronger) {
    dir_label <- paste("LST ->", pred)
  } else if (fwd_converges && rev_converges && fwd_sig && rev_sig) {
    dir_label <- "both significant"
  } else if (fwd_converges && fwd_sig) {
    dir_label <- paste(pred, "-> LST (weak)")
  } else if (rev_converges && rev_sig) {
    dir_label <- paste("LST ->", pred, "(weak)")
  } else {
    dir_label <- "not significant"
  }

  cat(sprintf("%-22s %5d %+8.3f %8.4f [%+.3f, %+.3f] %+8.3f %8.4f [%+.3f, %+.3f] %+5.2f %+5.2f %s\n",
              pred, n_pred_actual,
              rho_fwd_final, p_fwd, ci_fwd$ci_lower, ci_fwd$ci_upper,
              rho_rev_final, p_rev, ci_rev$ci_lower, ci_rev$ci_upper,
              kt_fwd$estimate, kt_rev$estimate,
              dir_label))

  summary_rows[[pred]] <- data.frame(
    predictor = pred,
    group = "causal",
    n_nominal = n_pred_actual,
    n_eff_clifford = n_eff_clifford[[pred]],
    rho_pred_to_LST = rho_fwd_final,
    rho_LST_to_pred = rho_rev_final,
    p_fwd = p_fwd, p_rev = p_rev,
    ci_fwd_lower = ci_fwd$ci_lower, ci_fwd_upper = ci_fwd$ci_upper,
    ci_rev_lower = ci_rev$ci_lower, ci_rev_upper = ci_rev$ci_upper,
    kendall_fwd = kt_fwd$estimate, kendall_fwd_p = kt_fwd$p.value,
    kendall_rev = kt_rev$estimate, kendall_rev_p = kt_rev$p.value,
    direction = dir_label
  )
}

# Save summary table
summary_df <- do.call(rbind, summary_rows)
summary_path <- file.path(RUN_DIR, "summary.csv")
write.csv(summary_df, summary_path, row.names = FALSE)
cat(sprintf("\nSaved: %s\n", summary_path))

cat("\n=== Done ===\n")
