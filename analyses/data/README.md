# Data Directory

## Structure

```
data/
  raw/          # Input data — treat as read-only
  processed/    # Pipeline outputs — reproducible from raw + code
```

## Quick Start

1. Clone the repo (you'll get the AOI shapefile automatically)
2. Set up a [Google Earth Engine](https://earthengine.google.com/) account and authenticate
3. Upload the AOI shapefile and cleaned OSM roads to your GEE project as assets (see below)
4. Update `config/processing.yaml` with your GEE project ID and asset paths
5. Run `notebooks/01_processing_pipeline.ipynb` to compute and download the raster stack
6. Load the data in any analysis notebook with:
   ```python
   from src.data import load_dataset
   df, config = load_dataset("../config/processing.yaml")
   ```
   See `notebooks/00_quick_start.ipynb` for a walkthrough.

## GEE Remote Datasets

The processing pipeline (`src/pipeline.py`) fetches these datasets directly from Google Earth
Engine. They do not need to be downloaded locally — you just need a GEE account.

| Dataset | GEE Collection ID | Used for | License |
|---|---|---|---|
| Landsat 8 C02 T1_L2 | `LANDSAT/LC08/C02/T1_L2` | LST | USGS, public domain |
| Landsat 9 C02 T1_L2 | `LANDSAT/LC09/C02/T1_L2` | LST | USGS, public domain |
| Sentinel-2 SR Harmonized | `COPERNICUS/S2_SR_HARMONIZED` | NDVI, NDBI, BSI | Copernicus, free and open |
| JRC Global Surface Water v1.4 | `JRC/GSW1_4/GlobalSurfaceWater` | Distance to water | Pekel et al. (2016), free |
| Copernicus DEM GLO-30 | `COPERNICUS/DEM/GLO30` | Elevation | Copernicus, free and open |
| ESA WorldCover 2021 | `ESA/WorldCover/v200/2021` | Built/green density | CC-BY 4.0 |

Temporal and processing parameters (study years, cloud thresholds, etc.) are defined in
`config/processing.yaml`.

## GEE Assets (User-Uploaded)

The pipeline also depends on two assets that must be uploaded to your own GEE project:

| Asset | Source | Description |
|---|---|---|
| AOI boundary | `data/raw/Shapefile Ouaga/Ouaga.shp` | Ouagadougou city boundary. Upload to GEE and set `ee_boundary_asset` in config. The pipeline falls back to the local shapefile if the asset is unavailable. |
| OSM roads | Cleaned from `data/raw/osm-roads/` | Ouagadougou road network. Must be cleaned (see below) then uploaded to GEE. Set `roads_asset` in config. There is no local fallback for this one. |

After uploading, update these fields in `config/processing.yaml`:
- `ee_project` — your GEE project ID
- `ee_boundary_asset` — your boundary asset path
- `roads_asset` — your roads asset path

## Raw Datasets

### Shapefile Ouaga/ (tracked in git)
- **What:** Ouagadougou city boundary polygon
- **Source:** Derived from [OCHA-HDX Burkina Faso admin boundaries](https://data.humdata.org/dataset/cod-ab-bfa) by filtering `adm3_name` for Ouagadougou.
- **Used by:** Nearly all notebooks (defines the Area of Interest)
- **Included in repo:** Yes — small enough to track directly

### osm-roads/
- **What:** OpenStreetMap road network extract for the Ouagadougou area
- **Source:** [Protomaps OSM Exports](https://app.protomaps.com/downloads/osm) — bounding box: `-1.795, 12.14, -1.265, 12.588`
- **License:** ODbL (Open Database License) — requires attribution to OpenStreetMap contributors
- **Used by:** `notebooks/Distance_measures/road_water_distance_measures.ipynb` (cleaning), then uploaded to GEE for the main pipeline
- **Setup:**
  1. Download the shapefile export for the bounding box above and extract into `data/raw/osm-roads/`
  2. Run the cleaning step in `notebooks/Distance_measures/road_water_distance_measures.ipynb` (filters out artifact road segments > 20 km)
  3. Upload the cleaned shapefile (`roads_cleaned.shp`) to your GEE project as a FeatureCollection asset

### OCHA-HDX/
- **What:** Burkina Faso administrative boundaries (national, regional, commune levels)
- **Source:** [OCHA HDX - Burkina Faso Admin Boundaries](https://data.humdata.org/dataset/cod-ab-bfa)
- **License:** Check dataset page for current license (typically CC-BY)
- **Used by:** Exploratory dataset, not used in the main pipeline (the filtered AOI is in `data/raw/Shapefile Ouaga/`).
- **Setup:** Download and extract into `data/raw/OCHA-HDX/`

### dem_ouaga/
- **What:** Copernicus DEM GLO-30 tiles downloaded locally for exploratory analysis
- **Source:** Downloaded via `notebooks/DEM/download_preprocess_DEM.ipynb`
- **License:** Copernicus programme, free and open access
- **Used by:** `notebooks/DEM/download_preprocess_DEM.ipynb` (exploratory only)
- **Note:** Not needed for the main pipeline, which fetches the DEM directly from GEE

### GHS-SMOD-Copernicus/
- **What:** Global Human Settlement Model (urban/rural classification grid)
- **Source:** [Copernicus GHS-SMOD](https://human-settlement.emergency.copernicus.eu/download.php?ds=smod)
- **License:** Copernicus open data policy — free to use with attribution
- **Used by:** Exploratory dataset, not used in the main pipeline.
- **Setup:** Download tiles R8_C18 and R8_C19 for the 2025 epoch (R2023A release) and extract into `data/raw/GHS-SMOD-Copernicus/`

### ndvi_ndbi_bsi/
- **What:** Pre-computed spectral indices (NDVI, NDBI, BSI) from Sentinel-2, resampled to 30m
- **Source:** Generated by `notebooks/NDVI_NDBI_BSI/NDVI_NDBI_BSI_Sentinel2_Ouagadougou.ipynb`
- **License:** Derived from Copernicus Sentinel-2 data (open)
- **Used by:** Reference/cache only — the main pipeline recomputes these from GEE
- **Setup:** Run the NDVI/NDBI/BSI notebook, or skip (not required for the main pipeline)

### ERA5 daily temperature (Heatwave analysis)
- **What:** ERA5-Land daily 2m temperature for Ouagadougou (2001-2024)
- **Source:** [Copernicus CDS](https://cds.climate.copernicus.eu/) — dataset: `derived-era5-land-daily-statistics`, variable: `2m_temperature`
- **License:** Copernicus, free and open access (requires CDS account registration)
- **Used by:** `notebooks/Heatwave/ERA5_Daily_Temperature_Ouagadougou.ipynb` and `notebooks/Heatwave/Heatwave_Analysis_Ouagadougou.ipynb`
- **Setup:** Register for a CDS API account, then run the download notebook. The output (`Ouagadougou_2001_2024_daily_tmax.nc`) is gitignored and must be regenerated locally.
- **Note:** Not needed for the main pipeline. Used for heatwave context analysis.

## Processed Data

The `processed/` directory contains outputs from the processing pipeline. The main output is:

- **`ouaga_aligned_stack.tif`** — 10-band GeoTIFF, 30m resolution, EPSG:32630 (UTM zone 30N), Float32

Band order (defined in `config/processing.yaml`):

| Band | Name | Description |
|---|---|---|
| 1 | NDVI | Normalized Difference Vegetation Index |
| 2 | NDBI | Normalized Difference Built-up Index |
| 3 | BSI | Bare Soil Index |
| 4 | DEM | Elevation (meters above sea level) |
| 5 | distance_to_water | Distance to nearest water body (meters) |
| 6 | distance_to_roads | Distance to nearest road (meters) |
| 7 | built_density | Fraction of built-up land in 90m neighbourhood |
| 8 | green_density | Fraction of green land in 90m neighbourhood |
| 9 | LST | Land Surface Temperature (°C, hot-season median) |
| 10 | hotspot | Binary: 1 = LST hotspot, 0 = not |

These files are generated by `notebooks/01_processing_pipeline.ipynb` and should not be edited manually.
