try:
    from osgeo import gdal
except ImportError:
    import gdal

try:
    from osgeo import osr
except ImportError:
    import osr

try:
    from osgeo import ogr
except ImportError:
    import ogr

try:
    from osgeo import gdalconst
except ImportError:
    import gdalconst

from mojadata.config import DEBUG
from mojadata.config import GDAL_MEMORY_LIMIT

gdal.PushErrorHandler("CPLQuietErrorHandler")
gdal.SetConfigOption("OGR_SQLITE_CACHE", "1024")
gdal.SetConfigOption("OGR_SQLITE_SYNCHRONOUS", "OFF")
gdal.SetConfigOption("CPL_DEBUG", DEBUG)
gdal.SetCacheMax(GDAL_MEMORY_LIMIT)
