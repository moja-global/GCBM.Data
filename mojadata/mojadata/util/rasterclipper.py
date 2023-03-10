from mojadata.util.gdal_calc import Calc
from mojadata.config import (
    GDAL_CREATION_OPTIONS
)


def clip_raster(bounding_box_layer, target_layer, output_path):
    '''
    Given two rasters that cover the same extent, simulates clipping by
    propagating the nodata pixels from the bounding box layer to the target
    layer.
    '''
    calc = "A * (B != {0}) + ((B == {0}) * {1})".format(
        bounding_box_layer.nodata_value, target_layer.nodata_value)

    Calc(calc, output_path, target_layer.nodata_value,
         creation_options=GDAL_CREATION_OPTIONS, overwrite=True,
         type=target_layer.data_type, A=target_layer.path,
         B=bounding_box_layer.path, quiet=True)
