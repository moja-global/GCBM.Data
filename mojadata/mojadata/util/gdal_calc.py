#!/usr/bin/env python
# -*- coding: utf-8 -*-
#******************************************************************************
#
#  Project:  GDAL
#  Purpose:  Command line raster calculator with numpy syntax
#  Author:   Chris Yesson, chris.yesson@ioz.ac.uk
#
#******************************************************************************
#  Copyright (c) 2010, Chris Yesson <chris.yesson@ioz.ac.uk>
#  Copyright (c) 2010-2011, Even Rouault <even dot rouault at mines-paris dot org>
#  Copyright (c) 2016, Piers Titus van der Torren <pierstitus@gmail.com>
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#  THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
#******************************************************************************

import os
import logging
from future.utils import viewitems

import numpy

from mojadata.util import gdal
from osgeo import gdalnumeric

# set up some default nodata values for each datatype
DefaultNDVLookup = {
    "Byte":255, "UInt16":65535, "Int16":-32767, "UInt32":4294967293,
    "Int32":-2147483647, "Float32":3.402823466E+38, "Float64":1.7976931348623158E+308
}

def calc(calc, outfile, nodata_value=None, type=None, format="GTiff", creation_options=[],
         overwrite=False, quiet=True, **input_files):

    # set up global namespace for eval with all functions of gdalnumeric
    global_namespace = dict([(key, getattr(gdalnumeric, key))
        for key in dir(gdalnumeric) if not key.startswith('__')])

    # set up some lists to store data for each band
    myFiles = []
    myBands = []
    myAlphaList = []
    myDataType = []
    myDataTypeNum = []
    myNDV = []
    DimensionsCheck = None

    # loop through input files - checking dimensions
    try:
        for myI, myF in viewitems(input_files):
            if not myI.endswith("_band"):
                # check if we have asked for a specific band...
                if "{}_band".format(myI) in input_files:
                    myBand = input_files["{}_band".format(myI)]
                else:
                    myBand = 1

                myFile = gdal.Open(myF, gdal.GA_ReadOnly)
                if not myFile:
                    raise IOError("No such file or directory: '{}'".format(myF))

                myFiles.append(myFile)
                myBands.append(myBand)
                myAlphaList.append(myI)
                myDataType.append(gdal.GetDataTypeName(myFile.GetRasterBand(myBand).DataType))
                myDataTypeNum.append(myFile.GetRasterBand(myBand).DataType)
                myNDV.append(myFile.GetRasterBand(myBand).GetNoDataValue())
                # check that the dimensions of each layer are the same
                if DimensionsCheck:
                    if DimensionsCheck != [myFile.RasterXSize, myFile.RasterYSize]:
                        raise Exception("Error! Dimensions of file {} ({}, {}) are different from other files ({}, {}). Cannot proceed".format(
                            myF, myFile.RasterXSize, myFile.RasterYSize, DimensionsCheck[0], DimensionsCheck[1]))
                else:
                    DimensionsCheck = [myFile.RasterXSize, myFile.RasterYSize]

                logging.debug("gdal_calc file {}: {}, dimensions: {}, {}, type: {}".format(
                    myI, myF, DimensionsCheck[0], DimensionsCheck[1], myDataType[-1]))

        # set up output file
        myOut = None
        myOutB = None
        if os.path.isfile(outfile) and not overwrite:
            myOut = gdal.Open(outfile, gdal.GA_Update)
            if [myOut.RasterXSize, myOut.RasterYSize] != DimensionsCheck:
                raise Exception("Error! Output exists, but is the wrong size.  Use the --overwrite option to automatically overwrite the existing file")
            myOutB = myOut.GetRasterBand(1)
            myOutNDV = myOutB.GetNoDataValue()
            myOutType = gdal.GetDataTypeName(myOutB.DataType)
        else:
            # remove existing file and regenerate
            if os.path.isfile(outfile):
                os.remove(outfile)

            # find data type to use
            if not type:
                # use the largest type of the input files
                myOutType = gdal.GetDataTypeName(max(myDataTypeNum))
            else:
                myOutType=type

            # create file
            myOutDrv = gdal.GetDriverByName(format)
            myOut = myOutDrv.Create(
                outfile, DimensionsCheck[0], DimensionsCheck[1], 1,
                gdal.GetDataTypeByName(myOutType), creation_options)

            # set output geo info based on first input layer
            myOut.SetGeoTransform(myFiles[0].GetGeoTransform())
            myOut.SetProjection(myFiles[0].GetProjection())

            if nodata_value is not None:
                myOutNDV = nodata_value
            else:
                myOutNDV = DefaultNDVLookup[myOutType]

            myOutB = myOut.GetRasterBand(1)
            myOutB.SetNoDataValue(myOutNDV)
            # write to band
            myOutB = None

        # find block size to chop grids into bite-sized chunks
        # use the block size of the first layer to read efficiently
        myBlockSize = myFiles[0].GetRasterBand(myBands[0]).GetBlockSize();
        # store these numbers in variables that may change later
        nXValid = myBlockSize[0]
        nYValid = myBlockSize[1]
        # find total x and y blocks to be read
        nXBlocks = int((DimensionsCheck[0] + myBlockSize[0] - 1) / myBlockSize[0]);
        nYBlocks = int((DimensionsCheck[1] + myBlockSize[1] - 1) / myBlockSize[1]);
        myBufSize = myBlockSize[0] * myBlockSize[1]

        for myBandNo in myBands:
            for X in range(0, nXBlocks):
                # in the rare (impossible?) case that the blocks don't fit perfectly
                # change the block size of the final piece
                if X == nXBlocks - 1:
                    nXValid = DimensionsCheck[0] - X * myBlockSize[0]
                    myBufSize = nXValid * nYValid

                # find X offset
                myX = X * myBlockSize[0]

                # reset buffer size for start of Y loop
                nYValid = myBlockSize[1]
                myBufSize = nXValid * nYValid

                for Y in range(0,nYBlocks):
                    # change the block size of the final piece
                    if Y == nYBlocks - 1:
                        nYValid = DimensionsCheck[1] - Y * myBlockSize[1]
                        myBufSize = nXValid * nYValid

                    # find Y offset
                    myY = Y * myBlockSize[1]

                    # create empty buffer to mark where nodata occurs
                    myNDVs = None

                    # make local namespace for calculation
                    local_namespace = {}

                    # fetch data for each input layer
                    for i, Alpha in enumerate(myAlphaList):
                        myval = gdalnumeric.BandReadAsArray(
                            myFiles[i].GetRasterBand(myBandNo),
                            xoff=myX, yoff=myY,
                            win_xsize=nXValid, win_ysize=nYValid)

                        # fill in nodata values
                        if myNDV[i] is not None:
                            if myNDVs is None:
                                myNDVs = numpy.zeros(myBufSize)
                                myNDVs.shape = (nYValid, nXValid)
                            myNDVs = 1 * numpy.logical_or(myNDVs == 1, myval == myNDV[i])

                        # add an array of values for this block to the eval namespace
                        local_namespace[Alpha] = myval
                        myval = None

                    # try the calculation on the array blocks
                    try:
                        myResult = eval(calc, global_namespace, local_namespace)
                    except:
                        raise RuntimeError("evaluation of calculation {} failed".format(calc))

                    # Propagate nodata values (set nodata cells to zero
                    # then add nodata value to these cells).
                    if myNDVs is not None:
                        myResult = ((1 * (myNDVs == 0)) * myResult) + (myOutNDV * myNDVs)
                    elif not isinstance(myResult, numpy.ndarray):
                        myResult = numpy.ones((nYValid, nXValid)) * myResult

                    # write data block to the output file
                    myOutB = myOut.GetRasterBand(myBandNo)
                    gdalnumeric.BandWriteArray(myOutB, myResult, xoff=myX, yoff=myY)
    except:
        raise
    finally:
        if myOutB:
            myOutB = None
        if myOut:
            myOut = None
        for myFile in myFiles:
            myFile = None
