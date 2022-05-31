from mojadata.layer.stacklayer import StackLayer

class RegularStackLayer(StackLayer):
    '''
    A stack of layers to process into a single Flint-format timeseries. The
    series of input layers must be contiguous and sorted in ascending date
    order.

    :param name: the name of the timeseries layer
    :type name: str
    :param layers: the layers that compose the timeseries
    :type layers: list of :class:`.Layer`
    :param requested_pixel_size: the pixel size that all layers in the stack
        will be resampled to
    :type requested_pixel_size: float
    :param data_type: the data type of the stack
    :type data_type: gdal.GDT_*
    :param years: the number of years in the timeseries
    :type years: int
    :param steps_per_year: the number of timesteps of data per year - for
        example, a list of 100 layers could cover a 10-year period with 10
        steps per year
    :type steps_per_year: int
    '''

    def __init__(self, years, steps_per_year, **kwargs):
        super(self.__class__, self).__init__(**kwargs)
        self._years = years
        self._steps_per_year = steps_per_year

    @property
    def metadata(self):
        meta = super(self.__class__, self).metadata
        meta.update({
            "nLayers"      : self._years,
            "nStepsPerYear": self._steps_per_year,
        })

        return meta
