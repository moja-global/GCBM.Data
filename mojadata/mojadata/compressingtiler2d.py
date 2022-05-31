import os
import zipfile
import logging
import traceback
from io import BytesIO
from mojadata.util.log import get_logger
from future.utils import viewitems
from zipfile import ZipFile
from mojadata.util import gdalconst
from mojadata.util import gdal
from mojadata.tiler import Tiler
from mojadata.cleanup import cleanup
from mojadata.config import (
    GDAL_MEMORY_LIMIT,
    PROCESS_MEMORY_LIMIT
)


class CompressingTiler2D(Tiler):
    '''
    Processes layers into the compressed tile/block/cell format supported by the
    Flint platform.

    :param bounding_box: the bounding box that defines the study area and other
        characteristics of the output
    :type bounding_box: :class:`.BoundingBox`
    :param tile_extent: [optional] the length of one side of a :class:`.Tile`, in
        units defined by the bounding box projection; default 1 degree in WGS84
    :type tile_extent: float
    :param block_extent: [optional] the length of one side of a :class:`.Block`, in
        units defined by the bounding box projection; default 0.1 degree in WGS84
    :type block_extent: float
    :param use_bounding_box_resolution: [optional] force all tiled layers to the
        bounding box resolution; by default, each layer's resolution is the nearest
        multiple of the bounding box resolution
    :type use_bounding_box_resolution: bool
    :param compact_attribute_table: [optional] write the attribute table in a
        compact format - not compatible with Flint, but may be useful for other
        scripts using the mojadata library
    :type compact_attribute_table: bool
    '''

    def __init__(self, bounding_box, tile_extent=1.0, block_extent=0.1,
                 use_bounding_box_resolution=False, compact_attribute_table=False):
        self._log = get_logger(self.__class__)
        self._bounding_box = bounding_box
        self._tile_extent = tile_extent
        self._block_extent = block_extent
        self._use_bounding_box_resolution = use_bounding_box_resolution
        self._compact_attribute_table = compact_attribute_table

    def tile(self, layers, output_path="."):
        self._skipped_layers = []
        working_path = os.path.abspath(os.curdir)
        os.makedirs(output_path, exist_ok=True)
        os.chdir(output_path)
        try:
            with cleanup():
                self._bounding_box.init()
                layers = self._remove_duplicates(layers)
                layer_config = {
                    "tile_extent": self._tile_extent,
                    "block_extent": self._block_extent,
                    "use_bbox_res": self._use_bounding_box_resolution,
                    "compact_attribute_table": self._compact_attribute_table
                }

                self._log.info("Processing layers...")
                pool = self._create_pool(_pool_init, (self._bounding_box, layers, layer_config))
                for i in range(len(layers)):
                    pool.apply_async(_tile_layer, (i,), callback=self._handle_tile_layer_result)

                pool.close()
                pool.join()

                study_area_info = self._get_study_area_info()
                study_area_info["layers"] = [
                    layer.metadata for layer in layers
                    if layer.name not in self._skipped_layers
                ]

                Tiler.write_json(study_area_info, "study_area.json")

                return study_area_info
        finally:
            os.chdir(working_path)

    def _handle_tile_layer_result(self, result):
        layer_name, success, messages = result
        if not success:
            self._skipped_layers.append(layer_name)

        for message in messages:
            self._log.log(*message)

    def _remove_duplicates(self, layers):
        unique_layers = []
        layer_names = []
        for layer in layers:
            if layer.name in layer_names:
                self._log.warning("Duplicate layer found: {}".format(layer.name))
                continue

            layer_names.append(layer.name)
            unique_layers.append(layer)

        return unique_layers


def _pool_init(_bounding_box, _layers, _config):
    global bbox, layers, config
    gdal.SetCacheMax(GDAL_MEMORY_LIMIT)
    bbox = _bounding_box
    layers = _layers
    config = _config


def _tile_layer(layer_idx):
    messages = []
    layer_name = ""
    try:
        layer = layers[layer_idx]
        layer_name = layer.name
        with cleanup():
            messages.append((logging.INFO, "Processing layer: {}".format(layer_name)))
            if layer.is_empty():
                messages.append((logging.WARNING, "Layer '{}' is empty - skipping.".format(layer_name)))
                return layer_name, False, messages

            layer, layer_messages = bbox.normalize(
                layer,
                config["block_extent"],
                bbox.pixel_size if config["use_bbox_res"] else None)

            messages += layer_messages

            if not layer or layer.is_empty():
                messages.append((logging.WARNING, "Layer '{}' is empty - skipping.".format(layer_name)))
                return layer_name, False, messages

            raster_name = "{}_moja".format("".join(layer_name.split("_moja")))
            output_folder = os.path.join(os.path.dirname(layer.path), raster_name)
            if not os.path.exists(output_folder):
                os.makedirs(output_folder)

            metadata_path = os.path.join(output_folder, "{}.json".format(raster_name))
            _write_metadata(layer, config, metadata_path)

            ds = gdal.Open(layer.path, gdalconst.GA_ReadOnly)
            try:
                buffer_memory_limit = min(PROCESS_MEMORY_LIMIT, 2**31 - 1)
                for tile in layer.tiles(config["tile_extent"], config["block_extent"]):
                    messages.append((logging.INFO, "Processing tile: {}".format(tile.name)))
                    tile_out_path = os.path.join(
                        output_folder,
                        "{}_{}.zip".format(raster_name, tile.name))

                    with open(tile_out_path, "wb", buffering=buffer_memory_limit) as output_file:
                        with ZipFile(output_file, "w", zipfile.ZIP_DEFLATED, True) as output_container:
                            band = ds.GetRasterBand(1)
                            try:
                                for i, block in enumerate(tile.blocks):
                                    block_out_path = os.path.join("{}.blk".format(i))
                                    data = band.ReadAsArray(block.x_offset, block.y_offset,
                                                            block.x_size, block.y_size)
                                    b = BytesIO(bytearray(data))
                                    output_container.writestr(block_out_path, b.getvalue())
                            except:
                                raise
                            finally:
                                band = None
            except:
                raise
            finally:
                ds = None
    except Exception as e:
        messages.append((logging.ERROR, "Error in layer '{}': {}".format(layer_name, e)))
        messages.append((logging.DEBUG, traceback.format_exc()))
        return layer_name, False, messages

    return layer_name, True, messages

def _write_metadata(layer, config, path):
    metadata = {
        "layer_type"  : "GridLayer",
        "layer_data"  : layer.data_type,
        "nodata"      : layer.nodata_value,
        "tileLatSize" : config["tile_extent"],
        "tileLonSize" : config["tile_extent"],
        "blockLatSize": config["block_extent"],
        "blockLonSize": config["block_extent"],
        "cellLatSize" : layer.pixel_size,
        "cellLonSize" : layer.pixel_size
    }

    if layer.attribute_table:
        if config["compact_attribute_table"]:
            metadata["attribute_names"] = layer.attributes
            metadata["attributes"] = layer.attribute_table
        else:
            attributes = {}
            for pixel_value, attr_values in viewitems(layer.attribute_table):
                if len(attr_values) == 1:
                    attributes[pixel_value] = attr_values[0]
                else:
                    attributes[pixel_value] = dict(zip(layer.attributes, attr_values))

            metadata["attributes"] = attributes

    Tiler.write_json(metadata, path)
