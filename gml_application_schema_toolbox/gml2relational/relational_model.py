"""
/**
 *   Copyright (C) 2016 BRGM (http:///brgm.fr)
 *   Copyright (C) 2016 Oslandia <infos@oslandia.com>
 *
 *   This library is free software; you can redistribute it and/or
 *   modify it under the terms of the GNU Library General Public
 *   License as published by the Free Software Foundation; either
 *   version 2 of the License, or (at your option) any later version.
 *
 *   This library is distributed in the hope that it will be useful,
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 *   Library General Public License for more details.
 *   You should have received a copy of the GNU Library General Public
 *   License along with this library; if not, see <http://www.gnu.org/licenses/>.
 */
"""
from builtins import object
# -*- coding: utf-8 -*-
import pickle

def xpath_to_column_name(xpath):
    if xpath == "text()":
        return "v"
    if xpath == "geometry()":
        return "geometry"
    t = []
    for e in xpath.split('/'):
        if e == "text()" or e == "geometry()":
            continue
        else:
            t.append(e.replace('@','').replace('[','').replace(']',''))
    return "_".join(t)

class Field(object):
    def __init__(self, xpath, optional = False):
        self._xpath = xpath
        self._optional = optional

    def xpath(self):
        return self._xpath
    def set_xpath(self, xpath):
        self._xpath = xpath
    def name(self):
        return xpath_to_column_name(self.xpath())
    def optional(self):
        return self._optional
    def set_optional(self, optional):
        self._optional = optional

    def __hash__(self):
        return self._xpath.__hash__()

class Link(Field):
    """A Link represents a link to another type/table"""

    def __init__(self, xpath, optional, min_occurs, max_occurs, ref_type, ref_table = None, substitution_group = None):
        Field.__init__(self, xpath, optional)
        self.__min_occurs = min_occurs
        self.__max_occurs = max_occurs
        self.__ref_type = ref_type # SQL type (str)
        self.__ref_table = ref_table # Table
        self.__substitution_group = substitution_group # for element that derives from a common element

    def clone(self):
        return Link(self.xpath(), self.optional(), self.min_occurs(), self.max_occurs(), self.ref_type(), self.ref_table())

    def ref_type(self):
        return self.__ref_type
    def ref_table(self):
        return self.__ref_table
    def set_ref_table(self, ref_table):
        self.__ref_table = ref_table
    def min_occurs(self):
        return self.__min_occurs
    def max_occurs(self):
        return self.__max_occurs
    def substitution_group(self):
        return self.__substitution_group

    def __repr__(self):
        return "Link<{}({}-{}){}>".format(self.xpath(), self.min_occurs(),
                                          "*" if self.max_occurs() is None else self.max_occurs(),
                                          "" if self.ref_table() is None else "," + self.ref_table().name())

class BackLink(Field):
    """A BackLink represents a foreign key relationship"""

    def __init__(self, xpath, ref_table):
        Field.__init__(self, xpath)
        self.__ref_table = ref_table
    def clone(self):
        return BackLink(self.xpath(), self.ref_table())

    def ref_table(self):
        return self.__ref_table

    def __repr__(self):
        return "BackLink<{}({})>".format(self.xpath(), self.ref_table().name())

class Column(Field):
    """A Column is a (simple type) column"""

    def __init__(self, xpath, optional = False, ref_type = None, auto_incremented = False):
        Field.__init__(self, xpath, optional)
        self.__ref_type = ref_type
        self.__auto_incremented = auto_incremented
    def clone(self):
        return Column(self.xpath(), self.optional(), self.ref_type(), self.auto_incremented())

    def ref_type(self):
        return self.__ref_type
    def auto_incremented(self):
        return self.__auto_incremented

    def __repr__(self):
        return "Column<{},{}{}{}>".format(self.xpath(), self.ref_type(), ",optional" if self.optional() else "", ",autoincremented" if self.auto_incremented() else "")

class Geometry(Field):
    """A geometry column"""

    def __init__(self, xpath, type, dim, srid, optional = False):
        """
        :param name: Name of the geometry column
        :param type: Geometry type in ['Point', 'LineString', 'Polygon', 'MultiPoint', 'MultiLineString', 'MultiPolygon']
        :param dim: dimension : 2 or 3
        :param srid: epsg code
        :param optional: is it optional
        """
        Field.__init__(self, xpath, optional)
        self.__type = type
        self.__dim = dim
        self.__srid = srid
    def clone(self):
        return Geometry(self.xpath(), self.type(), self.dimension(), self.srid(), self.optional())

    def type(self):
        return self.__type
    def dimension(self):
        return self.__dim
    def srid(self):
        return self.__srid
    def __repr__(self):
        return "Geometry<{},{}{}({}){}>".format(self.xpath(), self.type(), "Z" if self.dimension() == 3 else "", self.srid(), ",optional" if self.optional() else "")

class Table(object):
    """A Table is a list of Columns or Links to other tables, a list of geometry columns and an id"""

    def __init__(self, name = '', fields = [], uid = None):
        self.__name = name
        self.__fields = {}
        for f in fields:
            self.__fields[f.name()] = f
        # uid column
        self.__uid_column = uid
        # last value for autoincremented id
        # A Table must have either a uid column or a autoincremented id
        # but not both
        self.__last_uid = None

        # whether this table can be merged with its parent
        # a table cannot be merged if it can be refered by other tables
        # i.e. if it has an id
        self.__mergeable = True
    def clone(self):
        t = Table(self.name(), list(self.fields().values()), self.uid_column())
        t.__last_uid = self.__last_uid
        t.__mergeable = self.__mergeable
        return t

    def name(self):
        return self.__name
    def set_name(self, name):
        self.__name = name
    def fields(self):
        return self.__fields
    def add_field(self, field):
        #if self.__fields.has_key(field.name()):
        #    raise RuntimeError("add_field {} already existing".format(field.name()))
        self.__fields[field.name()] = field
    def add_fields(self, fields):
        for f in fields:
            self.add_field(f)
    def set_fields(self, fields):
        self.__fields = {}
        self.add_fields(fields)
        
    def remove_field(self, field_name):
        if field_name in self.__fields:
            del self.__fields[field_name]
    def has_field(self, field_name):
        return field_name in self.__fields
    def field(self, field_name):
        return self.__fields.get(field_name)
    
    def links(self):
        return [x for k, x in self.fields().items() if isinstance(x, Link)]
    def columns(self):
        return [x for k, x in self.fields().items() if isinstance(x, Column)]
    def geometries(self):
        return [x for k, x in self.fields().items() if isinstance(x, Geometry)]
    def back_links(self):
        return [x for k, x in self.fields().items() if isinstance(x, BackLink)]

    def uid_column(self):
        return self.__uid_column
    def set_uid_column(self, uid_column):
        self.__uid_column = uid_column
        self.__mergeable = False

    def has_autoincrement_id(self):
        return self.__last_uid is not None
    def set_autoincrement_id(self):
        self.__uid_column = Column("@id", auto_incremented = True)
        self.__fields['id'] = self.__uid_column
        self.__last_uid = 0
        self.__mergeable = True
    def increment_id(self):
        self.__last_uid += 1
        return self.__last_uid
        
    def add_back_link(self, name, table):
        f = [x for x in table.back_links() if x.name() == name and x.table() == table]
        if len(f) == 0:
            self.__fields[name] = BackLink(name, table)

    def max_field_depth(self):
        ff = [len(f.xpath().split('/')) for f in list(self.__fields.values())]
        if len(ff) == 0:
            return 0
        return max(ff)

    def is_mergeable(self):
        return self.__mergeable

    def __repr__(self):
        return "Table<{};{}>".format(self.name(), ";".join([f.__repr__() for f in list(self.__fields.values())]))

class Model(object):
    def __init__(self, tables, tables_rows, root_name):
        self.__tables = tables
        self.__tables_rows = tables_rows
        self.__root_name = root_name

    def tables(self):
        return self.__tables

    def tables_rows(self):
        return self.__tables_rows

    def root_name(self):
        return self.__root_name

model_file_magic = "GML2Relational model"
model_file_version = 1

def save_model_to(model, filename):
    fo = open(filename, "w")
    pickle.dump(model_file_magic, fo)
    pickle.dump(model_file_version, fo)
    pickle.dump(model, fo)
    fo.close()

def load_model_from(filename):
    fi = open(filename, "r")
    file_magic = pickle.load(fi)
    if file_magic != model_file_magic:
        raise RuntimeError("Invalid model file")
    version = pickle.load(fi)
    if version > model_file_version:
        raise RuntimeError("Invalid model file version")
    model = pickle.load(fi)
    fi.close()
    return model

