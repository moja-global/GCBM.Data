import os
import uuid
from future.utils import viewitems
from mojadata.util import gdalconst
from mojadata.util import gdal
from mojadata.util.validationhelper import ValidationHelper
from mojadata.util.gdalhelper import GDALHelper
from mojadata.config import (
    GDAL_MEMORY_LIMIT,
    GDAL_WARP_OPTIONS,
    GDAL_WARP_CREATION_OPTIONS
)
from mojadata.layer.layer import Layer
from mojadata import cleanup


class RasterLayer(Layer):
    '''
    Defines a raster layer to be processed into the Flint tile/block/cell format.
    Can either be converted with the values as-is, or with an attribute table
    for interpreting the existing pixel values using :param attributes: to define
    the attribute names, and :param attribute_table: to define the pixel value to
    attribute value mappings.

    :param path: path to the input raster layer
    :type path: str
    :param attributes: [optional] attribute names to include in the output layer
    :type attributes: list of str
    :param attribute_table: [optional] table of pixel values to attribute values
    :type attribute_table: dict of int to list of str
    :param nodata_value: [optional] override the layer's nodata value
    :type nodata_value: any value that fits within the layer's data type
    :param data_type: [optional] override the layer's data type
    :type data_type: gdal.GDT_*
    :param date: [optional] the date the layer applies to - mainly for use with
        :class:`.DiscreteStackLayer`
    :type date: :class:`.date`
    :param tags: [optional] metadata tags describing the layer
    :type tags: list of str
    :param name: the name of the layer
    :type name: str
    :param allow_nulls: [optional] allow null values in the attribute table
    :type allow_nulls: bool
    '''

    def __init__(self, path, attributes=None, attribute_table=None,
                 nodata_value=None, data_type=None, date=None, tags=None,
                 name=None, allow_nulls=False):
        super(self.__class__, self).__init__()
        ValidationHelper.require_path(path)
        self._name = name or os.path.splitext(os.path.basename(path))[0]
        self._path = os.path.abspath(path)
        self._attributes = attributes or []
        self._nodata_value = nodata_value
        self._data_type = data_type
        self._date = date
        self._tags = tags or []
        self._allow_nulls = allow_nulls
        self._attribute_table = (attribute_table or {}) if allow_nulls else {
            k: v for k, v in viewitems(attribute_table)
            if ValidationHelper.no_empty_values(v)
        } if attribute_table else {}

    @property
    def name(self):
        return self._name

    @property
    def tags(self):
        return self._tags

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, value):
        self._path = value

    @property
    def attributes(self):
        return self._attributes

    @property
    def attribute_table(self):
        return self._attribute_table

    @property
    def date(self):
        return self._date

    def is_empty(self):
        return RasterLayer.is_empty_layer(self._path)

    def _rasterize(self, srs, min_pixel_size, block_extent, requested_pixel_size=None,
                   data_type=None, bounds=None, preserve_temp_files=False):
        tmp_dir = "_".join((os.path.abspath(self._name), str(uuid.uuid1())[:4]))

        if not os.path.exists(tmp_dir):
            os.makedirs(tmp_dir)

        if not preserve_temp_files:
            cleanup.register_temp_dir(tmp_dir)

        warp_path = os.path.join(tmp_dir, "warp_{}.tif".format(self._name))
        gdal.Warp(warp_path, self._path,
                  targetAlignedPixels=True,
                  multithread=True,
                  dstSRS=srs,
                  xRes=requested_pixel_size or min_pixel_size,
                  yRes=requested_pixel_size or min_pixel_size,
                  warpMemoryLimit=GDAL_MEMORY_LIMIT,
                  options=GDAL_WARP_OPTIONS,
                  creationOptions=GDAL_WARP_CREATION_OPTIONS,
                  outputBounds=bounds)

        output_path = os.path.join(tmp_dir, "{}.tif".format(self._name))
        is_float = "Float" in self.data_type
        output_type = data_type if data_type is not None \
            else self._data_type if self._data_type is not None \
            else gdal.GDT_Float32 if is_float \
            else GDALHelper.best_fit_data_type(RasterLayer.get_min_max(warp_path))

        if self._nodata_value is None:
            self._nodata_value = GDALHelper.best_nodata_value(output_type)

        pixel_size = self._get_nearest_divisible_resolution(
            min_pixel_size, requested_pixel_size, block_extent) if requested_pixel_size \
            else self._get_nearest_divisible_resolution(
                min_pixel_size, RasterLayer.get_pixel_size(warp_path), block_extent)

        gdal.Warp(output_path, warp_path,
                  targetAlignedPixels=True,
                  multithread=True,
                  xRes=pixel_size, yRes=pixel_size,
                  outputType=output_type,
                  dstNodata=self._nodata_value,
                  warpMemoryLimit=GDAL_MEMORY_LIMIT,
                  options=GDAL_WARP_OPTIONS,
                  creationOptions=GDAL_WARP_CREATION_OPTIONS)

        return RasterLayer(output_path, self._attributes, self._attribute_table,
                           date=self._date, tags=self._tags, allow_nulls=self._allow_nulls)

    def _get_nearest_divisible_resolution(self, min_pixel_size, requested_pixel_size, block_extent):
        nearest_block_divisible_size = \
            min_pixel_size * round(min_pixel_size / requested_pixel_size) \
            if requested_pixel_size > min_pixel_size \
            else min_pixel_size

        return nearest_block_divisible_size \
            if nearest_block_divisible_size < block_extent \
            else block_extent

    @staticmethod
    def is_empty_layer(raster_path):
        if not os.path.exists(raster_path):
            return True

        ds = gdal.Open(raster_path, gdalconst.GA_ReadOnly)
        if not ds:
            return True

        try:
            hist = ds.GetRasterBand(1).GetHistogram(approx_ok=False, include_out_of_range=True)
            return hist is None or not any(hist)
        except:
            return True
        finally:
            ds = None

    @staticmethod
    def get_min_max(raster_path):
        ValidationHelper.require_path(raster_path)
        info = None
        try:
            info = GDALHelper.info(raster_path, computeMinMax=True)
        except:
            pass

        if not info or "computedMin" not in info["bands"][0]:
            return (0, 0)

        return (info["bands"][0]["computedMin"], info["bands"][0]["computedMax"])

    @staticmethod
    def get_pixel_size(raster_path):
        info = GDALHelper.info(raster_path)
        return abs(info["geoTransform"][1])
