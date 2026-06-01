# Notebooks

## Canonical analysis pipeline

Run these in order to reproduce the publication results:

- `01_processing_pipeline.ipynb` — Google Earth Engine acquisition, preprocessing, and aligned raster stack export
- `02_hotspot_detection.ipynb` — LST hotspot identification (binary classification target)
- `03_models.ipynb` — XGBoost / Random Forest / SVM training, SHAP, susceptibility maps
- `04_causal_analysis.ipynb` — GCCM convergence and asymmetry figures

## Companion analyses

- `02_eda.ipynb` — exploratory data analysis on the processed stack
- `Heatwave/` — heatwave context: ERA5 daily temperature retrieval and 2024 Ouagadougou case study
- `reference/GEE_setup.ipynb` — first-time Google Earth Engine setup walkthrough

## Methodology exploration (not required to reproduce the publication)

These notebooks document earlier methodology exploration and the reasoning behind choices in `src/pipeline.py`. They are kept on the public repo for reviewers and collaborators who want to see how decisions were made, but are excluded from the Zenodo publication snapshot via `.gitattributes` `export-ignore`.

- `00_quick_start.ipynb` — minimal example of loading the processed raster stack
- `DEM/download_preprocess_DEM.ipynb` — early DEM acquisition and preprocessing
- `Distance_measures/road_water_distance_measures.ipynb` — distance-to-roads and distance-to-water method validation (`fastDistanceTransform` comparison)
- `Hotspots/hotspots_detection.ipynb` — early hotspot detection prototype
- `NDVI_NDBI_BSI/NDVI_NDBI_BSI_Sentinel2_Ouagadougou.ipynb` — early spectral indices computation in Python
- `download_individual_bands.ipynb` — early per-band GEE acquisition
- `models.ipynb` — replication of Hoang et al. 2025 (predecessor to `03_models.ipynb`)
