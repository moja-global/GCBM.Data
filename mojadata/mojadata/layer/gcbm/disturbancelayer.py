import os
import uuid
import logging
import numpy as np
from future.utils import viewitems
from mojadata import cleanup
from mojadata.layer.gcbm.transitionrule import TransitionRule
from mojadata.layer.layer import Layer
from mojadata.layer.rasterlayer import RasterLayer
from mojadata.layer.attribute import Attribute
from mojadata import config as gdal_config
from mojadata.util.gdalhelper import GDALHelper


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
    :param survivor_transition: [optional, CBM4 only] the transition rule definition
        for the disturbance layer for the portion of the stand unaffected by the
        disturbance - no transition/model default if unspecified
    :type transition: :class:`.TransitionRule`
    '''

    def __init__(self, transition_rule_manager, lyr, year, disturbance_type,
                 transition=None, tags=None, conditions=None, survivor_transition=None,
                 proportion=None):
        super(self.__class__, self).__init__()
        self._transition_rule_manager = transition_rule_manager
        self._layer = lyr
        self._year = year
        self._disturbance_type = disturbance_type
        self._transition = transition
        self._survivor_transition = survivor_transition
        self._proportion = proportion
        self._tags = ["disturbance"] + (tags or [])
        self._metadata_attributes = []
        self._conditions = conditions
        self._attributes = ["year", "disturbance_type"]
        if proportion:
            self._attributes.append("proportion")
        if transition:
            self._attributes.append("transition")
        if survivor_transition:
            self._attributes.append("survivor_transition")
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
        return self._build_attribute_table(self._layer)

    def is_empty(self):
        return self._layer.is_empty()

    def _rasterize(self, srs, min_pixel_size, block_extent, requested_pixel_size=None,
                   data_type=None, bounds=None, **kwargs):
        raster, messages = self._layer.as_raster_layer(
            srs, min_pixel_size, block_extent, requested_pixel_size,
            data_type, bounds, **kwargs)

        self.messages = messages
        if not raster:
            return None

        uninterpreted_layer = not self._layer.attributes
        if uninterpreted_layer:
            raster = self._flatten(raster)

        # Layer might also include some extra attributes that aren't part of the
        # core disturbance attributes, but make up some additional metadata used
        # by specific modules.
        disturbance_attributes = [
            attr.db_name for attr in (self._year, self._disturbance_type, self._proportion)
            if isinstance(attr, Attribute)
        ]

        for transition in (self._transition, self._survivor_transition):
            if not transition:
                continue

            disturbance_attributes.extend([attr.db_name for attr in (
                transition.regen_delay, transition.age_after)
                if isinstance(attr, Attribute)])

            if isinstance(transition.classifiers, list):
                disturbance_attributes.extend(transition.classifiers)

        if not uninterpreted_layer:
            self._metadata_attributes = list(set(raster.attributes) - set(disturbance_attributes))

        # Handle the situation where a raster with no user-provided interpretation
        # is used as a disturbance layer, in which case we use all non-nodata pixel
        # values.
        attribute_table = (
            self.attribute_table if self._layer.attributes
            else self._build_attribute_table(raster)
        )
        
        if not attribute_table:
            return None

        return RasterLayer(raster.path, self.attributes, attribute_table, tags=self.tags)

    def _build_attribute_table(self, layer):
        attr_table = {}
        for pixel_value, attr_values in viewitems(layer.attribute_table):
            attr_values = dict(zip(layer.attributes, attr_values))

            for required_attr in [
                attr.db_name for attr in (self._year, self._disturbance_type)
                if isinstance(attr, Attribute)
            ]:
                if required_attr not in attr_values:
                    self.add_message((
                        logging.ERROR,
                        "Attribute '{}' not found in {}".format(required_attr, self.name)))

                    return {}

            values = [
                int(float(attr_values.get(self._year.db_name)))
                if isinstance(self._year, Attribute) else int(float(self._year)),
                attr_values.get(self._disturbance_type.db_name)
                if isinstance(self._disturbance_type, Attribute) else self._disturbance_type
            ]

            if self._proportion is not None:
                values.append(
                    float(attr_values.get(self._proportion.db_name))
                    if isinstance(self._proportion, Attribute)
                    else float(self._proportion))

            for transition_type, transition in (
                (TransitionRule.mortality, self._transition),
                (TransitionRule.survivor, self._survivor_transition)
            ):
                if transition:
                    transition_id = self._record_transition(transition_type, transition, attr_values)
                    values.append(transition_id)

            if self._conditions:
                values.append(self._conditions)

            for attr in self._metadata_attributes:
                values.append(attr_values.get(attr))

            attr_table[pixel_value] = values

        return attr_table

    def _record_transition(self, transition_type, transition, attr_values):
        regen_delay = attr_values.get(transition.regen_delay.db_name) \
            if isinstance(transition.regen_delay, Attribute) \
            else transition.regen_delay

        age_after = attr_values.get(transition.age_after.db_name) \
            if isinstance(transition.age_after, Attribute) \
            else transition.age_after

        transition_values = {c: attr_values.get(c) for c in self._transition.classifiers} \
            if isinstance(transition.classifiers, list) \
            else transition.classifiers

        transition_id = self._transition_rule_manager.get_or_add(
            transition_type, regen_delay, age_after, transition_values)

        return transition_id

    def _flatten(self, layer):
        tmp_dir = "_".join((os.path.abspath(layer.name), str(uuid.uuid1())[:4]))
        if not os.path.exists(tmp_dir):
            os.makedirs(tmp_dir)

        cleanup.register_temp_dir(tmp_dir)
        nodata = layer.nodata_value
        output_path = os.path.join(tmp_dir, layer.name)
        GDALHelper.calc(layer.path, output_path, lambda d: np.where(d != nodata, d, nodata))

        return RasterLayer(output_path, ["disturbed"], {1: [1]}, name=layer.name)
