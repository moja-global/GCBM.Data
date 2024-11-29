import simplejson as json
import numpy as np
from math import pow
from mojadata.util import gdal
from mojadata import config

class GDALHelper(object):

    byte_range    = (0, pow(2, 8) - 1)
    int16_range   = (-pow(2, 16) / 2, pow(2, 16) / 2 - 1)
    uint16_range  = (0, pow(2, 16) - 1)
    int32_range   = (-pow(2, 32) / 2, pow(2, 32) / 2 - 1)
    uint32_range  = (0, pow(2, 32) - 1)
    float32_range = (-3.4E+38, 3.4E+38)

    type_code_lookup = {
        gdal.GDT_Byte:    "Byte",
        gdal.GDT_Int16:   "Int16",
        gdal.GDT_UInt16:  "UInt16",
        gdal.GDT_Int32:   "Int32",
        gdal.GDT_UInt32:  "UInt32",
        gdal.GDT_Float32: "Float32"
    }

    @staticmethod
    def best_fit_data_type(range, allow_float=True):
        '''
        Gets the smallest data type that a range of values will fit into.

        :param range: tuple of min, max range to fit into a data type
        '''
        return   gdal.GDT_Float32 if allow_float and not (float(range[0]).is_integer() and float(range[1]).is_integer())   \
            else gdal.GDT_Byte    if range[0] >= GDALHelper.byte_range[0]   and range[1] <= GDALHelper.byte_range[1]   - 1 \
            else gdal.GDT_Int16   if range[0] >= GDALHelper.int16_range[0]  and range[1] <= GDALHelper.int16_range[1]  - 1 \
            else gdal.GDT_UInt16  if range[0] >= GDALHelper.uint16_range[0] and range[1] <= GDALHelper.uint16_range[1] - 1 \
            else gdal.GDT_Int32   if range[0] >= GDALHelper.int32_range[0]  and range[1] <= GDALHelper.int32_range[1]  - 1 \
            else gdal.GDT_UInt32

    @staticmethod
    def best_nodata_value(data_type):
        '''
        Gets the most appropriate nodata value for a particular GDAL data type.

        :param data_type: the GDAL data type to get a nodata value for
        :type data_type: GDAL.GDT_*
        '''
        return   GDALHelper.byte_range[1]    if data_type == gdal.GDT_Byte    \
            else GDALHelper.int16_range[1]   if data_type == gdal.GDT_Int16   \
            else GDALHelper.uint16_range[1]  if data_type == gdal.GDT_UInt16  \
            else GDALHelper.int32_range[1]   if data_type == gdal.GDT_Int32   \
            else GDALHelper.uint32_range[1]  if data_type == gdal.GDT_UInt32  \
            else GDALHelper.float32_range[1] if data_type == gdal.GDT_Float32 \
            else -1

    @staticmethod
    def info(path, **kwargs):
        '''
        Workaround for a bug in the GDAL Python bindings - "nan" values cause an
        exception to be thrown with format="json" option.
        '''
        info = gdal.Info(path, format="json", deserialize=False, **kwargs).replace("nan", "0")
        return json.loads(info)

    @staticmethod
    def blank_copy(path, output_path, data_type=None, nodata_value=None, **kwargs):
        '''
        Creates a blank (all nodata) copy of the specified layer with the same projection,
        resolution, and extent.

        Arguments:
        'output_path' -- path to the new layer to create.
        
        Returns the path to the blank copy.
        '''
        driver = gdal.GetDriverByName("GTiff")

        if data_type is None:
            original_raster = gdal.Open(path)
            driver.CreateCopy(
                output_path, original_raster, strict=0,
                options=config.GDAL_CREATION_OPTIONS + ["SPARSE_OK=YES"])

            del original_raster
        else:
            gdal.Translate(
                output_path, path, outputType=data_type,
                creationOptions=config.GDAL_CREATION_OPTIONS + ["SPARSE_OK=YES"])

        new_raster = gdal.Open(output_path, gdal.GA_Update)
        band = new_raster.GetRasterBand(1)
        nodata_value = nodata_value if nodata_value is not None else band.GetNoDataValue()
        band.SetNoDataValue(nodata_value)
        for chunk in GDALHelper.chunk(path):
            x_px_start, y_px_start, x_size, y_size = chunk
            band.WriteArray(np.full((y_size, x_size), nodata_value), x_px_start, y_px_start)

    @staticmethod
    def chunk(path, chunk_size=10000, **kwargs):
        '''
        Chunks this layer up for reading or writing.

        Arguments:
        'path' -- path to the new layer to create.
        'chunk_size' -- the size of one side of a square chunk.
        
        Yields the chunk information for the raster.
        '''
        width, height = GDALHelper.info(path)["size"]

        y_chunk_starts = list(range(0, height, chunk_size))
        y_chunk_ends = [y - 1 for y in (y_chunk_starts[1:] + [height])]
        y_chunks = list(zip(y_chunk_starts, y_chunk_ends))
        
        x_chunk_starts = list(range(0, width, chunk_size))
        x_chunk_ends = [x - 1 for x in (x_chunk_starts[1:] + [width])]
        x_chunks = list(zip(x_chunk_starts, x_chunk_ends))

        for y_px_start, y_px_end in y_chunks:
            for x_px_start, x_px_end in x_chunks:
                y_size = y_px_end - y_px_start + 1
                x_size = x_px_end - x_px_start + 1

                yield (x_px_start, y_px_start, x_size, y_size)

    @staticmethod
    def read_chunked(paths, **kwargs):
        '''
        Reads the raster layers specified in `paths` in chunks, yielding the
        chunk bounds (x start, y start, x size, y size) and the layer data in a
        list in the same order as the layer paths.

        Arguments:
            'paths' -- a list of rasters to read.
        '''
        if isinstance(paths, str):
            paths = [paths]

        rasters = [gdal.Open(path) for path in paths]
        bands = [raster.GetRasterBand(1) for raster in rasters]
        is_single_raster = len(paths) == 1
        for chunk in GDALHelper.chunk(paths[0]):
            if is_single_raster:
                yield chunk, bands[0].ReadAsArray(*chunk)
            else:
                yield chunk, [band.ReadAsArray(*chunk) for band in bands]

    @staticmethod
    def calc(paths, output_path, calc_fn, **kwargs):
        '''
        Performs a user-defined calculation on a list of rasters and writes the
        result to a new file.

        Arguments:
            'paths' -- a list of rasters to perform a calculation on.
            'output_path' -- path to the output raster to create.
            'calc_fn' -- a function that takes a list of chunked data in the same
                order as the list of paths, and returns a single array of data to
                write to the output raster.
        '''
        if isinstance(paths, str):
            paths = [paths]

        GDALHelper.blank_copy(paths[0], output_path, **kwargs)
        raster = gdal.Open(output_path, gdal.GA_Update)
        band = raster.GetRasterBand(1)
        for chunk, data in GDALHelper.read_chunked(paths, **kwargs):
            band.WriteArray(calc_fn(data), *chunk[:2])
