# =============================================================================
# Shared GCCM Configuration
# =============================================================================
#
# Sourced by both gccm_analysis.R and gccm_tau_sensitivity.R.
# Change parameters here and both scripts stay in sync.
# =============================================================================

RASTER_PATH <- "data/processed/ouaga_aligned_stack.tif"

# Band names must match config/processing.yaml band order exactly.
BAND_NAMES <- c("NDVI", "NDBI", "BSI", "DEM", "distance_to_water",
                "distance_to_roads", "built_density", "green_density",
                "LST", "hotspot")

# All available predictors for GCCM.
# All have a physically identifiable causal direction (predictor -> LST);
# LST cannot cause any of these surface properties.
#   built_density:     ESA WorldCover 2021, 90m kernel. Pre-smoothed at 10m.
#   green_density:     ESA WorldCover 2021, 90m kernel. Pre-smoothed at 10m.
#   distance_to_water: JRC Global Surface Water / OSM, static.
#   distance_to_roads: OSM, static.
#   DEM:               Copernicus GLO-30, static. Control variable
#                      (known direction: DEM -> LST, validates GCCM method).
#   NDBI:              Sentinel-2, 2024 Mar-May median. r=0.96 with BSI.
#   BSI:               Sentinel-2, 2024 Mar-May median. r=0.96 with NDBI.
#   NDVI:              Sentinel-2, 2024 Mar-May median.
# Target: LST = Landsat 8/9, 2022-2024 Mar-May median (different sensor
# and time window from Sentinel-2 indices).
ALL_PREDICTORS <- c("built_density", "green_density", "distance_to_water",
                    "distance_to_roads", "DEM",
                    "NDBI", "BSI", "NDVI")

TARGET <- "LST"

# Aggregation factor: 5x reduces 892x991 (30m) to ~178x198 (150m)
# 150m is close to Landsat thermal band native resolution (100m).
AGG_FACTOR <- 5

# Simplex: test embedding dimensions
E_RANGE <- 2:15

# GCCM library sizes (sliding window dimensions in pixels)
# At 150m resolution, 10px = 1.5km, 120px = 18km
LIB_SIZES <- seq(10, 120, 10)

# Number of prediction points (subsampled from non-NA pixels)
N_PRED <- 2000

SEED <- 42

THREADS <- 6  # CPU threads for spEDM


# -- Fingerprint helper -------------------------------------------------------

make_fingerprint <- function(predictors, tau, detrend = TRUE, fixed_E = NULL) {
  # Deterministic string encoding all parameters that affect GCCM results.
  # Used by both the main script (checkpoint validation) and the sensitivity
  # wrapper (skip-check validation).
  #
  # Note: detrend=TRUE omits the detrend tag for backward compatibility with
  # existing checkpoints (all created before --no-detrend was added).
  base <- paste(AGG_FACTOR, paste(E_RANGE, collapse = ","),
                paste(LIB_SIZES, collapse = ","), N_PRED, SEED, tau,
                paste(sort(predictors), collapse = ","),
                sep = "|")
  if (!detrend) base <- paste0(base, "|raw")
  if (!is.null(fixed_E)) base <- paste0(base, "|fixedE", fixed_E)
  base
}
