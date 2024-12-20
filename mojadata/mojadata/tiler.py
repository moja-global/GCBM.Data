import logging
import simplejson as json
from ftfy import guess_bytes
from collections import OrderedDict
from multiprocessing import Pool
from mojadata import config
import numpy as np

class Tiler(object):
    '''
    Base class for tilers which convert raw spatial data into formats supported
    by the Flint platform.
    '''

    def __init__(self, workers=None):
        self._workers = workers
        if workers:
            config.refresh(workers)

    def tile(self, items):
        '''
        Processes a list of layers (or stacks of layers) into a format supported
        by the Flint platform.
        '''
        raise NotImplementedError()

    def _get_study_area_info(self):
        study_area_info = {
            "pixel_size": self._bounding_box.pixel_size
        }

        for i, tile in enumerate(self._bounding_box.tiles(self._tile_extent, self._block_extent)):
            if tile is None:
                break
            
            if i == 0:
                study_area_info["tile_size"] = self._tile_extent
                study_area_info["block_size"] = self._block_extent
                study_area_info["tiles"] = []

            study_area_info["tiles"].append(OrderedDict(zip(
                ["x", "y", "index"],
                [int(loc) for loc in tile.name.split("_")] + [tile.index])))

        return study_area_info

    def _create_pool(self, initializer=None, init_args=None):
        workers = self._workers or config.PROCESS_POOL_SIZE
        logging.info("Creating pool with {} workers.".format(workers))
        return Pool(workers, initializer, init_args)

    @staticmethod
    def write_json(obj, path):
        json_content = json.dumps(obj, indent=4, ensure_ascii=False, default=Tiler._serialize)
        with open(path, "w", encoding="utf8", errors="surrogateescape") as out_file:
            out_file.write(json_content)

        # Fix any unicode errors and ensure the final JSON file is UTF-8. This fixes cases where
        # a shapefile has a bad encoding along with non-ASCII characters, causing the initial
        # write to have either mangled characters or an ASCII encoding when it should be UTF-8.
        tmp_txt, _ = guess_bytes(open(path, "rb").read())
        open(path, "wb").write(tmp_txt.encode("utf8"))

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
