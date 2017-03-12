"""

This is mainly to test that submodules are handled correctly.

"""

from __future__ import print_function, division, absolute_import

import pkg_dir.pkg_subdir.subpkg_module as thisNotCurrentlyChanged

print("In pkg_module.py.")

myNewVar = thisNotCurrentlyChanged.myVar

assert myNewVar == 10

def CamelNamedFun(camelName, another_name):
    numVars = 0

