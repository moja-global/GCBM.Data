import os
from mojadata.util import ogr
import uuid
import logging
import json

from mojadata import cleanup
from mojadata.util import gdal
from mojadata.util.validationhelper import ValidationHelper
from mojadata.util.gdalhelper import GDALHelper
from mojadata.config import (
    GDAL_RASTERIZE_CREATION_OPTIONS,
    GDAL_RASTERIZE_OPTIONS
)
from mojadata.layer.layer import Layer
from mojadata.layer.attribute import Attribute
from mojadata.layer.rasterlayer import RasterLayer


class VectorLayer(Layer):
    '''
    Defines a vector layer to be converted to the Flint tile/block/cell format.
    Can either be converted with an attribute table (the default), or in "raw"
    format using a single attribute's values where the pixel value is the exact
    attribute value.

    :param name: the name of the layer
    :type name: str
    :param path: the path to the input vector file
    :type path: str
    :param attributes: the attributes from the input vector to include
    :type attributes: list of :class:`.Attribute`
    :param raw: [optional] convert in raw mode, where the pixel value is the
        value of a single attribute; default is to use an attribute table
    :type raw: bool
    :param nodata_value: [optional] the nodata value for the output layer;
        defaults to -1
    :type nodata_value: int
    :data_type: [optional] the data type of the output layer; default is to
        detect the appropriate data type
    :type data_type: gdal.GDT_*
    :param layer: [optional] the name of the layer, if the input file is in a
        multi-layer format like GDB
    :param date: [optional] the date the layer applies to - mainly for use with
        :class:`.DiscreteStackLayer`
    :type date: :class:`.date`
    :param tags: [optional] metadata tags describing the layer
    :type tags: list of str
    :param allow_nulls: [optional] allow null values in the attribute table
    :type allow_nulls: bool
    '''

    def __init__(self, name, path, attributes, raw=False, nodata_value=None,
                 data_type=None, layer=None, date=None, tags=None, allow_nulls=False):
        super(self.__class__, self).__init__()
        ValidationHelper.require_path(path)
        self._name = name
        self._data_type = data_type
        self._nodata_value = nodata_value
        self._path = os.path.abspath(path)
        self._layer = layer
        self._raw = raw
        self._date = date
        self._id_attribute = "value_id" if not raw else attributes.name
        self._attribute_table = {}
        self._tags = tags or []
        self._allow_nulls = allow_nulls
        self._attributes = [attributes] if isinstance(attributes, Attribute) \
                                        else attributes

    @property
    def name(self):
        return self._name

    @property
    def tags(self):
        return self._tags

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, value):
        self._path = value

    @property
    def attributes(self):
        return [attr.db_name for attr in self._attributes]

    @property
    def attribute_table(self):
        return self._attribute_table

    @property
    def date(self):
        return self._date

    def _rasterize(self, srs, min_pixel_size, block_extent, requested_pixel_size=None,
                   data_type=None, bounds=None, preserve_temp_files=False):
        tmp_dir = "_".join((os.path.abspath(self._make_name()), str(uuid.uuid1())[:4]))
        if not os.path.exists(tmp_dir):
            os.makedirs(tmp_dir)

        if not preserve_temp_files:
            cleanup.register_temp_dir(tmp_dir)

        base_ogr2ogr_opts = ["-gt", "65535", "-lco", "SPATIAL_INDEX=NO",
                             "-nlt", "PROMOTE_TO_MULTI", "-ds_transaction",
                             "-dsco", "SPATIALITE=YES", "-dim", "XY"]

        reproj_opts = base_ogr2ogr_opts + ["-t_srs", str(srs)]

        if self._layer:
            reproj_opts += [self._layer]

        # Do a first pass with just the reprojection and layer selection - sometimes trying to
        # include the spat/spat_srs extent filter in the same operation results in an incorrect
        # spatial extent in the output layer.
        initial_reproj_path = os.path.join(tmp_dir, self._make_name("_reproj.db"))
        gdal.VectorTranslate(initial_reproj_path, self._path, format="SQLite", options=reproj_opts)

        if bounds:
            reproj_opts += ["-spat_srs", str(srs), "-spat"] \
                + [str(coord) for coord in bounds]

        if self._attributes:
            reproj_opts += ["-select", ",".join((attr.name for attr in self._attributes))]

        reproj_path = os.path.join(tmp_dir, self._make_name(".db"))
        gdal.VectorTranslate(reproj_path, initial_reproj_path, format="SQLite", options=reproj_opts)
        if not os.path.exists(reproj_path):
            self.add_message((logging.WARN, "No features remaining in the study area - resolution may be too coarse."))
            return None

        if not self._raw:
            self._build_attribute_table(reproj_path)

        clip_path = os.path.join(tmp_dir, self._make_name("_clip.db"))
        gdal.VectorTranslate(clip_path, reproj_path, format="SQLite",
                             options=base_ogr2ogr_opts + [
            "-select", self._id_attribute,
            "-where", "{} IS NOT NULL".format(self._id_attribute)])

        # Check that some geometry actually made it through the filtering process - calling
        # gdal.Rasterize on an empty vector layer will cause a hard crash in GDAL.
        if VectorLayer.is_empty_layer(clip_path):
            self.add_message((logging.WARN, "{} is empty - skipping".format(self._name)))
            return None

        self._data_type = data_type if data_type is not None \
            else self._data_type if self._data_type is not None \
            else self._get_native_data_type() if self._raw \
            else GDALHelper.best_fit_data_type(
                (0, max(self._attribute_table) if self._attribute_table else 0))

        if self._nodata_value is None:
            self._nodata_value = GDALHelper.best_nodata_value(self._data_type)

        # Fix for complicated geometry making rasterization very slow (days instead
        # of hours).
        self._clean_multipolygons(clip_path)

        tmp_raster_path = os.path.join(tmp_dir, self._make_name(".tiff"))
        gdal.Rasterize(tmp_raster_path, clip_path,
            layers=["exploded"],
            xRes=min_pixel_size, yRes=min_pixel_size,
            outputSRS=srs, outputBounds=bounds,
            attribute=self._id_attribute,
            noData=self._nodata_value,
            creationOptions=GDAL_RASTERIZE_CREATION_OPTIONS,
            targetAlignedPixels=True,
            options=GDAL_RASTERIZE_OPTIONS \
                + ["-ot", GDALHelper.type_code_lookup.get(self._data_type) or "Float32"])

        return RasterLayer(tmp_raster_path, self.attributes, self._attribute_table,
                           date=self._date, tags=self._tags, allow_nulls=self._allow_nulls)

    def is_empty(self):
        return VectorLayer.is_empty_layer(self._path, self._layer or 0)

    def _clean_multipolygons(self, path):
        ds = ogr.Open(path, 1)
        try:
            # Find the name of the table containing the geometry being rasterized.
            geometry_tables = ds.ExecuteSQL("SELECT f_table_name FROM geometry_columns LIMIT 1;")
            geometry_table = json.loads(geometry_tables[0].ExportToJson())["properties"]["f_table_name"]
            ds.ReleaseResultSet(geometry_tables)

            # Find the name of the feature that needs cleaning.
            features = ds.ExecuteSQL("PRAGMA table_info('{}')".format(geometry_table))
            geometry_feature = None
            for feature in features:
                feature_json = json.loads(feature.ExportToJson())
                feature_properties = feature_json.get("properties", {})
                if "POLYGON" in feature_properties.get("type", "").upper():
                    geometry_feature = feature_properties.get("name")
                    break

            ds.ReleaseResultSet(features)
            if not geometry_feature:
                self.add_message((logging.WARN, "Couldn't detect geometry feature name, skipped cleaning multipolygons."))
                return

            # Explode the multipolygon into multiple ordinary polygons to speed up GDAL processing.
            result = ds.ExecuteSQL(
                "SELECT ElementaryGeometries('{}', '{}', 'exploded', 'id_1', 'id_2');"
                .format(geometry_table, geometry_feature))

            ds.ReleaseResultSet(result)
        finally:
            ds = None

    def _make_name(self, ext=""):
        return "{}{}".format(self._name, ext)

    def _build_attribute_table(self, path):
        ValidationHelper.require_path(path)
        ds = ogr.Open(path, 1)
        if not ds:
            raise IOError("Error reading file: {}".format(path))

        selected_attributes = {attr.name for attr in self._attributes}
        found_attributes = set()
        layer = None
        try:
            layer = ds.GetLayer()
            layer.CreateField(ogr.FieldDefn(self._id_attribute, ogr.OFTInteger))

            # Workaround for feature updates breaking iteration in some vector
            # layer types like SQLite: get features by ID instead of iterating
            # over the collection.
            # https://gis.stackexchange.com/questions/109194/setfeature-creates-infinite-loop-when-updating-sqlite-feature-using-ogr
            feature_ids = [feature.GetFID() for feature in layer]
            if not feature_ids:
                return

            next_value_id = 1
            ds.StartTransaction()
            for feature_id in feature_ids:
                feature = layer.GetFeature(feature_id)
                try:
                    attribute_values = []
                    for attr in self._attributes:
                        # Try to get the attribute from the feature as-is,
                        # then retry as plain ASCII in case it's a unicode
                        # mismatch issue.
                        for attr_name in (attr.name, attr.name.encode("ascii", "ignore")):
                            try:
                                attr_value = feature[attr_name]
                                attribute_values.append(
                                    attr.sub(attr_value) if attr.filter(attr_value)
                                    else None)

                                found_attributes.add(attr.name)
                                break
                            except:
                                pass

                    # Don't rasterize polygons where any of the selected attributes
                    # are null, unless the user explicitly allows it.
                    if not self._allow_nulls and not ValidationHelper.no_empty_values(attribute_values):
                        continue

                    value_id = None
                    existing_key = [item[0] for item in self._attribute_table.items()
                                    if item[1] == attribute_values]
                    if existing_key:
                        value_id = existing_key[0]
                    else:
                        value_id = next_value_id
                        self._attribute_table[value_id] = attribute_values
                        next_value_id += 1

                    feature[self._id_attribute] = value_id
                    layer.SetFeature(feature)
                finally:
                    feature = None

            ds.CommitTransaction()
        except Exception as e:
            self.add_message((logging.ERROR, "Error in {}: {}".format(path, e)))
        finally:
            layer = None
            ds = None

        missing_attributes = selected_attributes - found_attributes
        if missing_attributes:
            self.add_message((logging.WARNING, "Attributes not found in {}: {}".format(
                path, ", ".join(missing_attributes))))

    def _get_native_data_type(self):
        ds = ogr.Open(self._path, 0)
        if not ds:
            return None

        try:
            layer = ds.GetLayerByName(self._layer) if self._layer else ds.GetLayer(0)
            layer_def = layer.GetLayerDefn()
            field_idx = layer_def.GetFieldIndex(self._id_attribute)
            field = layer_def.GetFieldDefn(field_idx)
            field_type_code = field.GetType()
            field_type_name = field.GetTypeName().lower()
            field_type_code_family = gdal.GDT_Int32 if "int" in field_type_name else gdal.GDT_Float32
            return field_type_code or field_type_code_family
        except:
            return None
        finally:
            ds = None

    @staticmethod
    def is_empty_layer(path, layer=0):
        if not os.path.exists(path):
            return True

        ds = ogr.Open(path, 0)
        if not ds:
            return True

        try:
            layer = ds.GetLayer(layer)
            return layer.GetNextFeature() is None
        except:
            return True
        finally:
            ds = None
