from mojadata.block import Block

class Tile(object):
    '''
    A single tile in the landscape to be processed.

    :param x: the absolute x origin of the tile in the landscape
    :type x: float
    :param y: the absolute y origin of the tile in the landscape
    :type y: float
    :param origin: the absolute origin of the landscape
    :type origin: tuple of x, y
    :param pixel_size: the length of one side of a pixel
    :type pixel_size: float
    :param tile_extent: [optional] the length of one side of a tile
    :type tile_extent: float
    :param block_extent: [optional] the length of one side of a block
    :type block_extent: float
    '''

    def __init__(self, x, y, origin, pixel_size, tile_extent=1.0, block_extent=0.1):
        self._x = x
        self._y = y
        self._origin = origin
        self._pixel_size = pixel_size
        self._tile_extent = tile_extent
        self._block_extent = block_extent

    @property
    def pixel_size(self):
        return self._pixel_size

    @property
    def x_min(self):
        return self._x

    @property
    def x_max(self):
        return self._x + 1

    @property
    def y_min(self):
        return self._y

    @property
    def y_max(self):
        return self._y + 1

    @property
    def x_offset(self):
        return abs(int((self.x_min - self._origin[0]) / self._pixel_size))

    @property
    def y_offset(self):
        return abs(int((self.y_max - self._origin[1]) / self._pixel_size))

    @property
    def x_size(self):
        return int(self._tile_extent / self._pixel_size)

    @property
    def y_size(self):
        return int(self._tile_extent / self._pixel_size)

    @property
    def blocks(self):
        '''Iterates through all of the blocks in the tile.'''
        num_blocks = int(self._tile_extent / self._block_extent)
        for y in range(num_blocks):
            for x in range(num_blocks):
                yield Block(x, y, self, self._pixel_size, self._block_extent)

    @property
    def name(self):
        '''The name (or address) of the tile.'''
        return "{0}{1:03d}_{2}{3:03d}".format(
            "-" if self.x_min < 0 else "",
            abs(self.x_min),
            "-" if self.y_max < 0 else "",
            abs(self.y_max))

    @property
    def index(self):
        o_lon = self._convert_to_lon_origin(self.x_min)
        o_lat = self._convert_to_lat_origin(self.y_max)
        tile_x = self._conv_o_to_i(o_lon, self._tile_extent)
        tile_y = self._conv_o_to_i(o_lat, self._tile_extent)
        tile_cols = self._conv_o_to_i(360.0, self._tile_extent)
        tile_idx = tile_y * tile_cols + tile_x
        return tile_idx

    def _convert_to_lon_origin(self, value):
        return value + 180.0

    def _convert_to_lat_origin(self, value):
        return value * -1 + 90.0

    def _conv_o_to_i(self, o, partSize):
        return int((o / partSize) + 0.000000001)
