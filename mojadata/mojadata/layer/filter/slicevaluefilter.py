from six import text_type

class SliceValueFilter(object):
    '''
    Compares a section of a value to a target value.

    :param target_val: the target value to compare against
    :type target_val: any string-convertible type
    :param slice_pos: [optional] the start index of the slice to extract from
        the value being compared - defaults to the beginning
    :type slice_pos: int
    :param slice_len: [optional] the length of the slice to extract from the
        value being compared - defaults to the whole length
    :type slice_len: int
    '''

    def __init__(self, target_val, slice_pos=0, slice_len=None):
        self._target_val = target_val
        self._pos = slice_pos
        self._len = slice_len
        
    def __call__(self, val):
        '''
        Evaluates the filter against a value.

        :returns: True if the values match, False if not
        '''
        slice_len = self._len or len(val)
        return type(self._target_val)(val)[self._pos:slice_len] == self._target_val \
            or text_type(val)[self._pos:slice_len] == text_type(self._target_val)
