import os
import csv
import sys
from future.utils import viewitems
from multiprocessing import RLock
from multiprocessing.managers import BaseManager


class _TransitionRuleManager(object):
    '''
    Accumulates transition rules from all disturbance layers and assigns IDs to
    unique rules for later output to csv format. The preferred way to obtain an
    instance of the rule manager is through :class:`.SharedTransitionRuleManager`
    .. code-block:: python
        mgr = SharedTransitionRuleManager()
        mgr.start()
        rule_manager = mgr.TransitionRuleManager()

    :param output_path: full path and filename of the csv file to output
    :type output_path: str
    '''

    class RuleInstance(object):

        def __init__(self, regen_delay, age_after, classifier_values=None):
            self._regen_delay = regen_delay
            self._age_after = age_after
            self._classifier_values = classifier_values or {}

        def __hash__(self):
            result = 13
            result += 7 * hash(self._regen_delay)
            result += 17 * hash(self._age_after)
            result += 23 * sum(((hash(v) for v in self._classifier_values)))
            return result

        def __eq__(self, other):
            return self._regen_delay == other._regen_delay \
                and self._age_after == other._age_after \
                and self._classifier_values == other._classifier_values

        def __ne__(self, other):
            return not self == other

        @property
        def regen_delay(self):
            return self._regen_delay

        @property
        def age_after(self):
            return self._age_after

        @property
        def classifier_set(self):
            return self._classifier_values

        @property
        def classifier_values(self):
            return self._classifier_values.values()

        @property
        def classifier_names(self):
            return self._classifier_values.keys()

    def __init__(self):
        self._lock = RLock()
        self._transition_rules = {}
        self._next_id = 1

    def get_or_add(self, regen_delay, age_after, classifier_values=None):
        '''
        Gets the unique ID for a set of transition rule values, adding it to
        the collection of accumulated rules if necessary.

        :param regen_delay: the number of timesteps after a disturbance until a
            stand is allowed to re-grow
        :type regen_delay: int
        :param age_after: the age to reset the stand to after a disturbance
        :type age_after: int
        :param classifier_values: [optional] the complete set of classifier
            values to transition to after a disturbance, or no change by default
        :type classifier_values: dict of classifier name to new classifier value
        :returns: the unique ID for the transition rule
        '''
        unique_rule = _TransitionRuleManager.RuleInstance(regen_delay, age_after, classifier_values)
        id = self._transition_rules.get(unique_rule)
        if not id:
            with self._lock:
                id = self._transition_rules.get(unique_rule)
                if not id:
                    id = self._next_id
                    self._transition_rules[unique_rule] = self._next_id
                    self._next_id += 1
        return id

    def write_rules(self, output_path="transition_rules.csv"):
        '''
        Writes the unique transition rules to the rule manager's output path.
        '''
        if not self._transition_rules:
            return

        rules_dir = os.path.dirname(os.path.abspath(output_path))
        if not os.path.exists(rules_dir):
            os.makedirs(rules_dir)

        with self._open_csv(output_path) as out_file:
            header = ["id", "regen_delay", "age_after"]
            header.extend(self._find_classifier_names())
            writer = csv.DictWriter(out_file, header)
            writer.writeheader()
            for rule, id in sorted(viewitems(self._transition_rules), key=lambda item: item[1]):
                rule_data = {"id": id, "regen_delay": rule.regen_delay, "age_after": rule.age_after}
                rule_data.update(rule.classifier_set)
                writer.writerow(rule_data)

    def _open_csv(self, path):
        return open(path, "wb") if sys.version_info[0] == 2 \
            else open(path, "w", newline="", encoding="utf-8", errors="surrogateescape")

    def _find_classifier_names(self):
        classifier_names = set()
        for rule in self._transition_rules:
            for name in rule.classifier_names:
                classifier_names.add(name)

        return classifier_names

class SharedTransitionRuleManager(BaseManager): pass
SharedTransitionRuleManager.register("TransitionRuleManager", _TransitionRuleManager)
