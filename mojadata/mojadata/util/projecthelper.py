import os
import shutil
import simplejson as json
from collections import OrderedDict
from glob import glob
from mojadata.tiler import Tiler
from mojadata.layer.rasterlayer import RasterLayer
from mojadata.util import gdal
from mojadata.config import *

def get_max_extent(study_areas):
    all_tiles = []
    for study_area_file in study_areas:
        all_tiles.extend(json.load(open(study_area_file, "r"))["tiles"])

    x_min = min((tile["x"] for tile in all_tiles))
    x_max = max((tile["x"] for tile in all_tiles)) + 1
    y_min = min((tile["y"] for tile in all_tiles))
    y_max = max((tile["y"] for tile in all_tiles)) - 1

    return (x_min, y_max, x_max, y_min)

def align_study_areas(*study_areas, output_path):
    max_extent = get_max_extent(study_areas)
    for study_area_file in study_areas:
        original_study_area_dir = os.path.dirname(os.path.abspath(study_area_file))
        study_area_output_path = os.path.join(
            output_path,
            original_study_area_dir.replace("\\", "_").replace(":", "_"))
        
        os.makedirs(study_area_output_path, exist_ok=True)
        study_area_data = json.load(open(study_area_file, "r"))
        for layer_name in (layer["name"] for layer in study_area_data["layers"]):
            input_layer_metadata = os.path.join(original_study_area_dir, f"{layer_name}_moja.json")
            output_layer_metadata = os.path.join(study_area_output_path, os.path.basename(input_layer_metadata))
            shutil.copyfile(input_layer_metadata, output_layer_metadata)

            input_layer_file = glob(os.path.join(original_study_area_dir, f"{layer_name}_moja.tif*"))[0]
            output_layer_file = os.path.join(study_area_output_path, os.path.basename(input_layer_file))
            gdal.Warp(output_layer_file, input_layer_file, outputBounds=max_extent,
                      xRes=study_area_data["pixel_size"], yRes=study_area_data["pixel_size"],
                      options=GDAL_WARP_OPTIONS, creationOptions=GDAL_WARP_CREATION_OPTIONS)
        
        any_new_layer = RasterLayer(glob(os.path.join(study_area_output_path, "*.tif*"))[0])
        study_area_data["tiles"] = []

        for tile in any_new_layer.tiles(study_area_data["tile_size"], study_area_data["block_size"]):
            study_area_data["tiles"].append(OrderedDict(zip(
                ["x", "y", "index"],
                [int(loc) for loc in tile.name.split("_")] + [tile.index])))

        Tiler.write_json(study_area_data, os.path.join(study_area_output_path, "study_area.json"))
