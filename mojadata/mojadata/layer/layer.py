import math
import logging
from mojadata.util import gdalconst
from mojadata.util.gdalhelper import GDALHelper
from mojadata.util import gdal
from mojadata.tile import Tile

class Layer(object):
    '''
    Defines a spatial layer to convert to the Flint tile/block/cell format.
    '''

    def __init__(self):
        self._messages = []

    @property
    def metadata(self):
        '''Metadata describing the layer for use with config files.'''
        meta = {"name": self.name,
                "type": self.__class__.__name__}

        if self.tags:
            meta["tags"] = self.tags

        return meta

    @property
    def name(self):
        '''The name of the spatial layer.'''
        raise NotImplementedError()

    @property
    def tags(self):
        '''Metadata tags describing the layer.'''
        raise NotImplementedError()

    @property
    def path(self):
        '''The path of the spatial layer.'''
        raise NotImplementedError()

    @path.setter
    def path(self, value):
        raise NotImplementedError()

    @property
    def attributes(self):
        '''The attribute names in the layer.'''
        raise NotImplementedError()

    @property
    def attribute_table(self):
        '''The dictionary of pixel value to attribute values in the layer.'''
        raise NotImplementedError()

    @property
    def date(self):
        '''The date the layer applies to, if applicable.'''
        raise NotImplementedError()

    @property
    def pixel_size(self):
        '''The pixel size in the current projection units.'''
        info = GDALHelper.info(self.path)
        return abs(info["geoTransform"][1])

    @property
    def data_type(self):
        '''The layer data type.'''
        info = GDALHelper.info(self.path)
        return info["bands"][0]["type"]

    @property
    def nodata_value(self):
        '''The layer nodata value in its correct python type.'''
        info = GDALHelper.info(self.path)
        value = info["bands"][0]["noDataValue"]
        dt = str(self.data_type).lower()
        if dt == "float32" or dt == "float" or dt == str(gdal.GDT_Float32):
            return float(value)
        else:
            return int(value)

    @property
    def messages(self):
        '''Messages generated during the processing of the layer.'''
        return [msg for msg in self._messages]

    @messages.setter
    def messages(self, value):
        self._messages = [msg for msg in value]

    def add_message(self, msg):
        '''Adds a message to the layer about some aspect of its processing.'''
        self._messages.append(msg)

    def is_empty(self):
        '''
        :returns: whether or not the layer is empty, if the layer subclass has
            implemented this method - otherwise the layer is always considered
            to have some data
        '''
        return False

    def as_raster_layer(self, *args, **kwargs):
        '''
        Rasterizes a layer with specified settings.

        :param srs: the destination projection
        :type srs: :class:`.osr.SpatialReference`
        :param min_pixel_size: the minimum pixel size, in units specified by :param srs:
        :type min_pixel_size: float
        :param block_extent: the size of a block, in units specified by :param srs:
        :type block_extent: float
        :param requested_pixel_size: [optional] the requested pixel size; the size
            actually used will be the next closest pixel size divisible by
            :param min_pixel_size:
        :type requested_pixel_size: float
        :param data_type: [optional] the data type to use; auto-detected if unspecified
        :type data_type: gdal.GDT_*
        :param bounds: [optional] the spatial extent to rasterize to, in the
            coordinate system specified by :param srs:
        :type bounds: 4-tuple of float:
            upper-left x, lower-right y, lower-right x, upper-left y
        :param preserve_temp_files: [optional] keep temp files created during
            processing - default is to delete them
        :type preserve_temp_files: bool
        '''
        gdal.PushErrorHandler(self._gdal_error_handler)
        try:
            result = self._rasterize(*args, **kwargs)
            return result if result and not result.is_empty() else None, self.messages
        except Exception as e:
            self.add_message((logging.ERROR, str(e)))
            return None, self.messages
        finally:
            gdal.PopErrorHandler()

    def _rasterize(self, srs, min_pixel_size, block_extent, requested_pixel_size=None,
                   data_type=None, bounds=None, preserve_temp_files=False):
        raise NotImplementedError

    def tiles(self, tile_extent, block_extent):
        '''
        Iterates through the tiles covered by the layer's spatial extent. The
        landscape is divided evenly into tiles, then further into blocks, which
        are the units of processing in the Flint platform.

        :param tile_extent: the length of one side of a tile, in the layer's
            coordinate system
        :type tile_extent: float
        :param block_extent: the length of one side of a block, in the layer's
            coordinate system
        '''
        ds = gdal.Open(self.path, gdalconst.GA_ReadOnly)
        try:
            info = GDALHelper.info(ds)
            transform = ds.GetGeoTransform()
            pixel_size = abs(transform[1])
            origin = (transform[0], transform[3])
            bounds = info["cornerCoordinates"]
            y_min = int(math.floor(bounds["lowerRight"][1]))
            y_max = int(math.ceil(bounds["upperLeft"][1]))
            x_min = int(math.floor(bounds["upperLeft"][0]))
            x_max = int(math.ceil(bounds["lowerRight"][0]))
            for x in range(x_min, x_max):
                for y in range(y_min, y_max):
                    yield Tile(x, y, origin, pixel_size, tile_extent, block_extent)
        except:
            raise
        finally:
            ds = None

    def _gdal_error_handler(self, err_class, err_num, err_msg):
        error_types = {
            gdal.CE_None:    "None",
            gdal.CE_Debug:   "Debug",
            gdal.CE_Warning: "Warning",
            gdal.CE_Failure: "Failure",
            gdal.CE_Fatal:   "Fatal"
        }

        err_msg = err_msg.replace("\n", " ")
        err_class = error_types.get(err_class, "None")
        self._messages.append((logging.DEBUG, ": ".join((err_class, err_msg))))
