#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Dec 12 14:32:32 2017

@author: Christopher Albert <albert@alumni.tugraz.at>
"""
import importlib
import inspect
import numpy as np
import os
import re
from cffi import FFI

arraydims = """
  typedef struct array_dims array_dims;
  struct array_dims {
    ptrdiff_t stride;
    ptrdiff_t lower_bound;
    ptrdiff_t upper_bound;
  };
"""

arraydescr = """
  typedef struct array_{0}d array_{0}d;
  struct array_{0}d {{
    void *base_addr;
    size_t offset;
    ptrdiff_t dtype;
    struct array_dims dim[{0}];
  }};

"""

def numpy2fortran(ffi, arr):
    """
    Converts Fortran-contiguous NumPy array arr into an array descriptor
    compatible with gfortran to be passed to library routines via cffi.
    """
    if not arr.flags.f_contiguous:
        raise TypeError('needs Fortran order in NumPy arrays')

    ndims = len(arr.shape)
    arrdata = ffi.new('array_{}d*'.format(ndims))
    arrdata.offset = 0

    arrdata.base_addr = ffi.cast('void*', arr.ctypes.data)
    arrdata.dtype = ndims # rank of the array
    arrdata.dtype = arrdata.dtype | (3 << 3) # "3" for float, TODO: allow others
    arrdata.dtype = arrdata.dtype | (arr.dtype.itemsize << 6) # no of bytes

    stride = 1
    for kd in range(ndims):
        arrdata.dim[kd].stride = stride
        arrdata.dim[kd].lower_bound = 1
        arrdata.dim[kd].upper_bound = arr.shape[kd]
        stride = stride*arr.shape[kd]

    return arrdata


def warn(output):
    caller_frame = inspect.currentframe().f_back
    (filename, line_number,
     function_name, lines, index) = inspect.getframeinfo(caller_frame)
    filename = os.path.split(filename)[-1]
    print('')
    print('WARNING {}:{} {}():'.format(filename, line_number, function_name))
    print(output)


def debug(output):
    caller_frame = inspect.currentframe().f_back
    (filename, line_number,
     function_name, lines, index) = inspect.getframeinfo(caller_frame)
    filename = os.path.split(filename)[-1]
    print('')
    print('DEBUG {}:{} {}():'.format(filename, line_number, function_name))
    print(output)


class fortran_module:
    def __init__(self, library, name):
        self.library = library
        self.name = name
        self.methods = []
        self.maxdim = 5  # maximum dimension of arrays
        self.csource = ''
        self.loaded = False

    def __dir__(self):
        return self.methods

    def __getattr__(self, attr):
        # print(attr)
        def method(*args): return self.__call_fortran(attr, *args)
        return method

    def __call_fortran(self, function, *args):
        cargs = []
        for arg in args:
            if isinstance(arg, np.ndarray):
                cargs.append(numpy2fortran(self._mod.ffi, arg))
            else:  # TODO: add pointers to basic types
                raise NotImplementedError('Argument type not understood')
        # GNU specific
        funcname = '__'+self.name+'_MOD_'+function
        func = getattr(self._mod.lib, funcname)
        debug('Calling {}({})'.format(funcname, cargs))
        func(*cargs)

    def cdef(self, csource):  # TODO: replace this by implementing fdef
        """
        Specifies C source with some template replacements:
        {mod} -> compiler module prefix, e.g. for self.name == testmod for GCC:
          void {mod}_func() -> void __testmod_MOD_func()
        """
        # GNU specific
        self.csource += csource.format(mod='__'+self.name+'_MOD')
        debug('C signatures are\n' + self.csource)

    def fdef(self, fsource):
        raise NotImplementedError('will allow to use Fortran signatures')

    def compile(self, verbose=False):
        """
        Compiles a Python extension as an interface for the Fortran module
        """
        ffi = FFI()

        structdef = arraydims
        for kdim in range(1, self.maxdim+1):
            structdef += arraydescr.format(kdim)

        ffi.cdef(structdef+self.csource)
        ffi.set_source('_'+self.name,
                       structdef,
                       libraries=[self.library],
                       library_dirs=['.'],
                       extra_link_args=['-Wl,-rpath=.', '-lgfortran'])

        debug('Compilation starting')
        ffi.compile(verbose=verbose)

    def load(self):
        """
        Loads the Fortran module using the generated Python extension.
        Attention: module cannot be re-/unloaded unless Python is restarted.
        """
        if self.loaded:
            # TODO: add a check if the extension module itself is loaded.
            # Otherwise a new instance of a fortran_module makes you think
            # you can reload the extension module without warning.
            warn('Module cannot be re-/unloaded unless Python is restarted.')

        self._mod = importlib.import_module('_'+self.name)
        self._ffi = self._mod.ffi
        self.methods = []
        ext_methods = dir(self._mod.lib)
        for m in ext_methods:
            mname = re.sub('__.+_MOD_', '', m)  # GNU specific
            self.methods.append(mname)
        self.loaded = True
