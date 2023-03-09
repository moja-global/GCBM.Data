from mojadata.util import gdal

# For osgeo_utils.gdal_calc on older GDAL versions (i.e. Python 3.7):
if not hasattr(gdal, "GDT_Int8"): gdal.GDT_Int8 = gdal.GDT_Unknown
if not hasattr(gdal, "GDT_Int64"): gdal.GDT_Int64 = gdal.GDT_Unknown
if not hasattr(gdal, "GDT_UInt64"): gdal.GDT_UInt64 = gdal.GDT_Unknown

from osgeo_utils.gdal_calc import Calc
