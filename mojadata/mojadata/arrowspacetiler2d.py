import os
import logging
import traceback
import json
from ftfy import fix_encoding
from pathlib import Path
from tempfile import TemporaryDirectory
from pandas import DataFrame
from future.utils import viewitems
from arrow_space.input.raster_input_layer import RasterInputLayer
from arrow_space.input.raster_input_layer import RasterInputSource
from arrow_space.input.attribute_table_reader import InMemoryAttributeTableReader
from arrow_space.input.input_layer_collection import InputLayerCollection
from arrow_space.flattened_coordinate_dataset import create as create_arrowspace_dataset
from mojadata.util.log import get_logger
from mojadata.util import gdal
from mojadata.tiler import Tiler
from mojadata.cleanup import cleanup
from mojadata import config as gdal_config

class ArrowspaceTiler2D(Tiler):
    '''
    Processes layers into an arrow-space dataset.

    :param bounding_box: the bounding box that defines the study area and other
        characteristics of the output
    :type bounding_box: :class:`.BoundingBox`
    '''

    def __init__(self, bounding_box, **kwargs):
        super().__init__(**kwargs)
        self._log = get_logger(self.__class__)
        self._bounding_box = bounding_box

    def tile(self, layers, output_path="."):
        working_path = os.path.abspath(os.curdir)
        os.makedirs(output_path, exist_ok=True)
        with TemporaryDirectory(dir=output_path) as working_temp:
            os.chdir(working_temp)
            try:
                tiled_layers = {}
                with cleanup():
                    self._bounding_box.init()
                    layers = self._remove_duplicates(layers)

                    self._log.info("Processing layers...")
                    pool = self._create_pool(_pool_init, (self._bounding_box, layers))
                    for i in range(len(layers)):
                        pool.apply_async(
                            _tile_layer, (i,),
                            callback=lambda result: self._handle_tile_layer_result(tiled_layers, result))

                    pool.close()
                    pool.join()

                arrowspace_layers = InputLayerCollection([
                    RasterInputLayer(
                        layer.name,
                        [RasterInputSource(path=f"{layer.name}_moja.tiff")],
                        InMemoryAttributeTableReader(tiled_layers[layer.name]),
                        layer.tags
                    ) for layer in layers if layer.name in tiled_layers
                ])
            
                dataset = create_arrowspace_dataset(
                    arrowspace_layers, "inventory", "local_storage",
                    os.path.join("..", "inventory.arrowspace"), {})
            
                return dataset
            finally:
                os.chdir(working_path)

    def _handle_tile_layer_result(self, tiled_layers, result):
        layer_name, attribute_table, success, messages = result
        if success:
            tiled_layers[layer_name] = attribute_table

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

def _pool_init(_bounding_box, _layers):
    global bbox, layers
    gdal.SetCacheMax(gdal_config.GDAL_MEMORY_LIMIT)
    bbox = _bounding_box
    layers = _layers

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
                return layer_name, None, False, messages

            layer, layer_messages = bbox.normalize(
                layer,
                bbox.pixel_size)

            messages += layer_messages

            if not layer or layer.is_empty():
                messages.append((logging.WARNING, "Layer '{}' is empty - skipping.".format(layer_name)))
                return layer_name, None, False, messages
    except Exception as e:
        messages.append((logging.ERROR, "Error in layer '{}': {}".format(layer_name, e)))
        messages.append((logging.DEBUG, traceback.format_exc()))
        return layer_name, None, False, messages

    return layer_name, _build_attribute_table(layer), True, messages

def _fix_unicode(_dict):
    # Fix any unicode errors and ensure the final attribute values are UTF-8. 
    # This fixes cases where a shapefile has a bad encoding along with non-ASCII
    # characters, causing the attribute values to have either mangled characters
    # or an ASCII encoding when it should be UTF-8.
    with TemporaryDirectory() as tmp:
        tmp_path = str(Path(tmp).joinpath("attributes.json"))
        Tiler.write_json(_dict, tmp_path)
        return json.loads(open(tmp_path, encoding="utf8").read())

def _build_attribute_table(layer):
    if layer.attribute_table:
        attribute_data = {}
        for pixel_value, attr_values in viewitems(layer.attribute_table):
            if len(attr_values) == 1:
                attribute_data[pixel_value] = attr_values[0]
            else:
                attribute_data[pixel_value] = dict(zip(layer.attributes, attr_values))

        attribute_data = _fix_unicode(attribute_data)

        rows = []
        for att_id, att_value in attribute_data.items():
            row = {"id": int(att_id)}
            if isinstance(att_value, dict):
                row.update(att_value)
            else:
                row.update({"value": att_value})
            
            rows.append(row)

        return DataFrame(rows)
