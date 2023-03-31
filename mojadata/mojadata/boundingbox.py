import os
import shutil
import math
from mojadata.util import osr
from mojadata.util import gdal
from mojadata.util.gdalhelper import GDALHelper
from mojadata.util.rasterclipper import clip_raster
from mojadata.util.rasterclipper import shrink_to_data
from mojadata.config import (
    TILER_MEMORY_LIMIT,
    GDAL_MEMORY_LIMIT,
    GDAL_WARP_OPTIONS,
    GDAL_WARP_CREATION_OPTIONS
)
from mojadata import cleanup


class BoundingBox(object):
    '''
    Defines the study area, or bounding box, that the tiler will operate on. All
    layers will be cropped to the geographic extent of the bounding box.

    :param layer: the layer to use as the bounding box
    :type layer: :class:`.Layer`
    :param epsg: the EPSG code to use for the bounding box projection, which
        becomes the output projection of all the layers being processed - note
        that currently only EPSG 4326 (WGS84 in degrees) is supported by the
        Flint platform
    :type epsg: int
    :param pixel_size: the output pixel size, in the units of the projection
        specified by :param epsg:
    :type pixel_size: float
    :param preprocessed: indicates that the bounding box layer has already been
        reprojected, rasterized, and resampled; i.e. the bounding box layer is
        the raster created by a previous run of the tiler and no work needs to
        be performed
    :type preprocessed: bool
    '''

    def __init__(self, layer, epsg=4326, pixel_size=0.00025, preprocessed=False, shrink_to_data=False):
        self._info = None
        self._srs = None
        self._layer = layer
        self._initialized = preprocessed
        self._epsg = epsg
        self._pixel_size = pixel_size
        self._shrink_to_data = shrink_to_data
        if preprocessed:
            self._pixel_size = self.info["geoTransform"][1]

    @property
    def pixel_size(self):
        return self._pixel_size

    @property
    def info(self):
        '''
        Gets the GDAL info for the bounding box layer, loading it if needed the
        first time.
        '''
        if not self._info: self._load_stats()
        return self._info

    @property
    def srs(self):
        '''
        Gets the GDAL SRS for the bounding box layer, loading it if needed the
        first time.
        '''
        if not self._srs: self._load_stats()
        return self._srs

    def init(self):
        if not self._initialized:
            self._process_bounding_box()
            self._initialized = True

    def tiles(self, tile_extent, block_extent):
        '''
        Iterates through the tiles in the bounding box.

        :returns: :class:`.Tile` iterator
        '''
        for tile in self._layer.tiles(tile_extent, block_extent):
            yield tile

    def normalize(self, layer, block_extent, requested_pixel_size=None, data_type=None):
        '''
        Processes a layer to conform to the bounding box: projection, pixel size,
        spatial extent.

        :param layer: the layer to process
        :type layer: :class:`.Layer`
        :param block_extent: the size of one side of a :class:`.Block`, in units
            defined by the bounding box projection
        :type block_extent: float
        :param requested_pixel_size: [optional] the requested pixel size for the
            layer; by default it will be the next nearest multiple of the bounding
            box resolution
        :type requested_pixel_size: float
        :param data_type: [optional] the requested data type for the layer; by
            default, the tiler will detect the most appropriate data type
        '''
        bounds = (self.info["cornerCoordinates"]["upperLeft"][0],
                  self.info["cornerCoordinates"]["lowerRight"][1],
                  self.info["cornerCoordinates"]["lowerRight"][0],
                  self.info["cornerCoordinates"]["upperLeft"][1])

        result, messages = layer.as_raster_layer(
            self.srs, self._pixel_size, block_extent, requested_pixel_size,
            data_type, bounds)

        if not result:
            return None, messages

        layer_path, ext = os.path.splitext(result.path)
        tmp_path = "{}_tmp{}".format(layer_path, ext)
        cleanup.register_temp_file(tmp_path)
        self._warp(result.path, tmp_path, result.pixel_size)
        result.path = tmp_path

        if requested_pixel_size:
            # Clip the target layer by the nodata pixels in the bounding box.
            tmp_path = "{}_clip{}".format(layer_path, ext)
            cleanup.register_temp_file(tmp_path)
            clip_raster(self._layer, result, tmp_path)

        output_path = "{}_moja.tiff".format(os.path.basename(layer_path))
        self._pad(tmp_path, output_path, result.pixel_size)
        result.path = output_path

        return result, messages

    def _load_stats(self):
        bbox = gdal.Open(self._layer.path)
        self._info = GDALHelper.info(bbox)
        self._srs = bbox.GetProjection()

    def _process_bounding_box(self):
        dest_srs = osr.SpatialReference()
        dest_srs.ImportFromEPSG(self._epsg)
        self._layer, messages = self._layer.as_raster_layer(dest_srs, self._pixel_size, 0.1)
        if not self._layer:
            raise RuntimeError("Error processing bounding box: {}".format(
                os.linesep.join((m[1] for m in messages))))

        layer_path, ext = os.path.splitext(self._layer.path)
        tmp_dir = os.path.basename(self._layer.path)
        cleanup.register_temp_dir(tmp_dir)

        gdal.SetCacheMax(TILER_MEMORY_LIMIT)

        if self._shrink_to_data:
            shrink_path = "{}_bbox_shrink{}".format(layer_path, ext)
            shrink_to_data(self._layer, shrink_path)
            self._layer.path = shrink_path

        # Go through the same warping process as the rest of the layers to
        # ensure the same raster dimensions; sometimes off by 1 without this.
        final_bbox_path = os.path.abspath("bounding_box{}".format(ext))
        self._warp(self._layer.path, final_bbox_path, self._pixel_size)
        self._layer.path = final_bbox_path

        gdal.SetCacheMax(GDAL_MEMORY_LIMIT)

    def _pad(self, in_path, out_path, pixel_size):
        info = GDALHelper.info(in_path)
        bounds = info["cornerCoordinates"]
        gdal.Warp(out_path, in_path,
                  xRes=pixel_size, yRes=pixel_size,
                  outputBounds=(math.floor(bounds["upperLeft"][0]),
                                math.floor(bounds["lowerRight"][1]),
                                math.ceil(bounds["lowerRight"][0]),
                                math.ceil(bounds["upperLeft"][1])),
                  warpMemoryLimit=GDAL_MEMORY_LIMIT,
                  options=GDAL_WARP_OPTIONS.copy(),
                  creationOptions=GDAL_WARP_CREATION_OPTIONS)

    def _warp(self, in_path, out_path, pixel_size):
        gdal.Warp(out_path, in_path,
                  dstSRS=self.srs,
                  xRes=pixel_size, yRes=pixel_size,
                  outputBounds=(self.info["cornerCoordinates"]["upperLeft"][0],
                                self.info["cornerCoordinates"]["lowerRight"][1],
                                self.info["cornerCoordinates"]["lowerRight"][0],
                                self.info["cornerCoordinates"]["upperLeft"][1]),
                  targetAlignedPixels=True,
                  warpMemoryLimit=GDAL_MEMORY_LIMIT,
                  options=GDAL_WARP_OPTIONS.copy(),
                  creationOptions=GDAL_WARP_CREATION_OPTIONS)
