import psutil
from multiprocessing import cpu_count

# WARNING: GDAL_THREADS is capped at 4 because larger values (i.e. cpu_count() == 40)
# can sometimes cause chunks of layers to go missing (memory issue?) when tiling a
# large list of layers.
GDAL_THREADS = min(cpu_count(), 4)

PROCESS_POOL_SIZE = cpu_count()
MEMORY_LIMIT_SCALE = int(cpu_count() / 10) or 1

TILER_MEMORY_LIMIT = int(psutil.virtual_memory().available * 0.75 / MEMORY_LIMIT_SCALE)
PROCESS_MEMORY_LIMIT = int(TILER_MEMORY_LIMIT / PROCESS_POOL_SIZE)
GDAL_MEMORY_LIMIT = int(PROCESS_MEMORY_LIMIT / GDAL_THREADS)

GDAL_OPTIONS = []
GDAL_WARP_OPTIONS = GDAL_OPTIONS + ["NUM_THREADS={}".format(GDAL_THREADS)]
GDAL_TRANSLATE_OPTIONS = GDAL_OPTIONS + ["NUM_THREADS={}".format(GDAL_THREADS)]
GDAL_RASTERIZE_OPTIONS = GDAL_OPTIONS

GDAL_CREATION_OPTIONS = ["COMPRESS=DEFLATE", "BIGTIFF=YES", "TILED=YES"]
GDAL_WARP_CREATION_OPTIONS = GDAL_CREATION_OPTIONS + ["NUM_THREADS={}".format(GDAL_THREADS)]
GDAL_TRANSLATE_CREATION_OPTIONS = GDAL_CREATION_OPTIONS + ["NUM_THREADS={}".format(GDAL_THREADS)]
GDAL_RASTERIZE_CREATION_OPTIONS = GDAL_CREATION_OPTIONS

# Change to "ON" to enable extra GDAL debugging (CPL_DEBUG)
DEBUG = "OFF"
