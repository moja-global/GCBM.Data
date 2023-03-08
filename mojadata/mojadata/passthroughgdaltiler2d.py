import os
import logging
import traceback
import shutil
from mojadata.util.log import get_logger
from future.utils import viewitems
from mojadata.util import gdal
from mojadata.tiler import Tiler
from mojadata.config import GDAL_MEMORY_LIMIT

class PassthroughGdalTiler2D(Tiler):
    '''
    Writes the metadata and study area file for a collection of layers that have
    been previously tiled or already have the correct resolution and spatial
    extent.

    :param tile_extent: [optional] the length of one side of a :class:`.Tile`, in
        units defined by the bounding box projection; default 1 degree in WGS84
    :type tile_extent: float
    :param block_extent: [optional] the length of one side of a :class:`.Block`, in
        units defined by the bounding box projection; default 0.1 degree in WGS84
    :type block_extent: float
    :param compact_attribute_table: [optional] write the attribute table in a
        compact format - not compatible with Flint, but may be useful for other
        scripts using the mojadata library
    :type compact_attribute_table: bool
    '''

    def __init__(self, tile_extent=1.0, block_extent=0.1, compact_attribute_table=False, **kwargs):
        super().__init__(**kwargs)
        self._log = get_logger(self.__class__)
        self._tile_extent = tile_extent
        self._block_extent = block_extent
        self._compact_attribute_table = compact_attribute_table

    def tile(self, layers, output_path="."):
        self._skipped_layers = []
        working_path = os.path.abspath(os.curdir)
        os.makedirs(output_path, exist_ok=True)
        os.chdir(output_path)
        try:
            layers = self._remove_duplicates(layers)
            layer_config = {
                "tile_extent": self._tile_extent,
                "block_extent": self._block_extent,
                "compact_attribute_table": self._compact_attribute_table
            }

            self._log.info("Processing layers...")
            pool = self._create_pool(_pool_init, (layers, layer_config))
            for i in range(len(layers)):
                pool.apply_async(_tile_layer, (i,), callback=self._handle_tile_layer_result)

            pool.close()
            pool.join()

            self._bounding_box = layers[0]
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

def _pool_init(_layers, _config):
    global layers, config
    gdal.SetCacheMax(GDAL_MEMORY_LIMIT)
    layers = _layers
    config = _config

def _tile_layer(layer_idx):
    messages = []
    layer_name = ""
    try:
        layer = layers[layer_idx]
        layer_name = layer.name
        messages.append((logging.INFO, "Processing layer: {}".format(layer_name)))
        if layer.is_empty():
            messages.append((logging.WARNING, "Layer '{}' is empty - skipping.".format(layer_name)))
            return layer_name, False, messages

        raster_name = "{}_moja".format("".join(layer_name.split("_moja")))
        ext = os.path.splitext(layer.path)[1]
        output_raster_path = os.path.join("{}{}".format(raster_name, ext))
        shutil.copyfile(layer.path, output_raster_path)
        _write_metadata(layer, config, output_raster_path)
    except Exception as e:
        messages.append((logging.ERROR, "Error in layer '{}': {}".format(layer_name, e)))
        messages.append((logging.DEBUG, traceback.format_exc()))
        return layer_name, False, messages

    return layer_name, True, messages

def _write_native_attribute_table(path, attributes):
    layer = gdal.Open(path)
    band = layer.GetRasterBand(1)
    band.SetCategoryNames(attributes)

def _write_metadata(layer, config, output_raster_path):
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
            native_attributes = ["null" for _ in range(max((int(px) for px in layer.attribute_table)) + 1)]
            for pixel_value, attr_values in viewitems(layer.attribute_table):
                if len(attr_values) == 1:
                    attributes[pixel_value] = attr_values[0]
                    native_attributes[int(pixel_value)] = str(attr_values[0])
                else:
                    attributes[pixel_value] = dict(zip(layer.attributes, attr_values))
                    native_attributes[int(pixel_value)] = repr([str(v) for v in attr_values])

            metadata["attributes"] = attributes
            _write_native_attribute_table(output_raster_path, native_attributes)

    metadata_path = "{}.json".format(os.path.splitext(output_raster_path)[0])
    Tiler.write_json(metadata, metadata_path)
