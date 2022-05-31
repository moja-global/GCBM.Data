class StackLayer(object):
    '''
    A stack of layers to process into a single Flint-format timeseries.

    :param name: the name of the timeseries layer
    :type name: str
    :param layers: the layers that compose the timeseries
    :type layers: list of :class:`.Layer`
    :param requested_pixel_size: the pixel size that all layers in the stack
        will be resampled to
    :type requested_pixel_size: float
    :param data_type: the data type of the stack
    :type data_type: gdal.GDT_*
    '''

    def __init__(self, name, layers, requested_pixel_size, data_type, tags=None):
        self._name = name
        self._layers = layers
        self._requested_pixel_size = requested_pixel_size
        self._data_type = data_type
        self._tags = tags or []

    @property
    def name(self):
        return self._name

    @property
    def tags(self):
        return self._tags

    @property
    def layers(self):
        return self._layers

    @property
    def requested_pixel_size(self):
        return self._requested_pixel_size

    @property
    def data_type(self):
        return self._data_type

    @property
    def metadata(self):
        '''Metadata describing the layer for use with config files.'''
        meta = {"name": self.name,
                "type": self.__class__.__name__}

        if self.tags:
            meta["tags"] = self.tags

        return meta
