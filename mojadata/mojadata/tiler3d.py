import os
import numpy as np
import logging
import traceback
from io import BytesIO
from mojadata.util import gdalconst
from mojadata.util import gdal
from mojadata.util.gdalhelper import GDALHelper
from mojadata.tiler import Tiler
from mojadata.util.log import get_logger
from mojadata.config import (
    TILER_MEMORY_LIMIT,
    GDAL_MEMORY_LIMIT
)
from mojadata.cleanup import cleanup

class Tiler3D(Tiler):
    '''
    Processes layers into the uncompressed tile/block/cell stack/timeseries format
    supported by the Flint platform.

    :param bounding_box: the bounding box that defines the study area and other
        characteristics of the output
    :type bounding_box: :class:`.BoundingBox`
    :param tile_extent: [optional] the length of one side of a :class:`.Tile`, in
        units defined by the bounding box projection; default 1 degree in WGS84
    :type tile_extent: float
    :param block_extent: [optional] the length of one side of a :class:`.Block`, in
        units defined by the bounding box projection; default 0.1 degree in WGS84
    :type block_extent: float
    '''

    def __init__(self, bounding_box, tile_extent=1.0, block_extent=0.1):
        self._log = get_logger(self.__class__)
        self._bounding_box = bounding_box
        self._tile_extent = tile_extent
        self._block_extent = block_extent

    def tile(self, stacks, output_path="."):
        working_path = os.path.abspath(os.curdir)
        os.makedirs(output_path, exist_ok=True)
        os.chdir(output_path)
        try:
            with cleanup():
                self._bounding_box.init()

                for stack in stacks:
                    self._log.info("Processing stack: {}".format(stack.name))
                    processed_layer_name = "{}_moja".format(stack.name, "moja")
                    output_folder = os.path.join(processed_layer_name)
                    if not os.path.exists(output_folder):
                        os.makedirs(output_folder)

                    self._log.info("Processing layers...")
                    pool = self._create_pool(_pool_init, (self._bounding_box, stack, self._block_extent))
                    results = [pool.apply_async(_process_layer, (i,)) for i in range(len(stack.layers))]

                    rasters = []
                    first_stack_layer = None
                    for i, result in enumerate(results):
                        messages, processed_layer = result.get()
                        for message in messages:
                            self._log.log(*message)

                        if not processed_layer or processed_layer.is_empty():
                            continue

                        self._log.debug("Stack {}, layer {}: {}".format(stack.name, i, processed_layer.name))
                        rasters.append(os.path.abspath(processed_layer.path))
                        if i == 0:
                            first_stack_layer = processed_layer

                    self._log.info("Writing tiles for {}".format(stack.name))
                    for tile in first_stack_layer.tiles(self._tile_extent, self._block_extent):
                        out_path = os.path.join(
                            output_folder,
                            "{}_{}.blk".format(processed_layer_name, tile.name))

                        pool.apply_async(_write_tile, (out_path, tile, rasters))

                    pool.close()
                    pool.join()

                    metadata_path = os.path.join(output_folder, "{}.json".format(processed_layer_name))
                    self._write_metadata(stack, first_stack_layer, metadata_path)

                study_area_info = self._get_study_area_info()
                study_area_info["layers"] = [stack.metadata for stack in stacks]
                Tiler.write_json(study_area_info, "study_area.json")

                return study_area_info
        finally:
            os.chdir(working_path)

    def _write_metadata(self, stack, layer, path):
        info = GDALHelper.info(layer.path)
        pixel_size = abs(info["geoTransform"][1])

        # Attribute tables are not supported for stack layers.
        metadata = {
            "layer_type"   : "StackLayer",
            "nLayers"      : len(stack.layers),
            "layer_data"   : layer.data_type,
            "nodata"       : layer.nodata_value,
            "tileLatSize"  : self._tile_extent,
            "tileLonSize"  : self._tile_extent,
            "blockLatSize" : self._block_extent,
            "blockLonSize" : self._block_extent,
            "cellLatSize"  : pixel_size,
            "cellLonSize"  : pixel_size
        }

        metadata.update(stack.metadata)
        Tiler.write_json(metadata, path)

def _process_layer(layer_idx):
    messages = []
    processed_layer = None
    layer_name = ""
    try:
        layer = stack.layers[layer_idx]
        layer_name = layer.name
        messages.append((logging.INFO, "Processing layer: {}".format(layer_name)))
        with cleanup():
            processed_layer, layer_messages = bbox.normalize(
                layer,
                block_extent,
                stack.requested_pixel_size,
                stack.data_type)
            messages += layer_messages
    except BaseException as e:
        messages.append((logging.ERROR, "Error in layer '{}': {}".format(layer_name, e)))
        messages.append((logging.DEBUG, traceback.format_exc()))

    return messages, processed_layer

def _write_tile(out_path, tile, raster_paths):
    buffer_memory_limit = min(TILER_MEMORY_LIMIT, 2**31 - 1)
    rasters = [gdal.Open(path, gdalconst.GA_ReadOnly) for path in raster_paths]
    with open(out_path, "wb", buffering=buffer_memory_limit) as blocked_file:
        for block in tile.blocks:
            block_data = []
            for raster in rasters:
                band = raster.GetRasterBand(1)
                block_data.append(band.ReadAsArray(
                    block.x_offset, block.y_offset,
                    block.x_size, block.y_size))
                band = None

            block = np.stack(block_data, -1)
            b = BytesIO(bytearray(block))
            blocked_file.write(b.getvalue())

def _pool_init(_bounding_box, _stack, _block_extent):
    global bbox, stack, block_extent
    gdal.SetCacheMax(GDAL_MEMORY_LIMIT)
    bbox = _bounding_box
    stack = _stack
    block_extent = _block_extent
