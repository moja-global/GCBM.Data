from mojadata.layer.stacklayer import StackLayer

class DiscreteStackLayer(StackLayer):
    '''
    A stack of layers to process into a single Flint-format timeseries which
    behaves like a series of date/value pairs, where values can be retrieved by
    exact date or nearest date. The series of input layers can be in any order,
    where each layer in the series is tagged with the date it applies to. All
    layers must be at the same temporal resolution - for example, if a layer
    applies to a particular day, it is not valid to include a layer that applies
    to an entire month.

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

    def __init__(self, **kwargs):
        super(self.__class__, self).__init__(**kwargs)

    @property
    def metadata(self):
        meta = super(self.__class__, self).metadata
        meta.update({
            "dates": [str(layer.date) for layer in self.layers]
        })

        return meta
