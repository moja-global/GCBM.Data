class Block(object):
    '''
    Represents a block of pixels within a :class:`.Tile`. A block is the typical
    division of work in the Flint platform.

    :param x: the block's relative x coordinate within the tile
    :type x: int
    :param y: the block's relative y coordinate within the tile
    :type y: int
    :param tile: the block's parent :class:`.Tile`
    :type tile: :class:`.Tile`
    :param pixel_size: the size of one side of a pixel within the block
    :type pixel_size: float
    :param extent: the size of one side of the block
    :type extent: float
    '''

    def __init__(self, x, y, tile, pixel_size, extent):
        self._x = x
        self._y = y
        self._tile = tile
        self._pixel_size = pixel_size
        self._extent = extent

    @property
    def x_size(self):
        '''The width of the block in pixels.'''
        return int(self._extent / self._pixel_size)

    @property
    def y_size(self):
        '''The height of the block in pixels.'''
        return int(self._extent / self._pixel_size)

    @property
    def x_offset(self):
        '''The horizontal offset of the block from the origin of the landscape.'''
        return abs(self._tile.x_offset + self._x * self.x_size)

    @property
    def y_offset(self):
        '''The vertical offset of the block from the origin of the landscape.'''
        return abs(self._tile.y_offset + self._y * self.y_size)
