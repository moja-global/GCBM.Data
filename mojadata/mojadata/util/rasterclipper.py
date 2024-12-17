import os
import uuid
import numpy as np
from mojadata import cleanup
from mojadata.util import gdal
from mojadata.util import ogr
from mojadata.util import osr
from mojadata.util.gdalhelper import GDALHelper
from mojadata import config as gdal_config


def clip_raster(bounding_box_layer, target_layer, output_path):
    '''
    Given two rasters that cover the same extent, simulates clipping by
    propagating the nodata pixels from the bounding box layer to the target
    layer.
    '''
    GDALHelper.calc(
        [target_layer.path, bounding_box_layer.path],
        output_path,
        lambda d: np.where(
            d[1] != bounding_box_layer.nodata_value,
            d[0],
            target_layer.nodata_value))

def shrink_to_data(target_layer, output_path):
    '''
    Shrink the spatial extent of the target layer to fit the data.
    '''
    output_path = os.path.abspath(output_path)
    tmp_dir = "_".join((os.path.splitext(output_path)[0], str(uuid.uuid1())[:4]))
    os.makedirs(tmp_dir, exist_ok=True)
    cleanup.register_temp_dir(tmp_dir)

    calc_output_path = os.path.join(tmp_dir, "flattened_data.tif")
    GDALHelper.calc(
        target_layer.path, calc_output_path, lambda d: d != target_layer.nodata_value,
        data_type=gdal.GDT_Byte, nodata_value=0)

    src_ds = gdal.Open(target_layer.path)
    srs = osr.SpatialReference()
    srs.ImportFromWkt(src_ds.GetProjectionRef())

    cutline_output_path = os.path.join(tmp_dir, "flattened_data_extent.shp")
    drv = ogr.GetDriverByName("ESRI Shapefile")
    dst_ds = drv.CreateDataSource(cutline_output_path)
    dst_layer = dst_ds.CreateLayer("out", geom_type=ogr.wkbPolygon, srs=srs)

    flattened_data_ds = gdal.Open(calc_output_path)
    flattened_data_band = flattened_data_ds.GetRasterBand(1)
    gdal.Polygonize(flattened_data_band, flattened_data_band, dst_layer, -1, [])
    min_x, max_x, min_y, max_y = dst_layer.GetExtent()

    gdal.Translate(output_path, src_ds,
                   projWin=[min_x, max_y, max_x, min_y],
                   options=gdal_config.GDAL_TRANSLATE_OPTIONS.copy(),
                   creationOptions=gdal_config.GDAL_TRANSLATE_CREATION_OPTIONS)
