import io
import simplejson as json
from ftfy import fix_encoding
from collections import OrderedDict
from multiprocessing import Pool
from mojadata.config import *
import numpy as np

class Tiler(object):
    '''
    Base class for tilers which convert raw spatial data into formats supported
    by the Flint platform.
    '''

    def tile(self, items):
        '''
        Processes a list of layers (or stacks of layers) into a format supported
        by the Flint platform.
        '''
        raise NotImplementedError()

    def _get_study_area_info(self):
        study_area_info = {
            "tile_size": self._tile_extent,
            "block_size": self._block_extent,
            "tiles": []
        }

        for i, tile in enumerate(self._bounding_box.tiles(self._tile_extent, self._block_extent)):
            study_area_info["tiles"].append(OrderedDict(zip(
                ["x", "y", "index"],
                [int(loc) for loc in tile.name.split("_")] + [tile.index])))

            if i == 0:
                study_area_info["pixel_size"] = tile.pixel_size

        return study_area_info

    def _create_pool(self, initializer=None, init_args=None):
        return Pool(PROCESS_POOL_SIZE, initializer, init_args)

    @staticmethod
    def write_json(obj, path):
        json_content = json.dumps(obj, indent=4, ensure_ascii=False, default=Tiler._serialize)
        with open(path, "w", encoding="utf8", errors="surrogateescape") as out_file:
            out_file.write(json_content)

        # Fix any unicode errors and ensure the final JSON file is UTF-8. This fixes cases where
        # a shapefile has a bad encoding along with non-ASCII characters, causing the initial
        # write to have either mangled characters or an ASCII encoding when it should be UTF-8.
        tmp_txt = list(fix_encoding(open(path, "r").read()))
        open(path, "w", encoding="utf8").writelines(tmp_txt)

    @staticmethod
    def _serialize(obj):
        '''
        Adds JSON serialization support for non-standard objects such as numpy numeric types.
        '''
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            raise TypeError("{} is not JSON serializable.".format(type(obj)))
