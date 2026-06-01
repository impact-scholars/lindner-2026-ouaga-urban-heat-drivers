"""Data loading utilities for Ouagadougou urban heat analysis."""

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import yaml


def load_config(config_path: str | Path) -> dict:
    """Load a YAML configuration file and derive computed fields.

    Parameters
    ----------
    config_path : str | Path
        Path to the YAML configuration file.

    Returns
    -------
    dict
        Configuration dictionary with all fields ready to use.

    Raises
    ------
    FileNotFoundError
        If the config file doesn't exist.
    ValueError
        If the config file is empty or missing required keys.
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    if not config:
        raise ValueError(f"Config file is empty: {config_path}")

    # Validate required keys
    required_keys = [
        "target_crs",
        "target_scale",
        "study_years",
        "hot_season_months",
        "band_names",
        "raster_name",
    ]
    missing = [k for k in required_keys if k not in config]
    if missing:
        raise ValueError(f"Config missing required keys: {missing}")

    # Derive paths from conventions
    # Project root is inferred from config file location: config/ is one level down
    project_root = config_path.resolve().parent.parent

    config["data_dir"] = project_root / "data" / "processed"
    config["raster_path"] = config["data_dir"] / (config["raster_name"] + ".tif")
    # Resolve configured paths relative to project root
    for key in ["figures_dir", "shapefile_path"]:
        if key in config:
            config[key] = project_root / config[key]

    # Derive band_index from band_names (1-indexed for rasterio)
    config["band_index"] = {
        name: i + 1 for i, name in enumerate(config["band_names"])
    }

    # Create output directories
    for key in ["data_dir", "figures_dir"]:
        if key in config:
            config[key].mkdir(parents=True, exist_ok=True)

    return config


def load_dataset(
    config_path: str | Path = "config/processing.yaml",
) -> tuple[pd.DataFrame, dict]:
    """Load the processed raster stack into a DataFrame, ready for analysis.

    Convenience function that loads the config and raster in one call.
    Colleagues can get a modeling-ready DataFrame with:

        from src.data import load_dataset
        df, config = load_dataset()

    Parameters
    ----------
    config_path : str | Path
        Path to the YAML configuration file. Defaults to the project config.

    Returns
    -------
    tuple[pd.DataFrame, dict]
        (df, config) where df has columns [row, col, lon, lat, <band_names>]
        and config is the full configuration dictionary (includes 'raster_info'
        with raster properties and loading diagnostics).
    """
    config = load_config(config_path)
    df, info = load_raster_to_dataframe(
        config["raster_path"], config["band_names"]
    )
    config["raster_info"] = info
    return df, config


def load_raster_to_dataframe(
    raster_path: str | Path, band_names: list[str]
) -> tuple[pd.DataFrame, dict]:
    """Load a multi-band GeoTIFF and convert to a DataFrame with coordinates.

    If the GeoTIFF has band descriptions embedded, validates them against
    the expected band_names. If descriptions are present but don't match,
    uses the file's descriptions as the source of truth.

    Parameters
    ----------
    raster_path : str | Path
        Path to the multi-band GeoTIFF.
    band_names : list[str]
        Expected band names (from config).

    Returns
    -------
    tuple[pd.DataFrame, dict]
        (df, info) where df has columns [row, col, lon, lat, <band_names>]
        and info contains raster properties and loading diagnostics:
        - data_3d: raw numpy array (bands, rows, cols)
        - shape, crs, resolution, bounds: raster properties
        - band_names: resolved names (from file or config)
        - band_names_match: True if match, False if mismatch, None if no
          descriptions in file
        - file_band_names: descriptions from file, or None
        - n_valid, n_total, coverage_pct: pixel coverage stats
    """
    with rasterio.open(raster_path) as src:
        data_3d = src.read()
        transform = src.transform
        descriptions = src.descriptions
        info = {
            'shape': data_3d.shape,
            'crs': src.crs,
            'transform': transform,
            'resolution': (transform[0], -transform[4]),
            'bounds': src.bounds,
            'meta': src.meta.copy(),
        }

    # Validate band names against embedded descriptions if available
    has_descriptions = descriptions and all(d is not None for d in descriptions)
    if has_descriptions:
        file_band_names = list(descriptions)
        info['file_band_names'] = file_band_names
        info['band_names_match'] = (file_band_names == band_names)
        if not info['band_names_match']:
            band_names = file_band_names
    else:
        info['file_band_names'] = None
        info['band_names_match'] = None

    info['band_names'] = band_names

    # Find valid pixels (finite in all bands — excludes NaN, -inf, +inf)
    valid_mask = np.isfinite(data_3d[0])
    for i in range(1, data_3d.shape[0]):
        valid_mask &= np.isfinite(data_3d[i])

    rows, cols = np.where(valid_mask)
    n_valid = len(rows)
    n_total = data_3d.shape[1] * data_3d.shape[2]

    info['n_valid'] = n_valid
    info['n_total'] = n_total
    info['coverage_pct'] = 100 * n_valid / n_total
    info['data_3d'] = data_3d

    # Get coordinates for valid pixels
    xs, ys = rasterio.transform.xy(transform, rows, cols)

    # Build DataFrame
    df_dict = {
        'row': rows,
        'col': cols,
        'lon': xs,
        'lat': ys,
    }

    for i, name in enumerate(band_names):
        df_dict[name] = data_3d[i][rows, cols]

    df = pd.DataFrame(df_dict)

    return df, info
