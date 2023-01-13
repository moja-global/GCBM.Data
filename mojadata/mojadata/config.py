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

# WARNING: GDAL mutates these lists when passed to its bindings using the "options="
# argument. Always copy when using!
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


def refresh(pool_size):
    '''
    Refresh all the pool and memory limits for the given pool size. Sometimes
    when using mojadata from another package, multiprocessing.cpu_count()
    returns 1 instead of the actual thread count, so a workaround is to call
    multiprocessing.cpu_count() in the outermost application, then pass the
    result to either this function before interacting with the rest of the
    mojadata package, or directly to the Tiler constructor.

    :param pool_size: the pool size (thread count) to use
    :type pool_size: int
    '''
    global GDAL_THREADS
    global PROCESS_POOL_SIZE
    global MEMORY_LIMIT_SCALE
    global TILER_MEMORY_LIMIT
    global PROCESS_MEMORY_LIMIT
    global GDAL_MEMORY_LIMIT
    global GDAL_OPTIONS
    global GDAL_WARP_OPTIONS
    global GDAL_TRANSLATE_OPTIONS
    global GDAL_RASTERIZE_OPTIONS
    global GDAL_CREATION_OPTIONS
    global GDAL_WARP_CREATION_OPTIONS
    global GDAL_TRANSLATE_CREATION_OPTIONS
    global GDAL_RASTERIZE_CREATION_OPTIONS

    GDAL_THREADS = min(pool_size, 4)
    PROCESS_POOL_SIZE = pool_size
    MEMORY_LIMIT_SCALE = int(pool_size / 10) or 1
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
