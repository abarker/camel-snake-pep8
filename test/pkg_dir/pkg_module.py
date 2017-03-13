"""

This is mainly to test that submodules are handled correctly.

"""

from __future__ import print_function, division, absolute_import

# Failure in renaming on below import, when the variable myVar1
# is changed in subpkg_module but reference in later line isn't.
# But a warning is given after all changes.
import pkg_dir.pkg_subdir.subpkg_module as thisNotCurrentlyChanged

# Failure here, too, when myVar2 is changed in subpkg_module but not
# also changed here where it is imported.  But a warning is given
# after all changes.
from pkg_dir.pkg_subdir.subpkg_module import myVar2 as myVar2

print("In pkg_module.py.")

myNewVar1 = thisNotCurrentlyChanged.myVar1
myNewVar2 = myVar2

assert myNewVar1 == 10
assert myNewVar2 == 11

def CamelNamedFun(camelName, another_name):
    numVars = 0

