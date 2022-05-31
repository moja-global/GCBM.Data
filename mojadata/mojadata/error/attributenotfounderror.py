class AttributeNotFoundError(Exception):

    def __init__(self, layer_name, attr_name, *args, **kwargs):
        super(self.__class__, self).__init__(args, kwargs)
        self.layer_name = layer_name
        self.attr_name = attr_name

    def __str__(self):
        return "Attribute '{}' not found in layer '{}'".format(
            self.attr_name, self.layer_name)
