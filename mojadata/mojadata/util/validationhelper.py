import os
from six import string_types


class ValidationHelper(object):

    @staticmethod
    def require_path(path):
        if not os.path.exists(path):
            raise IOError("File not found: {}".format(path))

    @staticmethod
    def no_empty_values(values):
        for value in values:
            if value is None or (isinstance(value, string_types)
                                 and (not value or value.isspace())):
                return False

        return True
