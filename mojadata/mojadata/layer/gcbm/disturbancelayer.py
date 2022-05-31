import logging
from future.utils import viewitems
from mojadata.layer.layer import Layer
from mojadata.layer.rasterlayer import RasterLayer
from mojadata.layer.attribute import Attribute


class DisturbanceLayer(Layer):
    '''
    Represents a disturbance layer to tile.

    :param transition_rule_manager: a transition rule manager instance to record
        transition rule information in - see :class:`._TransitionRuleManager`
        for details about obtaining a rule manager instance
    :type transition_rule_manager: :class:`._TransitionRuleManager`
    :param lyr: the data source for the disturbance layer
    :type lyr: :class:`.Layer`
    :param year: the attribute containing the disturbance year, or a single
        explicitly provided year
    :type year: :class:`.Attribute` or int
    :param disturbance_type: the attribute containing the disturbance type name,
        or a single explicitly provided disturbance type name
    :type disturbance_type: :class:`.Attribute` or str
    :param transition: [optional] the transition rule definition for the
        disturbance layer - no transition/model default if unspecified
    :type transition: :class:`.TransitionRule`
    :param tags: [optional] list of tag strings providing extra metadata about
        the disturbance layer
    :type tags: list of `str`
    :param conditions: [optional] list of conditions that must all be met in order for
        the disturbance to be applied. Conditions are specified in the format:
            ["<variable name>", "<comparison>", <target>], i.e.:
            ["age", ">=", 40]
    :type conditions: list of 3-element lists
    '''

    def __init__(self, transition_rule_manager, lyr, year, disturbance_type,
                 transition=None, tags=None, conditions=None):
        super(self.__class__, self).__init__()
        self._transition_rule_manager = transition_rule_manager
        self._layer = lyr
        self._year = year
        self._disturbance_type = disturbance_type
        self._transition = transition
        self._tags = ["disturbance"] + (tags or [])
        self._metadata_attributes = []
        self._conditions = conditions
        self._attributes = ["year", "disturbance_type"]

        if transition:
            self._attributes.append("transition")

        if conditions:
            self._attributes.append("conditions")

    @property
    def name(self):
        return self._layer.name

    @property
    def tags(self):
        return self._tags

    @property
    def name(self):
        return self._layer.name

    @property
    def path(self):
        return self._layer.path

    @path.setter
    def path(self, value):
        self._layer.path = value

    @property
    def attributes(self):
        return self._attributes + self._metadata_attributes

    @property
    def attribute_table(self):
        attr_table = {}
        for pixel_value, attr_values in viewitems(self._layer.attribute_table):
            attr_values = dict(zip(self._layer.attributes, attr_values))

            for required_attr in [
                attr.db_name for attr in (self._year, self._disturbance_type)
                if isinstance(attr, Attribute)
            ]:
                if required_attr not in attr_values:
                    self.add_message((
                        logging.ERROR,
                        "Attribute '{}' not found in {}".format(required_attr, self.name)))

                    return {}

            transition_id = None
            if self._transition:
                regen_delay = attr_values.get(self._transition.regen_delay.db_name) \
                    if isinstance(self._transition.regen_delay, Attribute) \
                    else self._transition.regen_delay

                age_after = attr_values.get(self._transition.age_after.db_name) \
                    if isinstance(self._transition.age_after, Attribute) \
                    else self._transition.age_after

                transition_values = {c: attr_values.get(c) for c in self._transition.classifiers} \
                    if isinstance(self._transition.classifiers, list) \
                    else self._transition.classifiers

                transition_id = self._transition_rule_manager.get_or_add(
                    regen_delay, age_after, transition_values)

            values = [
                attr_values.get(self._year.db_name)
                if isinstance(self._year, Attribute) else self._year,
                attr_values.get(self._disturbance_type.db_name)
                if isinstance(self._disturbance_type, Attribute) else self._disturbance_type]

            if transition_id:
                values.append(transition_id)

            if self._conditions:
                values.append(self._conditions)

            for attr in self._metadata_attributes:
                values.append(attr_values.get(attr))

            attr_table[pixel_value] = values

        return attr_table

    def is_empty(self):
        return self._layer.is_empty()

    def _rasterize(self, srs, min_pixel_size, block_extent, requested_pixel_size=None,
                   data_type=None, bounds=None):
        raster, messages = self._layer.as_raster_layer(
            srs, min_pixel_size, block_extent, requested_pixel_size,
            data_type, bounds)

        self.messages = messages
        if not raster or not self.attribute_table:
            return None

        # Layer might also include some extra attributes that aren't part of the
        # core disturbance attributes, but make up some additional metadata used
        # by specific modules.
        disturbance_attributes = [attr.db_name for attr in (
            self._year, self._disturbance_type) if isinstance(attr, Attribute)]

        if self._transition:
            disturbance_attributes.extend([attr.db_name for attr in (
                self._transition.regen_delay, self._transition.age_after)
                if isinstance(attr, Attribute)])

            if isinstance(self._transition.classifiers, list):
                disturbance_attributes.extend(self._transition.classifiers)

        self._metadata_attributes = list(set(raster.attributes) - set(disturbance_attributes))

        return RasterLayer(raster.path, self.attributes, self.attribute_table, tags=self.tags)
