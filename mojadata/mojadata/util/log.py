import logging


def get_logger(cls):
    '''
    Gets a logger with the standard mojadata tiler prefix and a default handler
    if none is configured for the specified class. Users of mojadata can
    configure the logging module specifically for the tiler using the "tiler."
    prefix.
    '''
    logger = logging.getLogger("tiler.{}".format(cls.__name__))
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

    return logger
