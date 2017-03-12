
from __future__ import print_function, division, absolute_import

#
# Test collisions due to Rope renaming.
#

def camelFunction(camelArg1, camelArg2, camelArg3, camelArg4, camelArg5):
    """Warning on this is correct, gives error."""
    camel_arg4 = 333
    class snake_class(object):
        camelArg5 = camelArg3
    snake_class.camelArg1 = camelArg1
    snake_class.camelArg3 = snake_class.camelArg1
    snake_class.camelArg3 = camelArg2
    snake_class.camelArg5 = camelArg5
    camelArg4 = 999
    return camel_arg4

a_a = 44
def fF(aA, a, bB, b, cC, c, dD=3, d=a_a): # Test short names and rename to global.
    """Warning is not correct on this, does not actually cause error.
    Resulting code is correct, but `aA` is not converted when warning is heeded."""
    pass

#
# Test collision when the two suggested strings collide.
#

myVar = 5
myVAR = 44

#
# Test changing a for-loop variable.
#

for camelVar in range(3):
    pass

for camelCount, camelVar in enumerate(range(3)):
    pass

#
# Test modifying docs.
#

class _snake_name(object):
    """This is a class that uses `snake_name` as its name to test when `snake_name`
    will be modified by Rope with docs set to change or not."""
    d = {}
    d["snake_name"] = "snake_name" # Danger of using docs modifications!

#
# Test multiple assignment.
#

xX, yY, zZ = 1, 2, 3 # Only the last one, zZ, is modified.

yY = 100 # This change does not cause a problem, though, since Rope also gets above yY.

#
# Test some special case short names.
#

# Names that are all caps and underscores are left unchanged (might be consts).
def _G(_, X, xX, yY, ZZ, _Y, _rR_=__name__):
    pass

