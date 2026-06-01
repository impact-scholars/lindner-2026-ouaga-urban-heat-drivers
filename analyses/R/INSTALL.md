# R Dependencies

## Requirements

- R >= 4.3

## Recommended: install via `renv` (exact reproducibility)

This project uses [`renv`](https://rstudio.github.io/renv/) to lock R package versions exactly. To install all locked packages (including `spEDM`, `terra`, `SpatialPack`, `ggplot2`, `yaml`, and their transitive dependencies) at the same versions used in the analysis:

```r
install.packages("renv")
renv::restore()
```

The first time you open R in this project directory, `.Rprofile` automatically activates `renv` and prompts you to restore the library if it isn't already in sync. Subsequent R sessions use the project-private library at `renv/library/`.

## Alternative: manual install

If you prefer to install the five top-level dependencies into your system R library (transitive dependencies will be installed at whatever version CRAN currently provides — not exactly the versions used in the analysis):

```r
install.packages(c("spEDM", "terra", "SpatialPack", "ggplot2", "yaml"))
```

Tested with: spEDM 1.7, terra 1.8.54, SpatialPack 0.4.1, ggplot2 3.5.2, yaml 2.3.7.

## Usage

Run all R scripts from the repository root:

```bash
cd ouaga-urban-heat-drivers
Rscript R/gccm_analysis.R --fixed-E=3 --tau=1
```
