
from __future__ import print_function, division

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

