"""Smoke tests for src.data — config loading and raster→DataFrame conversion."""
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.data import load_config, load_dataset, load_raster_to_dataframe

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "processing.yaml"


def test_load_config_returns_required_keys():
    """The project config loads and exposes both raw and derived keys."""
    config = load_config(CONFIG_PATH)

    expected_top_level = {
        "target_crs",
        "target_scale",
        "study_years",
        "hot_season_months",
        "band_names",
        "raster_name",
    }
    assert expected_top_level.issubset(config.keys())

    # Derived fields added by load_config
    assert "data_dir" in config
    assert "raster_path" in config
    assert "band_index" in config
    # band_index is 1-indexed for rasterio compatibility
    assert min(config["band_index"].values()) == 1


def test_load_config_raises_on_missing_file(tmp_path):
    """A nonexistent config path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does_not_exist.yaml")


def test_load_raster_to_dataframe_synthetic(tmp_path):
    """Round-trip a tiny synthetic raster; verify valid-pixel filtering."""
    raster_path = tmp_path / "synthetic.tif"
    band_names = ["band_a", "band_b"]

    # 5x5 raster, 2 bands; introduce one NaN to test valid-pixel filtering
    data = np.arange(50, dtype=np.float32).reshape(2, 5, 5)
    data[0, 0, 0] = np.nan

    transform = from_origin(west=0.0, north=0.0, xsize=1.0, ysize=1.0)
    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        height=5,
        width=5,
        count=2,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data)
        dst.descriptions = tuple(band_names)

    df, info = load_raster_to_dataframe(raster_path, band_names)

    # 25 pixels minus 1 NaN = 24 valid
    assert len(df) == 24
    assert list(df.columns) == ["row", "col", "lon", "lat", "band_a", "band_b"]
    assert info["n_valid"] == 24
    assert info["n_total"] == 25
    assert info["band_names_match"] is True


@pytest.mark.skipif(
    not (PROJECT_ROOT / "data" / "processed" / "ouaga_aligned_stack.tif").exists(),
    reason="processed raster not available — download from Zenodo to enable",
)
def test_load_dataset_real_raster():
    """End-to-end smoke test on the actual project raster (when available)."""
    df, config = load_dataset(CONFIG_PATH)

    expected_cols = ["row", "col", "lon", "lat"] + config["band_names"]
    assert list(df.columns) == expected_cols
    assert len(df) > 0
    # No NaN in valid-pixel DataFrame
    assert not df.isna().any().any()
    assert "raster_info" in config
