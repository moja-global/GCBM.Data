import os
import uuid
import numpy as np
from mojadata.layer.rasterlayer import RasterLayer
from mojadata.util import gdal
from mojadata.util.gdalhelper import GDALHelper
from mojadata.config import GDAL_CREATION_OPTIONS
from mojadata.layer.layer import Layer
from mojadata import cleanup


class DummyLayer(Layer):
    '''
    Defines a dummy layer with a single value in an attribute table that matches
    the bounding box.

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

    def __init__(self, name, value, nodata_value=None, data_type=None, tags=None):
        super(self.__class__, self).__init__()
        self._name = name
        self._path = name
        self._data_type = data_type or gdal.GDT_Byte
        self._nodata_value = nodata_value or GDALHelper.best_nodata_value(self._data_type)
        self._tags = tags
        self._attributes = [name]
        self._attribute_table = {1: [value]}

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

    def _rasterize(self, srs, min_pixel_size, block_extent, requested_pixel_size=None,
                   data_type=None, bounds=None, preserve_temp_files=False, memory_limit=None,
                   **kwargs):
        tmp_dir = "_".join((os.path.abspath(self._name), str(uuid.uuid1())[:4]))

        if not os.path.exists(tmp_dir):
            os.makedirs(tmp_dir)

        if not preserve_temp_files:
            cleanup.register_temp_dir(tmp_dir)

        pixel_size = requested_pixel_size or min_pixel_size
        ulx, lry, lrx, uly = bounds
        width_px = int(abs(lrx - ulx) // pixel_size)
        height_px = int(abs(lry - uly) // pixel_size)

        output_path = os.path.join(tmp_dir, "{}.tif".format(self._name))
        driver = gdal.GetDriverByName("GTiff")
        dummy_raster = driver.Create(
            output_path, width_px, height_px, 1,
            self._data_type, GDAL_CREATION_OPTIONS)

        dummy_raster.SetProjection(srs)
        dummy_raster.SetGeoTransform((ulx, pixel_size, 0, uly, 0, -pixel_size))
        band = dummy_raster.GetRasterBand(1)
        band.SetNoDataValue(self._nodata_value)
        band.WriteArray(np.ones((height_px, width_px)), 0, 0)
        band.FlushCache()
        band = None
        dummy_raster = None

        return RasterLayer(output_path, self._attributes, self._attribute_table, tags=self._tags,
                           name=self._name)
