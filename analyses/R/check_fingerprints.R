source("R/gccm_config.R")

dirs <- list(
  "main_E3_tau1 (publication run)" = "outputs/gccm/main_E3_tau1"
)

for (nm in names(dirs)) {
  d <- dirs[[nm]]
  cat(sprintf("\n=== %s ===\n", nm))

  # Read run metadata
  meta_path <- file.path(d, "run_metadata.yaml")
  if (!file.exists(meta_path)) {
    cat("  No metadata found\n")
    next
  }
  meta <- readLines(meta_path)
  cat(sprintf("  %s\n", trimws(grep("tau:", meta, value = TRUE)[1])))
  cat(sprintf("  %s\n", trimws(grep("fixed_E:", meta, value = TRUE)[1])))

  # Read one checkpoint and extract fingerprint
  ck_dir <- file.path(d, "checkpoints")
  fs <- list.files(ck_dir, pattern = "gccm_", full.names = TRUE)
  if (length(fs) == 0) {
    cat("  No checkpoints\n")
    next
  }

  saved <- readRDS(fs[1])
  cached_fp <- NULL
  if (is.list(saved) && "fingerprint" %in% names(saved)) {
    cached_fp <- saved$fingerprint
    cat(sprintf("  Cached FP:  %s\n", cached_fp))
  } else {
    cat("  Old format (no fingerprint) -- will RERUN\n")
    next
  }

  # What fingerprint would the current code generate?
  tau_line <- grep("tau:", meta, value = TRUE)[1]
  tau_val <- as.integer(regmatches(tau_line, regexpr("[0-9]+", tau_line)))

  e_line <- grep("fixed_E:", meta, value = TRUE)[1]
  if (grepl("[0-9]", e_line)) {
    fixed_e <- as.integer(regmatches(e_line, regexpr("[0-9]+", e_line)))
  } else {
    fixed_e <- NULL
  }

  new_fp <- make_fingerprint(ALL_PREDICTORS, tau_val, detrend = TRUE,
                             fixed_E = fixed_e)
  cat(sprintf("  New FP:     %s\n", new_fp))
  cat(sprintf("  Match: %s\n", identical(cached_fp, new_fp)))
}
