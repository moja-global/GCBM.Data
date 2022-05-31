class TransitionRule(object):
    '''
    Defines the transition rules for a disturbance layer. Can be either a simple
    transition rule that defines the post-disturbance stand age and regeneration
    delay, or a more complex rule that also changes the classifier values.

    :param regen_delay: [optional] the number of timesteps after the disturbance
        before the stand starts to re-grow - specified either by an attribute in
        the disturbance layer or by an explicit value, or no delay by default
    :type regen_delay: :class:`.Attribute` or int
    :param age_after: [optional] the age the stand should be reset to after the
        disturbance - specified either by an attribute in the disturbance layer
        or by an explicit value, or no change by default
    :type age_after: :class:`.Attribute` or int
    :param classifiers: [optional] the classifiers to transition to after the
        disturbance - specified either by attribute names in the disturbance layer
        or explicitly by a dictionary of the complete list of classifier names
        to their new values, or no change by default
    :type classifiers: list of str, or dict
    '''

    def __init__(self, regen_delay=0, age_after=-1, classifiers=None):
        self._regen_delay = regen_delay
        self._age_after = age_after
        self._classifiers = classifiers or []

    def __hash__(self):
        result = 37
        result += 3 * hash(self._regen_delay)
        result += 7 * hash(self._age_after)
        result += 13 * sum(hash(c) for c in self._classifiers)
        return result

    def __eq__(self, other):
        return self._regen_delay == other._regen_delay \
            and self._age_after == other._age_after \
            and self._classifiers == other._classifiers

    def __ne__(self, other):
        return not self == other

    @property
    def regen_delay(self):
        return self._regen_delay

    @property
    def age_after(self):
        return self._age_after

    @property
    def classifiers(self):
        return self._classifiers
