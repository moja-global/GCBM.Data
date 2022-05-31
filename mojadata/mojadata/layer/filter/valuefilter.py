from six import text_type

class ValueFilter(object):
    '''
    Compares a value to a target value.

    :param target_val: the target value to compare against
    :type target_val: any string-convertible type or list of values
    '''

    def __init__(self, target_val, *args, **kwargs):
        self._target_val = target_val
        
    def __call__(self, val):
        '''
        Evaluates the filter against a value.

        :returns: True if the values match, False if not
        '''
        if isinstance(self._target_val, list) or isinstance(self._target_val, set):
            return any((self._compare(v, val) for v in self._target_val))

        return self._compare(self._target_val, val)

    def _compare(self, v, other):
        return type(v)(other) == v or text_type(other) == text_type(v)
