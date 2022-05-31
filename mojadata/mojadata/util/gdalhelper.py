import simplejson as json
from math import pow
from mojadata.util import gdal

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
        return   gdal.GDT_Float32 if allow_float and not (float(range[0]).is_integer() and float(range[1]).is_integer()) \
            else gdal.GDT_Byte    if range[0] >= GDALHelper.byte_range[0]   and range[1] <= GDALHelper.byte_range[1]     \
            else gdal.GDT_Int16   if range[0] >= GDALHelper.int16_range[0]  and range[1] <= GDALHelper.int16_range[1]    \
            else gdal.GDT_UInt16  if range[0] >= GDALHelper.uint16_range[0] and range[1] <= GDALHelper.uint16_range[1]   \
            else gdal.GDT_Int32   if range[0] >= GDALHelper.int32_range[0]  and range[1] <= GDALHelper.int32_range[1]    \
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
