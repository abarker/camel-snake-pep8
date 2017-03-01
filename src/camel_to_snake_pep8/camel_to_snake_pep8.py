#!/usr/bin/env python2
"""

Refactoring tool to convert camel case to snake case in a Python program in
conformity with the PEP-8 style guide.

Usage: camel_to_snake_pep8.py <packageOrProjectDir> <fileToModify> [<fileToModify> ...]

Note that Python-Rope only supports Python2 for now!  A port is said to be in
progress...

Be careful and look at the changes carefully because Rope will happily rename a
variable to a name that is already in use in the same scope.  For example, a
function argument could be renamed to collide with a preexisting local variable
inside the function.  Make a backup first, and maybe run unittests as the
changes are made.

It is better to make all the changes in one run of the program, since the
program collects all the existing names (per module) before starting in order
to warn about possible collisions.

Collision detection currently only gathers the preexisting names from the
module being modified.  But changes might also be made in other modules when
imports are done.  Collision detection could be even better if it determined
which resources are involved in the change and then combined all those
preexisting names for the preexisting name set to check against.  At the start
of the program it could gather that information for each resource in the
project (using the methods of the rope Project class and others).

"""

from __future__ import print_function, division
import sys
import os
import rope
import re
import difflib
from rope.base.project import Project
from rope.refactor.rename import Rename
from rope.base import worder
from colorama import Fore, Back, Style

change_function_and_method_names = True
change_function_and_method_arguments = True
change_function_and_method_keywords = True
change_assigned_variables = True

banner_width = 78
blue_info_color = Fore.BLUE + Style.BRIGHT

#
# Process command-line arguments.
#

if not len(sys.argv) >= 3:
    print("Usage: camel_to_snake_pep8 <packageOrProjectDir> "
                                      "<fileToModify> [<fileToModify> ...]",
          file=sys.stderr)
    sys.exit(1)

project_dir = sys.argv[1]
project_is_package = False
if os.path.exists(os.path.join(project_dir, "__init__.py")):
    project_is_package = True
fname_list = sys.argv[2:]

#
# Simple utility functions.
#

first_cap_re = re.compile('(.)([A-Z][a-z]+)') # Used in camel_to_snake.
all_cap_re = re.compile('([a-z0-9])([A-Z])')  # Used in camel_to_snake.

def camel_to_snake(name):
    """Convert possible camelcase string to snake case."""
    # From: http://stackoverflow.com/questions/1175208/
    s1 = first_cap_re.sub(r'\1_\2', name)
    return all_cap_re.sub(r'\1_\2', s1).lower()

def get_source_string(fname):
    """Get string versions of the source code in the files with filenames
    passed in.  Returns a dict keyed by the filenames."""
    with open(fname, "r") as source_file:
        source_string = source_file.read()
    return source_string

def color(color, string):
    """Convert a string to a Colorama colorized string."""
    return color + string + Style.RESET_ALL

def print_color(color, *args, **kwargs):
    """Like print, but with a color argument."""
    kwargs2 = kwargs.copy()
    kwargs2["end"] = ""
    print(color, sep="", end="")
    print(*args, **kwargs2)
    print(Style.RESET_ALL, **kwargs)

def print_banner(text, big=False, char="="):
    """Print out the text in a banner."""
    c = blue_info_color
    print_color(c, char * banner_width)
    if big: print_color(c, char * banner_width)
    print_color(c, char * 5, " ", text, " ", char * (banner_width - 7 - len(text)), sep="")
    print_color(c, char * banner_width)
    if big: print_color(c, char * banner_width)
    print()

def filename_to_module_name(fname):
    """Return the module name from a filename.  Not fully qualified for the
    package, though."""
    # TODO: Not sure if this works on subpackages.  What if modules have
    # the same name in different subpackages?

    # Code gives right dotted module paths, but rope doesn't return the
    # full changes description like it does with the shorter name.
    #if project_is_package:
    #    relative_dir = os.path.realpath(os.path.join(project_dir, ".."))
    #else:
    #    relative_dir = os.path.realpath(project_dir)
    relative_dir = os.path.realpath(project_dir)

    abs_fname = os.path.realpath(fname)
    relpath = os.path.relpath(abs_fname, relative_dir)
    assert relpath[-3:] == ".py"
    relpath = relpath[:-3]
    module_name = relpath.replace(os.path.sep, ".")
    return module_name

#
# Functions that do the real work.
#

# Consider also using the Finder object in
# https://github.com/python-rope/rope/blob/master/rope/refactor/occurrences.py
# The Occurrence objects it returns (from generator) have an offset attribute.
# Seems to just run filters on all the names (similar to what is below but
# maybe higher level but maybe not exactly what I want).
#
# There are also the Rename and ChangeOccurrences classes, one of which will
# be used.
# https://github.com/python-rope/rope/blob/master/rope/refactor/rename.py

# Test rename below works, and modifies the variables in file, but the offsets
# become invalid after the changes!  So you'd need to re-read the file each
# time.

def rope_iterate_worder(source_file_name, fun_name_defs=False, fun_arguments=False,
                        fun_keywords=False, assigned_vars=False, unfiltered=False):
    """Get all the names of a given type and their offsets."""
    # Currently based on Worder class:
    # https://github.com/python-rope/rope/blob/master/rope/base/worder.py
    if unfiltered:
        fun_name_defs = True
        fun_arguments = True
        fun_keywords = True
        assigned_vars = True

    source_string = get_source_string(source_file_name)
    w = worder.Worder(source_string)

    possible_changes = []
    upcoming = None
    i = 0
    while True:
        try:
            word = w.get_word_at(i)
        except (ValueError, IndexError):
            break

        if w.is_function_keyword_parameter(i) and fun_keywords:
            possible_changes.append([word, i])

        elif w.is_assigned_here(i) and assigned_vars:
            possible_changes.append([word, i])

        if word == "def":
            upcoming = "def"
        elif word == "class":
            upcoming = "class"
        else:
            if upcoming == "def" and w.is_a_class_or_function_name_in_header(i):
                if fun_name_defs:
                    possible_changes.append([word, i])
                upcoming = None

                try:
                    fun_and_args = w.get_function_and_args_in_header(i)
                except (ValueError, IndexError):
                    fun_and_args = None
                #print("function and args", fun_and_args)

                #try:
                #    fun_offset = w.find_function_offset(i)
                #    lparens, rparens = w.get_word_parens_range(fun_offset)
                #except (ValueError, IndexError):
                #    pass # Doesn't always work...
                #arg_string = source_string[fun_offset:rparens + 1]
                #print("arg string is", arg_string)

        # Move the offset pointer ahead until the recognized word changes.
        break_outer = False
        while True:
            i += 1
            try:
                next_word = w.get_word_at(i)
                if next_word != word:
                    break
            except (ValueError, IndexError):
                break_outer = True
                break
        if break_outer:
            break

    if unfiltered:
        return possible_changes

    # Filter out the possible changes that are already in snake case.
    filtered_changes = []
    for c in possible_changes:
        new_name = camel_to_snake(c[0])
        if new_name == c[0]:
            continue
        c.append(new_name)
        filtered_changes.append(c)
    return filtered_changes

def rope_rename_refactor(project, source_file_name, possible_changes, original_name_set):
    """Query the user about changes to make.  Do at most one change (since
    all the offsets are generated again after a change).  If a change is
    done return true, otherwise return false."""
    # Example refactor at:
    #    https://github.com/python-rope/rope/blob/master/docs/library.rst

    # NOTE alb, Rename(project, resource, offset), where project and offset
    # are described below.  Offset is a character count into a resource,
    # which seems to be a module.  Offset of None refers to the resource itself.

    module_name = filename_to_module_name(source_file_name)
    module = project.find_module(module_name)

    for name, offset, new_name in possible_changes:
        while True:
            changes = Rename(project, module, offset).get_changes(
                                               new_name, docs=True, unsure=None)
            change_string = changes.get_description()

            if new_name in original_name_set:
                print_color(Fore.RED, "Caution: The new name '{0}' already existed"
                        "\nsomewhere in the module before this run of the program made"
                        "\nany changes.  This may or may not cause a name collision."
                        "\nScoping was not taken into account in the analysis.\n".
                        format(new_name))
            # Colorize the description.
            color_new_name = color(Fore.GREEN, new_name)
            color_name = color(Fore.CYAN, name)
            change_string = change_string.replace(name, color_name)
            change_string = change_string.replace(new_name, color_new_name)
            print("Changes are:\n", change_string)

            # Query the user.
            print_color(blue_info_color, "Do the changes? [ync] ", end="")
            yes_no = raw_input("")
            if yes_no == "c":
                print_color(blue_info_color, "Enter a different string: ", end="")
                new_name = raw_input("")
                print()
                continue
            elif yes_no not in ["n", "N"]:
                project.do(changes)
            break
        print()
        print_color(blue_info_color, "-" * banner_width)
        print()
        return True

    return False

def main():
    print_banner("Running camel_to_snake_pep8.")

    print("The default on query replies (with enter) is YES.")
    print("Entering 'c' will query for a different name string.")

    print("\nIt is safer to make all changes to a given module"
          " in the same run of the\nprogram because warnings of"
          " possible collisions will be more accurate.")

    if project_is_package:
        print("\nThe project is detected as a Python package.")
    else:
        print("\nThe project is detected to not be a Python package.")

    print("\nConverting these files:")
    for f in fname_list:
        print("   ", f)

    print_color(blue_info_color, "\nHit enter to begin the refactoring... ", end="")
    raw_input("")
    print()

    # Create a project.
    project = Project(project_dir)

    # Analyze the project.
    print_color(blue_info_color, "Analyzing all the modules in the project,"
                                                           " may be slow...")
    rope.base.libutils.analyze_modules(project) # Analyze all the modules.
    print_color(blue_info_color, "Finished the analysis.", sep="")
    print()


    for filename in fname_list:
        print_banner("Python module name: " + filename_to_module_name(filename))

        original_names_in_module = rope_iterate_worder(filename, unfiltered=True)
        original_name_set = set(c[0] for c in original_names_in_module)
        print("Original names are", list(original_name_set))

        print_banner("Changing variables assigned in the code.")
        while change_assigned_variables:
            possible_changes = rope_iterate_worder(filename, assigned_vars=True)
            if not rope_rename_refactor(project, filename, possible_changes,
                                        original_name_set):
                break

        print_banner("Changing function and method names.")
        while change_function_and_method_names:
            possible_changes = rope_iterate_worder(filename, fun_name_defs=True)
            if not rope_rename_refactor(project, filename, possible_changes,
                                        original_name_set):
                break

        print_banner("Changing function and method keywords.")
        while change_function_and_method_keywords:
            possible_changes = rope_iterate_worder(filename, fun_keywords=True)
            if not rope_rename_refactor(project, filename, possible_changes,
                                        original_name_set):
                break

        print_banner("Changing unassigned function and method arguments.")
        while change_function_and_method_arguments:
            possible_changes = rope_iterate_worder(filename, assigned_vars=True)
            if not rope_rename_refactor(project, filename, possible_changes,
                                        original_name_set):
                break

    project.close()

if __name__ == "__main__":

    main()

