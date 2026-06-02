# =============================================================================
# Recompute GCCM Statistics from Existing Checkpoints
# =============================================================================
#
# Regenerates derived output files (results.csv, convergence.png, summary.csv)
# from existing .rds checkpoints using nominal N for p-values and CIs.
# Does NOT load rasters, run simplex, or run GCCM.
#
# Usage:
#   Rscript R/recompute_stats.R                                  # publication run (main_E3_tau1)
#   Rscript R/recompute_stats.R outputs/gccm/some_other_run      # custom directory
#
# Inputs (per output directory):
#   checkpoints/gccm_*.rds   - raw rho-vs-libsize data (read-only)
#   summary.csv              - reads existing n_eff column for supplementary values
#   run_metadata.yaml        - reads tau and detrend for plot titles
#
# Outputs (overwrites only derived files):
#   results.csv              - long-format with n_nominal + n_eff_clifford columns
#   convergence.png          - convergence plot with nominal-N CIs
#   summary.csv              - summary table with nominal-N statistics
#
# Dependencies: ggplot2, yaml (no spEDM, no terra, no SpatialPack)
# =============================================================================

library(ggplot2)
library(yaml)

source("R/gccm_config.R")

# -- Helper functions (same as gccm_analysis.R) --------------------------------

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

# -- Configuration ------------------------------------------------------------

DEFAULT_DIRS <- c(
  "outputs/gccm/main_E3_tau1"
)

args <- commandArgs(trailingOnly = TRUE)
dirs <- if (length(args) > 0) args else DEFAULT_DIRS

n_nominal <- N_PRED  # 2000 from gccm_config.R

cat(sprintf("Recomputing stats with nominal N = %d\n", n_nominal))
cat(sprintf("Directories: %s\n\n", paste(dirs, collapse = ", ")))

# -- Process each directory ----------------------------------------------------

files_written <- character()

for (run_dir in dirs) {
  cat(sprintf("=== %s ===\n", run_dir))

  # --- Validate inputs ---
  meta_path <- file.path(run_dir, "run_metadata.yaml")
  if (!file.exists(meta_path)) {
    cat("  SKIP: no run_metadata.yaml\n\n")
    next
  }

  old_summary_path <- file.path(run_dir, "summary.csv")
  if (!file.exists(old_summary_path)) {
    cat("  SKIP: no summary.csv\n\n")
    next
  }

  checkpoint_dir <- file.path(run_dir, "checkpoints")
  rds_files <- list.files(checkpoint_dir, pattern = "^gccm_.*\\.rds$",
                          full.names = TRUE)
  if (length(rds_files) == 0) {
    cat("  SKIP: no checkpoints\n\n")
    next
  }

  # --- Read metadata for plot title ---
  meta <- read_yaml(meta_path)
  tau_val <- meta$params$tau
  detrend_val <- isTRUE(meta$params$detrend)
  detrend_label <- if (detrend_val) "detrended" else "raw"

  # --- Read old summary.csv for n_eff (Clifford/Dutilleul) and group ---
  old_summary <- read.csv(old_summary_path, stringsAsFactors = FALSE)
  n_eff_lookup <- setNames(old_summary$n_eff, old_summary$predictor)
  group_lookup <- setNames(old_summary$group, old_summary$predictor)

  # --- Load checkpoints ---
  all_results <- list()
  for (rds_path in rds_files) {
    pred_name <- sub("^gccm_(.*)\\.rds$", "\\1", basename(rds_path))
    saved <- readRDS(rds_path)
    if (is.data.frame(saved)) {
      all_results[[pred_name]] <- saved
    } else {
      all_results[[pred_name]] <- saved$data
    }
  }

  # Use ALL_PREDICTORS order for consistency
  completed_preds <- intersect(ALL_PREDICTORS, names(all_results))
  cat(sprintf("  Loaded %d checkpoints: %s\n",
              length(completed_preds), paste(completed_preds, collapse = ", ")))

  # --- Step 3: Build long-format results with CIs ---
  plot_data <- data.frame()

  for (pred in completed_preds) {
    res_df <- all_results[[pred]]
    n_eff_cliff <- if (pred %in% names(n_eff_lookup)) n_eff_lookup[[pred]] else NA

    for (xmap_col in c("y_xmap_x_mean", "x_xmap_y_mean")) {
      dir_label <- if (xmap_col == "y_xmap_x_mean") {
        paste0(pred, "->", TARGET)
      } else {
        paste0(TARGET, "->", pred)
      }

      rho_vals <- res_df[[xmap_col]]
      ci <- fisher_z_ci(rho_vals, n_nominal)
      p_vals <- pearson_significance(rho_vals, n_nominal)

      plot_data <- rbind(plot_data, data.frame(
        predictor = pred,
        libsize = res_df$libsizes,
        direction = dir_label,
        rho = rho_vals,
        ci_lower = ci$ci_lower,
        ci_upper = ci$ci_upper,
        p_value = p_vals,
        n_nominal = n_nominal,
        n_eff_clifford = n_eff_cliff
      ))
    }
  }

  plot_data$is_pred_to_lst <- grepl(paste0("->", TARGET, "$"), plot_data$direction)

  results_path <- file.path(run_dir, "results.csv")
  write.csv(plot_data, results_path, row.names = FALSE)
  cat(sprintf("  Wrote: %s\n", results_path))
  files_written <- c(files_written, results_path)

  # --- Step 4: Convergence plot ---
  p <- ggplot(plot_data, aes(x = libsize, y = rho,
                             colour = is_pred_to_lst,
                             fill = is_pred_to_lst,
                             linetype = is_pred_to_lst,
                             group = direction)) +
    geom_ribbon(aes(ymin = ci_lower, ymax = ci_upper),
                alpha = 0.15, colour = NA) +
    geom_line(linewidth = 0.8) +
    geom_point(size = 1.5) +
    facet_wrap(~ predictor, ncol = min(4, length(completed_preds)),
               scales = "free_y") +
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
                         detrend_label, tau_val)) +
    theme_minimal(base_size = 11) +
    theme(
      strip.text = element_text(face = "bold"),
      legend.position = "bottom"
    )

  plot_path <- file.path(run_dir, "convergence.png")
  ggsave(plot_path, p, width = 16, height = 8, dpi = 300)
  cat(sprintf("  Wrote: %s\n", plot_path))
  files_written <- c(files_written, plot_path)

  # --- Step 5: Summary table ---
  summary_rows <- list()

  for (pred in completed_preds) {
    res_df <- all_results[[pred]]

    rho_fwd <- res_df$y_xmap_x_mean
    rho_rev <- res_df$x_xmap_y_mean

    rho_fwd_final <- tail(rho_fwd, 1)
    rho_rev_final <- tail(rho_rev, 1)

    # Significance and CIs (nominal N)
    p_fwd <- pearson_significance(rho_fwd_final, n_nominal)
    p_rev <- pearson_significance(rho_rev_final, n_nominal)
    ci_fwd <- fisher_z_ci(rho_fwd_final, n_nominal)
    ci_rev <- fisher_z_ci(rho_rev_final, n_nominal)

    # Convergence: Kendall's tau of rho vs library size
    kt_fwd <- cor.test(res_df$libsizes, rho_fwd, method = "kendall")
    kt_rev <- cor.test(res_df$libsizes, rho_rev, method = "kendall")

    # Direction determination via CI non-overlap
    fwd_converges <- kt_fwd$estimate > 0 && kt_fwd$p.value < 0.05
    rev_converges <- kt_rev$estimate > 0 && kt_rev$p.value < 0.05
    fwd_sig <- p_fwd < 0.05
    rev_sig <- p_rev < 0.05

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

    n_eff_cliff <- if (pred %in% names(n_eff_lookup)) n_eff_lookup[[pred]] else NA
    group_val <- if (pred %in% names(group_lookup)) group_lookup[[pred]] else "causal"

    summary_rows[[pred]] <- data.frame(
      predictor = pred,
      group = group_val,
      n_nominal = n_nominal,
      n_eff_clifford = n_eff_cliff,
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

  summary_df <- do.call(rbind, summary_rows)
  summary_path <- file.path(run_dir, "summary.csv")
  write.csv(summary_df, summary_path, row.names = FALSE)
  cat(sprintf("  Wrote: %s\n\n", summary_path))
  files_written <- c(files_written, summary_path)
}

# -- Summary -------------------------------------------------------------------

cat(sprintf("=== Done: %d files written ===\n", length(files_written)))
for (f in files_written) cat(sprintf("  %s\n", f))
