class Attribute(object):
    '''
    A single attribute to extract from a vector layer.

    :param layer_name: the attribute name as it appears in the layer
    :type layer_name: str
    :param db_name: [optional] the attribute name as it should appear in the
        processed layer, if not determined elsewhere (i.e. by the layer name if
        processing a vector layer with only a single attribute)
    :type db_name: str
    :param filter: [optional] callable that takes a value for the attribute and
        returns True if the attached polygon should be included in the output or
        False if it should be considered nodata
    :type filter: callable
    :param substitutions: [optional] a table of substitutions from the original
        attribute values to replacements - if no replacement is found, the
        original is used, unless only_substitutions is set to True.
    :type substitutions: dict
    :param only_substitutions: [optional] if a substitution table is provided,
        setting this flag to True causes values not in the substitution table
        to be dropped.
    :param transform: [optional] applies a transform function to the attribute
        value being read. Function should take a single argument, the original
        value, and return the modified value. The transform is applied before
        the substitution table lookup, if applicable.
    '''

    def __init__(self, layer_name, db_name=None, filter=None, substitutions=None,
                 only_substitutions=False, transform=None):
        self._name = layer_name
        self._db_name = db_name or layer_name
        self._filter = filter
        self._substitutions = substitutions or {}
        self._only_substitutions = only_substitutions
        self._transform = transform

    @property
    def name(self):
        return self._name

    @property
    def db_name(self):
        return self._db_name

    def filter(self, value):
        '''
        Evaluates the optional filter for a particular value of the attribute.

        :param value: the attribute value to check
        :type value: any
        :returns: True if the value passes the filter and should be included,
            False if the value should be filtered out
        '''
        if self._transform and value is not None:
            value = self._transform(value)

        return self._filter(value) if self._filter else True

    def sub(self, value):
        '''
        Substitutes an attribute value with its replacement, or returns the
        original attribute value if no replacement exists in the lookup table.

        :returns: the substituted value if available, otherwise the original
        '''
        if self._transform and value is not None:
            value = self._transform(value)

        substitution = self._substitutions.get(value)
        if self._only_substitutions:
            return substitution

        return substitution if substitution is not None else value
