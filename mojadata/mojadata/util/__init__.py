import warnings
warnings.simplefilter(action="ignore", category=FutureWarning)

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

def refresh_gdal_config():
    from mojadata.config import DEBUG
    from mojadata.config import GDAL_MEMORY_LIMIT
    from mojadata.config import PROCESS_POOL_SIZE
    gdal.SetConfigOption("OGR_SQLITE_CACHE", str(int(GDAL_MEMORY_LIMIT / PROCESS_POOL_SIZE)))
    gdal.SetConfigOption("OGR_SQLITE_SYNCHRONOUS", "OFF")
    gdal.SetConfigOption("CPL_DEBUG", DEBUG)
    gdal.SetCacheMax(GDAL_MEMORY_LIMIT)
    gdal.SetConfigOption("GDAL_SWATH_SIZE", str(GDAL_MEMORY_LIMIT))
    gdal.SetConfigOption("VSI_CACHE", "TRUE")
    gdal.SetConfigOption("VSI_CACHE_SIZE", str(int(GDAL_MEMORY_LIMIT / PROCESS_POOL_SIZE)))
    gdal.SetConfigOption("GTIFF_DIRECT_IO", "YES")
    gdal.SetConfigOption("SQLITE_USE_OGR_VFS", "YES")

gdal.PushErrorHandler("CPLQuietErrorHandler")
refresh_gdal_config()
