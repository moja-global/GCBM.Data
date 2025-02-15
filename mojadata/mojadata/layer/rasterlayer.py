﻿import os
import uuid
import numpy as np
from future.utils import viewitems
from mojadata.util import gdalconst
from mojadata.util import gdal
from mojadata.util.validationhelper import ValidationHelper
from mojadata.util.gdalhelper import GDALHelper
from mojadata import config as gdal_config
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
        self._data_type = gdal.GetDataTypeByName(data_type) if isinstance(data_type, str) else data_type
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
                   data_type=None, bounds=None, preserve_temp_files=False, memory_limit=None,
                   **kwargs):
        '''
        About resampling rasters to a coarser resolution:
            - GDALWarp with "mode" resampling ignores nodata by default, i.e. a 95% nodata / 5% data
              pixel -> data pixel in resampled layer.
            - srcnodata="None" allows nodata to be considered, but then there can be more of the
              single nodata value pixels than the count of any distinct data value making up the
              resampled pixel, causing errors the other way: nodata pixels where there should be data.
            - Solution is multi-step:
                - Before resampling, create a mask layer:
                    - Start with a copy of the layer being resampled.
                    - Flatten all the non-nodata values to 1.
                    - Do a mode resample with srcnodata="None" to come up with a simple majority
                      data/nodata mask.
                - Do a "mode" resample of the original layer using the defaults, i.e. let it exclude
                  nodata from the calculation.
                - Apply the data/nodata mask to remove any extra pixels that were actually majority nodata.
        '''
        tmp_dir = "_".join((os.path.abspath(self._name), str(uuid.uuid1())[:4]))

        if not os.path.exists(tmp_dir):
            os.makedirs(tmp_dir)

        if not preserve_temp_files:
            cleanup.register_temp_dir(tmp_dir)

        original_nodata = self.nodata_value
        if original_nodata is None and self._nodata_value is not None:
            original_nodata = self._nodata_value

        nodata_mask_path = None
        if original_nodata is not None:
            flattened_path = "/vsimem/flattened_{}.tif".format(self._name)
            GDALHelper.calc(
                self._path, flattened_path, lambda d: d != original_nodata,
                data_type=gdal.GDT_Byte, nodata_value=0)

            nodata_mask_path = "/vsimem/nodata_{}.tif".format(self._name)
            gdal.Warp(nodata_mask_path, flattened_path,
                      targetAlignedPixels=True,
                      dstSRS=srs,
                      resampleAlg="mode",
                      srcNodata="None",
                      xRes=requested_pixel_size or min_pixel_size,
                      yRes=requested_pixel_size or min_pixel_size,
                      warpMemoryLimit=memory_limit or gdal_config.GDAL_MEMORY_LIMIT,
                      options=gdal_config.GDAL_WARP_OPTIONS.copy(),
                      creationOptions=gdal_config.GDAL_WARP_CREATION_OPTIONS + ["SPARSE_OK=YES"],
                      outputBounds=bounds)

        warp_path = os.path.join(tmp_dir, "warp_{}.tif".format(self._name))
        gdal.Warp(warp_path, self._path,
                  targetAlignedPixels=True,
                  dstSRS=srs,
                  resampleAlg="mode",
                  srcNodata=original_nodata,
                  xRes=requested_pixel_size or min_pixel_size,
                  yRes=requested_pixel_size or min_pixel_size,
                  warpMemoryLimit=memory_limit or gdal_config.GDAL_MEMORY_LIMIT,
                  options=gdal_config.GDAL_WARP_OPTIONS.copy(),
                  creationOptions=gdal_config.GDAL_WARP_CREATION_OPTIONS + ["SPARSE_OK=YES"],
                  outputBounds=bounds)

        if nodata_mask_path:
            masked_path = os.path.join(tmp_dir, "masked_{}.tif".format(self._name))
            GDALHelper.calc(
                [warp_path, nodata_mask_path],
                masked_path,
                lambda d: np.where(d[1] == 0, original_nodata, d[0]),
                nodata_value=original_nodata)
            
            warp_path = masked_path
        
        output_path = os.path.join(tmp_dir, "{}.tif".format(self._name))
        is_float = "Float" in self.data_type
        output_type = data_type if data_type is not None \
            else self._data_type if self._data_type is not None \
            else gdal.GDT_Float32 if is_float \
            else GDALHelper.best_fit_data_type(RasterLayer.get_min_max(warp_path))

        if self._nodata_value is None:
            self._nodata_value = GDALHelper.best_nodata_value(output_type)

        pixel_size = self._get_nearest_divisible_resolution(
            srs, min_pixel_size, requested_pixel_size, block_extent) if requested_pixel_size \
            else self._get_nearest_divisible_resolution(
                srs, min_pixel_size, RasterLayer.get_pixel_size(warp_path), block_extent)

        gdal.Warp(output_path, warp_path,
                  targetAlignedPixels=True,
                  xRes=pixel_size, yRes=pixel_size,
                  outputType=output_type,
                  dstNodata=self._nodata_value,
                  warpMemoryLimit=memory_limit or gdal_config.GDAL_MEMORY_LIMIT,
                  options=gdal_config.GDAL_WARP_OPTIONS.copy(),
                  creationOptions=gdal_config.GDAL_WARP_CREATION_OPTIONS + ["SPARSE_OK=YES"])

        self._drop_nulls(output_path)

        return RasterLayer(output_path, self._attributes, self._attribute_table,
                           date=self._date, tags=self._tags, allow_nulls=self._allow_nulls)

    def _drop_nulls(self, path):
        # If this layer has an attribute table attached, drop any pixel values
        # that have been left out of it.
        if not self._attribute_table:
            return

        tmp_path = os.path.join(os.path.dirname(path), f"{os.path.basename(path)}_drop_nulls.tiff")
        os.rename(path, tmp_path)
        keep_values = list(self._attribute_table.keys())
        GDALHelper.calc(tmp_path, path, lambda d: np.where(np.isin(d, keep_values), d, self._nodata_value))
        os.remove(tmp_path)

    def _get_nearest_divisible_resolution(self, srs, min_pixel_size, requested_pixel_size, block_extent):
        if srs != 4326:
            return requested_pixel_size

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
