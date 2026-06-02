"""GEE feature computation and export for Ouagadougou urban heat analysis."""

import ee
import geemap
import geopandas as gpd


def load_aoi(config: dict) -> ee.Geometry:
    """Load area of interest from EE asset, falling back to shapefile.

    Parameters
    ----------
    config : dict
        Configuration dictionary with 'ee_boundary_asset' and optionally
        'shapefile_path'.

    Returns
    -------
    ee.Geometry
        Area of interest geometry.
    """
    try:
        aoi = ee.FeatureCollection(config["ee_boundary_asset"]).geometry()
        print("AOI loaded from Earth Engine asset")
        return aoi
    except Exception:
        aoi_gdf = gpd.read_file(config["shapefile_path"])
        aoi_gdf = aoi_gdf.to_crs("EPSG:4326")
        aoi_gdf = aoi_gdf.dissolve()
        coords = aoi_gdf.geometry.iloc[0].__geo_interface__["coordinates"]
        aoi = ee.Geometry.Polygon(coords)
        print("AOI loaded from shapefile")
        return aoi


def compute_all_features(aoi: ee.Geometry, config: dict) -> dict[str, ee.Image]:
    """Compute all feature layers for the study area.

    Parameters
    ----------
    aoi : ee.Geometry
        Area of interest boundary.
    config : dict
        Configuration dictionary from load_config().

    Returns
    -------
    dict[str, ee.Image]
        Dictionary mapping band names to their single-band ee.Image layers.
    """
    layers = {}

    # --- LST from Landsat (TARGET VARIABLE) ---
    lst_composite, hotspot_binary = _compute_lst_and_hotspot(aoi, config)
    layers["LST"] = lst_composite
    layers["hotspot"] = hotspot_binary

    # --- Sentinel-2 Spectral Indices ---
    spectral = _compute_spectral_indices(aoi, config)
    layers["NDVI"] = spectral.select("NDVI")
    layers["NDBI"] = spectral.select("NDBI")
    layers["BSI"] = spectral.select("BSI")

    # --- Distance to Water ---
    layers["distance_to_water"] = _compute_distance_to_water(config)

    # --- Distance to Roads ---
    layers["distance_to_roads"] = _compute_distance_to_roads(aoi, config)

    # --- Elevation ---
    layers["DEM"] = _compute_elevation(aoi)

    # --- Land Cover Density ---
    built, green = _compute_land_cover_density(config)
    layers["built_density"] = built
    layers["green_density"] = green

    return layers


def stack_layers(
    layers: dict[str, ee.Image], band_names: list[str], aoi: ee.Geometry
) -> ee.Image:
    """Stack individual layers into a single multi-band ee.Image.

    Parameters
    ----------
    layers : dict[str, ee.Image]
        Dictionary mapping band names to their ee.Image layers.
    band_names : list[str]
        Ordered list of band names (determines band order in stack).
    aoi : ee.Geometry
        Area of interest boundary for clipping.

    Returns
    -------
    ee.Image
        Multi-band image with bands ordered per band_names, cast to Float32.
    """
    # Stack all layers
    stack = layers[band_names[0]]
    for name in band_names[1:]:
        stack = stack.addBands(layers[name])

    # Clip to study area boundary
    stack = stack.clip(aoi)

    # Force band order to match config (single source of truth for band ordering)
    stack = stack.select(band_names)

    # Cast all bands to Float32 (smaller files, sufficient precision)
    return stack.toFloat()


def download_stack(image: ee.Image, aoi: ee.Geometry, config: dict) -> None:
    """Download a stacked image directly to a local GeoTIFF.

    Uses geemap to tile and download the image, bypassing Google Drive.

    Parameters
    ----------
    image : ee.Image
        Multi-band image to download.
    aoi : ee.Geometry
        Region to download.
    config : dict
        Configuration dictionary. Uses 'raster_path', 'target_crs',
        and 'target_scale'.
    """
    output_path = config["raster_path"]

    print(f"Downloading to {output_path}...")
    geemap.download_ee_image(
        image=image,
        filename=str(output_path),
        region=aoi,
        scale=config["target_scale"],
        crs=config["target_crs"],
    )
    print(f"Done. Saved to {output_path}")


# =============================================================================
# Private functions: one per data source
# =============================================================================


def _compute_lst_and_hotspot(
    aoi: ee.Geometry, config: dict
) -> tuple[ee.Image, ee.Image]:
    """Compute LST composite and binary hotspot map from Landsat.

    Parameters
    ----------
    aoi : ee.Geometry
        Area of interest boundary.
    config : dict
        Configuration dictionary.

    Returns
    -------
    tuple[ee.Image, ee.Image]
        (lst_composite, hotspot_binary) - each single-band.
    """
    lst_valid_range = config["lst_valid_range"]

    def process_landsat_lst(img):
        """Extract LST with quality filtering."""
        lst_celsius = img.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15)

        # Quality mask: clear conditions
        qa = img.select('QA_PIXEL')
        clear = qa.bitwiseAnd(1 << 6).neq(0)

        # Range check: reject physically implausible values
        valid_range = lst_celsius.gt(lst_valid_range[0]) \
                                 .And(lst_celsius.lt(lst_valid_range[1]))

        return lst_celsius.updateMask(clear).updateMask(valid_range) \
                          .rename('LST').copyProperties(img, ['system:time_start'])

    # Build multi-year hot season filter
    date_filters = []
    for year in config["study_years"]:
        for month in config["hot_season_months"]:
            start = ee.Date.fromYMD(year, month, 1)
            end = start.advance(1, 'month')
            date_filters.append(ee.Filter.date(start, end))

    landsat = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
        .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2')) \
        .filterBounds(aoi) \
        .filter(ee.Filter.Or(*date_filters)) \
        .filter(ee.Filter.lt('CLOUD_COVER', config["cloud_threshold"])) \
        .map(process_landsat_lst)

    # Composite: median reduces outlier influence
    lst_composite = landsat.median().rename('LST')

    # Compute threshold for hotspots
    lst_stats = lst_composite.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True),
        geometry=aoi,
        scale=config["target_scale"],
        crs=config["target_crs"],
        maxPixels=1e13
    )
    threshold = ee.Number(lst_stats.get('LST_mean')).add(
        ee.Number(lst_stats.get('LST_stdDev')).multiply(config["hotspot_std_multiplier"])
    )
    # Create binary hotspot map
    hotspot_binary = (
        lst_composite
        .gt(threshold)
        .rename('hotspot')
        .updateMask(lst_composite.mask())  # Mask no-data areas
    )

    return lst_composite, hotspot_binary


def _compute_spectral_indices(aoi: ee.Geometry, config: dict) -> ee.Image:
    """Compute NDVI, NDBI, BSI from Sentinel-2.

    Parameters
    ----------
    aoi : ee.Geometry
        Area of interest boundary.
    config : dict
        Configuration dictionary.

    Returns
    -------
    ee.Image
        Three-band image with NDVI, NDBI, BSI.
    """

    def process_sentinel(img):
        """Cloud mask and compute indices at native resolution."""
        qa = img.select('QA60')
        cloud_mask = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))

        masked = img.updateMask(cloud_mask).divide(10000)

        ndvi = masked.normalizedDifference(['B8', 'B4']).rename('NDVI')
        ndbi = masked.normalizedDifference(['B11', 'B8']).rename('NDBI')
        bsi = masked.expression(
            '((SWIR + RED) - (NIR + BLUE)) / ((SWIR + RED) + (NIR + BLUE))',
            {'SWIR': masked.select('B11'), 'RED': masked.select('B4'),
             'NIR': masked.select('B8'), 'BLUE': masked.select('B2')}
        ).rename('BSI')

        return ndvi.addBands(ndbi).addBands(bsi).copyProperties(img, ['system:time_start'])

    sentinel = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
        .filterBounds(aoi) \
        .filter(ee.Filter.calendarRange(3, 5, 'month')) \
        .filter(ee.Filter.calendarRange(config["sentinel_year"], config["sentinel_year"], 'year')) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', config["cloud_threshold"])) \
        .map(process_sentinel)

    spectral_indices = sentinel.median()

    return spectral_indices


def _compute_distance_to_water(config: dict) -> ee.Image:
    """Compute distance to nearest water body using JRC Global Surface Water.

    Parameters
    ----------
    config : dict
        Configuration dictionary.

    Returns
    -------
    ee.Image
        Single-band image with distance to water in meters.
    """
    gsw = ee.Image('JRC/GSW1_4/GlobalSurfaceWater')
    water_mask = gsw.select('occurrence').gte(70).unmask(0)

    # fastDistanceTransform returns distance in PIXELS, multiply by scale.
    # .reproject() AFTER FDT forces the transform to compute at the target scale;
    # without it, GEE's lazy evaluation runs FDT at whatever downstream scale is
    # requested (e.g., export scale), making the pixel-to-meter conversion wrong.
    target_proj = ee.Projection(config["target_crs"]).atScale(config["target_scale"])
    distance_water_squared = water_mask.fastDistanceTransform(
        neighborhood=500,  # Max search in pixels: 500 * 30m = ~15km
        units='pixels',
        metric='squared_euclidean'
    ).reproject(target_proj)

    # Convert pixels to meters
    distance_water = distance_water_squared.sqrt().multiply(
        config["target_scale"]
    ).rename('distance_to_water')

    return distance_water


def _compute_distance_to_roads(aoi: ee.Geometry, config: dict) -> ee.Image:
    """Compute distance to nearest road.

    Parameters
    ----------
    aoi : ee.Geometry
        Area of interest boundary.
    config : dict
        Configuration dictionary.

    Returns
    -------
    ee.Image
        Single-band image with distance to roads in meters.
    """
    roads = ee.FeatureCollection(config["roads_asset"]).filterBounds(aoi)
    road_raster = ee.Image().paint(roads, 1).unmask(0).setDefaultProjection(
        crs=config["target_crs"], scale=config["target_scale"]
    )

    # .reproject() AFTER FDT forces the transform to compute at the target scale
    distance_roads_squared = road_raster.fastDistanceTransform(
        neighborhood=500,  # 500 * 30m = ~15km max
        units='pixels',
        metric='squared_euclidean'
    ).reproject(crs=config["target_crs"], scale=config["target_scale"])
    # Convert to meters
    distance_roads = distance_roads_squared.sqrt().multiply(
        config["target_scale"]
    ).rename('distance_to_roads')

    return distance_roads


def _compute_elevation(aoi: ee.Geometry) -> ee.Image:
    """Load elevation from Copernicus DEM.

    Parameters
    ----------
    aoi : ee.Geometry
        Area of interest boundary.

    Returns
    -------
    ee.Image
        Single-band DEM image.
    """
    dem = ee.ImageCollection('COPERNICUS/DEM/GLO30').filterBounds(aoi).mosaic()
    elevation = dem.select('DEM')

    return elevation


def _compute_land_cover_density(config: dict) -> tuple[ee.Image, ee.Image]:
    """Compute built-up and green space density from ESA WorldCover.

    Parameters
    ----------
    config : dict
        Configuration dictionary.

    Returns
    -------
    tuple[ee.Image, ee.Image]
        (built_density, green_density) - each single-band, values 0-1.
    """
    esa = ee.Image(f'ESA/WorldCover/v200/{config["worldcover_year"]}')
    built_mask = esa.eq(50)
    green_mask = esa.eq(10).Or(esa.eq(20))

    kernel = ee.Kernel.circle(radius=90, units='meters', normalize=True)
    built_density = built_mask.reduceNeighborhood(
        ee.Reducer.mean(), kernel
    ).rename('built_density')
    green_density = green_mask.reduceNeighborhood(
        ee.Reducer.mean(), kernel
    ).rename('green_density')

    return built_density, green_density
