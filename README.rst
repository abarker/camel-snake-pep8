camel-snake-pep8
================

A refactoring tool to help convert camel case to snake case and vice versa in a
Python program, in conformity with the PEP-8 style guide.  It uses/abuses
Python-Rope to find and perform the changes.  The program interactively
displays proposed changes and the code diffs that would result from the change.
It queries the user as to whether or not to accept the changes.

The program does not do all the changes for full PEP-8 naming compliance, but
it does most of them.  It currently does not recognize unpacked assignments to
tuples very well, and it does not try to modify any names in the context of
import statements (though Rope will indirectly change some names in import
statements if they are renamed elsewhere).

Note that a formatting program such as autopep8 (which is pip installable) can
be used to automatically fix many syntactical and spacing issues, but those
programs do not rename variables.  If such a program is also used it should be
done as a separate step, and some testing should be done between running the
two programs to help isolate any problems which might be introduced.

* **Use this software at your own risk.** This program has various features to
  try to avoid introducing errors in renaming, but correctness cannot be
  guaranteed.  Always make a backup copy of any project before running this
  program on it.  The program has been used a few times with good results, but
  does not currently have formal tests.

  Rope is not perfect, so check your results and look at the warnings issued.
  Rope can have problems with changing names which are imported from different
  modules, especially with "import ... as", so it might be a good idea to
  change all names which appear in such statements by hand.

* Mostly tested on Ubuntu Linux but should also work on Windows.

Installing and using
--------------------

To install using pip, run::

   pip install camel-snake-pep8 --upgrade

A recent version of Rope is recommended for Python 3 compatibility.

The program is a single module, and can also be downloaded and run directly as
``python camel_snake_pep8.py``, provided the dependencies (colorama and rope)
are installed.

Usage::

      camel-snake-pep8 <projectDir> <moduleToModify> [<moduleToModify> ...]

If the module arguments are omitted the program will gather all the ``.py``
files in the ``<projectDir>`` directory, and recursively for any subpackages
if the directory has an ``__init__.py`` file.  If all arguments are omitted
then the current directory is assumed to be the main project directory.

The program can be used to refactor either Python 2 or Python 3 code.  **Run
the program installed in the same version of Python as the code that is being
modified.** That is, if the code being refactored is Python 2 code then run the
program installed in Python 2, and similarly for Python 3.

Note that Rope currently only has limited support for Python 3 type hinting.

As an example, to change all the Python files in a package with one subpackage
go to the package root directory and type::

    camel-snake-pep8

or, equivalently::

    camel-snake-pep8 . *.py */*.py

If individual modules to modify are listed be sure to also include the paths to
any subpackage modules, subsubpackage modules, etc., which are to be modified
on the same line.  Note that any faulty code in the same directory as the files
to be modified may cause Rope to fail, since Rope looks at those also (and may
modify them secondary to a change in a selected file).

The program can be stopped at any time with ``^C``.  But note that it is better
to make all the changes in one run of the program. That is because the program
collects and saves all the names in modules to change, before any changes are
made, in order to give warnings about possible name collisions.

If you want to quickly convert a (copy of a) full project at once to see what
the results would be, two command-line options are provided.  The option
``--yes-to-all`` runs the program as if the user had entered "y" to all queries.
The option ``--yes-no-default`` runs the program as if the user just hit return,
giving the default action (which is to accept changes without warnings and
reject others).  The latter is safer, but in either case running without
reviewing the changes may result in some changes that are unintended.

How it works
------------

This program goes through each file character by character, keeping the
character offset value.  This offset is passed to Python-Rope to detect
variables to possibly rename.  The program queries the user about proposed
changes and makes any user-approved changes.  Python-Rope is also used to do
the renaming.

The names and offsets from a module file are all re-calculated after each
change, since offsets can change with each modification.  The running time is
nevertheless not bad for interactive use.  Variable names for rejected name
changes --- which keep the original variable name --- are temporarily renamed
to have a magic string appended to them.  This is so the program knows the name
has been reviewed and should be retained.  This magic string is then globally
removed from all the files after all the possible changes are processed.  If
the program halts abnormally (such that the ``finally`` of a ``try`` is not
executed) some of those magic strings may still be present.

Warnings and theory
-------------------

The program tries to make the refactoring as safe as possible, since bugs
introduced by bad renaming can be difficult to find.  One of the main dangers
with renaming operations is name collisions.

One type of name collision occurs because Rope will happily rename a variable
to a name that is already in use in the same scope.  For example, a function
parameter could be renamed to collide with a preexisting local variable inside
the function.  Here is an example:

.. code:: python

   def f(camelArg):
       camelArg = 555
       camel_arg = 444
       return camelArg

If the change of the parameter ``camelArg`` to ``camel_arg`` is accepted
(despite the warning that will be issued) the new function will return 444
instead of the previous value 555.  The camel-snake-pep8 program will issue a
warning since the new name previously existed in the module before any changes
were made (i.e, before any changes by the current run of the program).

Another type of name collision is when the renaming itself causes two distinct
names like ``myVar`` and ``myVAR`` to map to a common new name ``my_var``.  In
this case, a warning is given if a name change that was accepted (on the
current run of the program) already mapped a different name to that same new
name.

Warnings are issued for possible situations which may lead to a collision -- or
may not, since scoping is not taken into account in the analysis.  The default
query reply, such as when the user just hits "enter" each time, is to accept
the change when no warning is given and reject the change when a warning is
given.  Many of the changes with warnings will actually be safe, but before
accepting one the displayed diffs for the change (and possibly the files
themselves) should be carefully inspected to be sure.  As an alternative, a
different name entirely can be tried by hitting ``c`` in response to the query.

After all the changes are made the program does an analysis looking for
potential problems, and warnings are issued for any that are found.  No scoping
is taken into account so many of these warnings are probably false alarms.  To
be cautious, though, the warnings should still be checked to see what is
causing them.

Another problem comes when Rope changes the name of a variable assigned in a
module, but then fails to also change an import statement from another module
which imports that variable from the first module.  Similarly, Rope cannot
resolve some attribute assignments.  Both of these kinds of problems will
generate warnings after all the changes have been made.

To summarize: all names per module are saved before any changes, and all names
per module are saved after all the changes.  The name mappings are all saved.
A warning is given on mapping a name into a name that pre-existed in a module.
A warning is also given for a mapping that collides with a previous mapping
(i.e., is not one-to-one).  After all the changes, the places where preimages
of accepted-change mappings still exist are warned about.  Similarly, places
where the images of rejected-change mappings still exist are warned about.

    Rough "proof" of reasonable safety for changes without warnings, assuming
    that Python-Rope does the name replacements correctly (which it doesn't
    always do, e.g., class attributes it cannot resolve).

    1.  The camel case strings that this program would change to snake case strings
    without issuing a warning (and vice versa) are disjoint sets of names.

    2.  If no occurrences of the new, proposed name exist in any file where changes
    are made then no warning will be given and all the instances of the old
    name will be converted to the new one.  No name collisions can occur
    because the new name did not exist in any of those files in the first
    place.  Any variables which end up with the same name already had the same
    name in the first place.

    Of course since Python is dynamic and has introspection there will always
    be cases where the rename substitutions fail (such as modifying the globals
    dict).  Rope is also not perfect, and fails to make some changes which it
    should make for semantic equivalence.  Most of these latter errors will at
    least cause a warning to be generated after all the changes have been
    applied.

License
=======

Copyright (c) 2017 by Allen Barker.  MIT license, see the file LICENSE for more
details.

