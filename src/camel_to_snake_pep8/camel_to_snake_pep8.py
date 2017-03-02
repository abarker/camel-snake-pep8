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

.. note::

    Proof of reasonable safety for changes without warnings or user modifications
    and assuming that Python-Rope does the replacement correctly for the scope, etc.

    1. Camel case strings and snake case are disjoint sets of names.

    2. If no instances of the new snake case string exist in any file where
    changes are made then all the corresponding camel case strings will be
    converted to that value.  No name collisions can occur, and variables which
    end up with the same name had the same name in the first place.

    Of course since Python is dynamic and has introspection there will always
    be cases where the substitutions fail (such as modifying the globals dict).
    But for most cases it should be safe.

    Many of the changes with warnings will also be safe, but before accepting
    them users should carefully inspect the changes (and possibly the files
    themselves) to be sure.  As an alternative, a slightly different snake case
    name can be tried by hitting ``c`` on the query.

    Possible problems can also arise from cases where Rope cannot resolve a
    name to change and the change is skipped.

"""

from __future__ import print_function, division
import sys
import os
import rope
import re
import difflib
import itertools

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
# Dict for saving original names in files.
#

original_names_sets = {} # Original names in files, keyed by realpath to the files.
modified_modules_set = set() # The realpaths of modified modules.

def get_original_names_set(filename):
    original_names_in_module = rope_iterate_worder(filename, unfiltered=True)
    original_name_set = set(c[0] for c in original_names_in_module)
    return original_name_set

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
# Temporary renaming for rejected changes.
#

# TODO: big problem with basic design here... it is almost impossible for a user
# to reject a change!  Everything is re-calculated each time, after a refactor.
# The offset may change, and the name may be accepted for change somewhere else!
# But if we keep a LIST it should presumably encounter them in the same sequence
# for each type of modification, since finding them is sequential.  But refactors
# can change many things, such as the names and offsets and file locations...
#
# Only real solution: change to some magic name, such as append a weird string to
# everything that should stay the same.  Then reject changes to those vars.  After,
# you just go through everything (save all files which have been modified as in dict
# for warnings) and remove that magic.  Note that these names also need to be UNIQUE,
# so have a counter increment for each one and paste that on the end, too.

REJECTED_CHANGE_MAGIC_COOKIE = "_XxX_CamelToSnake_PreserveName_XxX_"
change_reject_counter = 0 # Make the temporary names unique.

def create_rejected_change_preserve_name(name):
    global change_reject_counter
    change_reject_counter += 1
    return name + REJECTED_CHANGE_MAGIC_COOKIE + str(change_reject_counter)

def remove_rejected_change_magic_cookies(modified_modules_set):
    """Remove the magic cookie strings for rejected changes, for all modules
    in `modified_modules_set`."""
    for fname in modified_modules_set:
        with open(fname) as f:
            file_string = f.read()

        with open(fname, "w") as f:
            f.write(restore_text(file_string))

def restore_text(text):
    # TODO compile it
    remove_cookie = REJECTED_CHANGE_MAGIC_COOKIE + r"\d+"
    text = re.sub(remove_cookie, "", text)
    return text

#
# Simple utility functions.
#

first_cap_re = re.compile('(.)([A-Z][a-z]+)') # Used in camel_to_snake.
all_cap_re = re.compile('([a-z0-9])([A-Z])')  # Used in camel_to_snake.

def camel_to_snake(name):
    """Convert possible camelcase string to snake case."""
    # From: http://stackoverflow.com/questions/1175208/
    if all(c.isupper() or c == "_" for c in name): # Regexes fail on all-cap constants.
        return name
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

def unique_everseen(iterable, key=None):
    "List unique elements, preserving order. Remember all elements ever seen."
    # unique_everseen('AAAABBBCCDAABBB') --> A B C D
    # unique_everseen('ABBCcAD', str.lower) --> A B C D
    # https://docs.python.org/3/library/itertools.html#recipes
    seen = set()
    seen_add = seen.add
    if key is None:
        for element in itertools.ifilterfalse(seen.__contains__, iterable):
            seen_add(element)
            yield element
    else:
        for element in iterable:
            k = key(element)
            if k not in seen:
                seen_add(k)
                yield element

#
# Parsing function parameter strings to get parameters without default values.
#

import re, tokenize, keyword
def is_identifier_or_keyword(string):
    """Test whether `string` is a keyword or identifier."""
    # http://stackoverflow.com/questions/2544972/
    #return re.match(tokenize.Name + '$', string) and not keyword.iskeyword(string)
    return re.match(tokenize.Name + '$', string)

def get_identifier_at(source_string, offset):
    """Get the identifier that starts at the given character offset in the
    source string.  Only the beginning offset returns a non-empty string."""
    substring = ""
    curr_offset = offset
    valid_id = False
    while True:
        test_substring = substring + source_string[curr_offset]
        if is_identifier_or_keyword(test_substring):
            valid_id = True
            substring = test_substring
            curr_offset += 1
            continue
        elif valid_id:
            return test_substring
        else:
            return None

def process_param(param, offset):
    """Process a single parameter produced by `get_function_parameter_names`."""
    #print("   arg being processed:", param, offset)

    # Ignore args with default values, since Rope considers them assignments.
    if "=" in param:
        #print("   returning arg:", [])
        return []

    # Strip off any type annotation.
    first_colon_index = param.find(":")
    if first_colon_index >= 0:
        offset += first_colon_index + 1
        param = param[first_colon_index+1:]

    # Strip off beginning whitespace.
    first_non_whitespace_index = len(param) - len(param.lstrip())
    offset += first_non_whitespace_index
    param = param.strip()
    if not param:
        return []
    #print("   returning arg:", param, offset)
    return [param, offset]

def get_function_parameter_names(initial_fun_string, initial_offset):
    """Parse a function string to get the parameter names which are
    not assigned default values (since those are taken care of in the
    variable-assignment group)."""
    fun_string = initial_fun_string
    offset = initial_offset

    if not fun_string:
        return []
    #print("\ninitial fun string is:", fun_string)
    # Do some initial preprocessing.
    index = fun_string.find("(") + 1
    fun_string = fun_string[index:].split("->")[0] # Remove fun name and return type.
    offset += index
    index = 0 # Keep a local index relative to first char of first arg.
    fun_string = fun_string.rstrip()
    #print("fun string is:", fun_string)

    # Make into a list of characters.
    close_paren_index = fun_string.rfind(")")
    fun_string = fun_string[:close_paren_index+1]
    fun_list = [c for c in fun_string]
    assert fun_list[close_paren_index] == ")"
    fun_list[close_paren_index] = "," # Map close paren to comma for consistency later.

    # Turn all unneeded chars into spaces, including all inside any paren nesting.
    simplified_fun_list = []
    paren_count = 0
    for c in fun_list:
        if c in "([{":
            paren_count += 1
            simplified_fun_list.append(" ")
        elif c in ")]}":
            paren_count -= 1
            simplified_fun_list.append(" ")
        elif paren_count > 0 or c == "*":
            simplified_fun_list.append(" ")
        else:
            simplified_fun_list.append(c)
    fun_string = "".join(simplified_fun_list)
    #print("fun string after quashing is:", fun_string)

    # Separate the arguments and call process_arg on them.
    final_name_list = []
    while True:
        comma_index = fun_string.find(",", index)
        #print("index is", index, "comma index is", comma_index)
        if comma_index < 0:
            break
        arg_string = fun_string[index:comma_index]
        #print("passing in arg", arg_string)
        if arg_string:
            name_and_offset = process_param(arg_string, offset + index)
            if name_and_offset:
                final_name_list.append(name_and_offset)
        index = comma_index + 1

    for n in final_name_list:
        for i in range(len(n[0])):
            assert n[0][i] == initial_fun_string[n[1]-initial_offset + i]
    #print("returning args:", final_name_list)
    return final_name_list

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
    """Get all the names of a given type and their offsets.

    Due to how rope works these are split up in an unusual way.  The function arguments
    without default values are parsed out of the string representing the function
    and its arguments.

    fun_name_defs = all function and method defs
    fun_arguments = function arguments which do now have default values
    fun_keywords = function keywords (which duplicate the assigned vars changes)
    assigned_vars = any variables which are assigned, including keyword parameters

    """
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
    fun_args_watch_list = []
    unidentified_words = []
    upcoming = None
    offset = 0
    while True:
        try:
            word = w.get_word_at(offset)
        except (ValueError, IndexError):
            break

        #print("word is:", word, "fun_args_watch_list is:", fun_args_watch_list)
        #if fun_args_watch_list and word == fun_args_watch_list[0]:
        #    print("Got a fun_args_watchlist match with:", word)
        #    print("fun_args_watch_list is:", fun_args_watch_list)
        #    del fun_args_watch_list[0]
        #    if fun_arguments:
        #        possible_changes.append([word, offset])

        if w.is_function_keyword_parameter(offset) and fun_keywords:
            possible_changes.append([word, offset])

        elif w.is_assigned_here(offset) and assigned_vars:
            possible_changes.append([word, offset])

        elif word == "def":
            upcoming = "def"

        elif word == "class":
            upcoming = "class"

        elif upcoming == "def" and w.is_a_class_or_function_name_in_header(offset):
            #print("Got a fun name:", word)
            if fun_name_defs:
                possible_changes.append([word, offset])
            upcoming = None

            try:
                # TODO NOTE: Adding -10 below was needed to make the CURRENT fun name
                # detected match the function and args returned below!  Otherwise,
                # you always got a fun name, but got the string for the one that is
                # ahead in text...  This also makes the offsets match better...
                # NOTE that 4 is the minimum to make them match, and it also makes
                # the offsets match the ones found below in "unidentified" section...
                # But now it has some other weird problems...... keeps repeating
                # certain ones.
                fun_and_args = w.get_function_and_args_in_header(offset-4)
            except (ValueError, IndexError):
                fun_and_args = None
            #print("Fun and args string from rope is:", fun_and_args)
            if fun_arguments:
                fun_args_watch_list = get_function_parameter_names(fun_and_args, offset)
                #print("args for fun", word, "are:", fun_args_watch_list)
                possible_changes += fun_args_watch_list

            #if fun_arguments:
            #    for a in fun_args_watch_list:
            #        possible_changes.append([word, offset])
            #if original_name_set:
            #    for a in fun_args_watch_list:
            #        if not a in original_name_set:
            #            print("Fun arg not found in orig:", a)

            #print("fun_args_watch_list is:", fun_args_watch_list)

            """
            try:
                fun_offset = w.find_function_offset(offset)
                lparens, rparens = w.get_word_parens_range(fun_offset)
            except (ValueError, IndexError):
                pass # Doesn't always work...
            arg_string = source_string[fun_offset:rparens + 1]
            #print("arg string is", arg_string)
            #print("Calculated offsets string from source is:", arg_string)
            #params = w.get_parameters(fun_offset-1, rparens) # FAILS, tried guessing
            #print("Params is:", params)
            """

        else:
            #print("-----> unidentified:", word)
            unidentified_words.append([word, offset])
            # Look for the function arguments anticipated in fun_args_watch_list.
            #if fun_args_watch_list and word == fun_args_watch_list[0][0]:
                # TODO Seems to work, but may mess up if a default value or
                # type annotation contains a name that is the same as the
                # variable it annotates.
                # TODO TODO offsets do not match those calculated from parsing...
                # currently using this code which mostly works, but would be better
                # to use the above code to just calculate them and offsets and stick
                # them in... but the offsets don't match. Consider:
                #
                #    WaterBug = 4
                #    def dummy(EggSalad=WaterBug, WaterBug=4):
                #        pass
                #
                # BUT, cannot have default def params before non-default ones...

                #print("Matched loop pair", [word, offset], "with parsed", fun_args_watch_list[0])
                #possible_changes.append([word, offset])
                #possible_changes.append(fun_args_watch_list[0]) # causes errors in place of above
                #del fun_args_watch_list[0]

        # Move the offset pointer ahead until the recognized word changes.
        break_outer = False
        while True:
            offset += 1
            try:
                next_word = w.get_word_at(offset)
                if next_word != word:
                    break
            except (ValueError, IndexError):
                break_outer = True
                break
        if break_outer:
            break

    if unfiltered:
        #return possible_changes
        return possible_changes + unidentified_words

    # Filter out the possible changes that are already in snake case, save new name.
    filtered_changes = []
    for c in possible_changes:
        name = c[0]
        if REJECTED_CHANGE_MAGIC_COOKIE in name:
            continue
        new_name = camel_to_snake(name)
        if new_name == name:
            continue
        c.append(new_name)
        filtered_changes.append(tuple(c))

    # Remove duplicates and return.
    unique_changes_generator = unique_everseen(filtered_changes)
    filtered_changes = [c for c in unique_changes_generator]
    #print("Deduped filtered changes:", filtered_changes)
    return filtered_changes

def get_renaming_changes(project, module, offset, new_name, name, source_file_name):
    """Get the changes for doing a rename refactoring."""
    try:
        changes = Rename(project, module, offset).get_changes(
                                       new_name, docs=True, unsure=None)
        return changes
    except rope.base.exceptions.RefactoringError:
        print("Error in performing a rename from '{0}' to '{1}' in file"
              "\n   {2}".format(name, new_name, source_file_name))
        #raise
    return None

def rope_rename_refactor(project, source_file_name, possible_changes):
    """Query the user about changes to make.  Do at most one change (since all
    the possible change offsets are generated again after a change).  If a
    change is done return true, otherwise if there are no changes to make
    return false.  Rejected changes are actually made (to include a magic
    cookie) and then are deleted later."""
    # Example refactor at:
    #    https://github.com/python-rope/rope/blob/master/docs/library.rst

    # NOTE alb, Rename(project, resource, offset), where project and offset
    # are described below.  Offset is a character count into a resource,
    # which seems to be a module.  Offset of None refers to the resource itself.

    if not possible_changes:
        return False

    module_name = filename_to_module_name(source_file_name)
    module = project.find_module(module_name)

    for name, offset, new_name in possible_changes:
        #print("DEBUG name, offset, new_name:", name, offset, new_name)
        while True:
            skip_change = False # Skip changes that rope simply cannot resolve.
            changes = get_renaming_changes(project, module, offset, new_name, name,
                                           source_file_name)
            if not changes:
                skip_change = True
                break
            change_string = changes.get_description()
            changed_resources = list(changes.get_changed_resources())

            # Calculate changed resources and possible warnings.
            warning = False
            warning_modules = []
            print("Modules to possibly change are:")
            for c in changed_resources:
                #print("   Path of resource changed:", c.path)
                #print("   Name of resource changed:", c.name)
                #print("   Name of resource changed:", c.real_path)
                print(" ", c.name)
                if c.real_path not in original_names_sets:
                    original_names_sets[c.real_path] = get_original_names_set(c.real_path)
                if new_name in original_names_sets[c.real_path]:
                    warning = True
                    warning_modules.append(c.name)
                modified_modules_set.add(c.real_path)
            print()

            if warning:
                print_color(Fore.RED, "Caution: The new name '{0}' already existed"
                        "\nsomewhere in the module before this run of the program made"
                        "\nany changes.  This may or may not cause a name collision."
                        "\nScoping was not taken into account in the analysis.\n"
                        "\nModules with warnings are:"
                        .format(new_name))
                for m in warning_modules:
                    print_color(Fore.RED, "  ", m)
                print()

            # Colorize the description.
            color_new_name = color(Fore.GREEN, new_name)
            color_name = color(Fore.CYAN, name)
            change_string = change_string.replace(name, color_name)
            change_string = change_string.replace(new_name, color_new_name)
            print("Changes are:\n", change_string)

            # Query the user.
            print_color(blue_info_color, "Do the changes? [ync] ", end="")
            yes_no = raw_input("").strip()
            if yes_no == "c":
                print_color(blue_info_color, "Enter a different string: ", end="")
                new_name = raw_input("")
                print()
                continue
            elif yes_no in "yY" or (yes_no not in "nN" and not warning):
                project.do(changes)
            else:
                skip_change = False
                changes = get_renaming_changes(project, module, offset,
                              create_rejected_change_preserve_name(name),
                              name, source_file_name)
                if not changes:
                    skip_change = True
                    break
                #changes = Rename(project, module, offset).get_changes(
                #                 create_rejected_change_preserve_name(name),
                #                 docs=False, unsure=None)
                project.do(changes)

            break
        if skip_change:
            print("Rope cannot properly resolve the change, or some other Rope problem.")
            print("Skipping the change...\n")
            print_color(blue_info_color, "-" * banner_width)
            print()
            continue
        print()
        print_color(blue_info_color, "-" * banner_width)
        print()
        return True

    return False

def main():
    print_banner("Running camel_to_snake_pep8.")

    print("The default reply for queries (e.g. with enter) when no warning/caution"
          "\nis given is 'y', i.e, do the changes.  If a warning/caution is given then"
          "\nthe default reply is 'n'.")
    print("\nEntering 'c' will query for a changed name string from the user.")

    print("\nIt is safer to make all changes to a given package/module"
          " in the same run of\nthe program because warnings of"
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
    # Does this help refactoring?  See below for related discussion.
    # https://groups.google.com/forum/#!topic/rope-dev/1P8OADQ0DQ4
    print_color(blue_info_color, "Analyzing all the modules in the project,"
                                                           " may be slow...")
    rope.base.libutils.analyze_modules(project) # Analyze all the modules.
    print_color(blue_info_color, "Finished the analysis.", sep="")
    print()

    for filename in fname_list:
        print_banner("Python module name: " + filename_to_module_name(filename), char="%")

        print_banner("Changing variables assigned in the code.")
        while change_assigned_variables:
            possible_changes = rope_iterate_worder(filename, assigned_vars=True)
            if not possible_changes: print("No more variable assignment changes.\n")
            if not rope_rename_refactor(project, filename, possible_changes):
                break

        print_banner("Changing function arguments which do not have defaults.")
        while change_function_and_method_arguments:
            possible_changes = rope_iterate_worder(filename, fun_arguments=True)
            if not possible_changes: print("No more function argument changes.\n")
            if not rope_rename_refactor(project, filename, possible_changes):
                break

        print_banner("Changing function and method names.")
        while change_function_and_method_names:
            possible_changes = rope_iterate_worder(filename, fun_name_defs=True)
            if not possible_changes: print("No more function and method name changes.\n")
            if not rope_rename_refactor(project, filename, possible_changes):
                break

        if not change_assigned_variables: # Redundant when that is also selected.
            print_banner("Changing function and method keywords.")
            while change_function_and_method_keywords:
                possible_changes = rope_iterate_worder(filename, fun_keywords=True)
                if not possible_changes: print("No more function and method keyword changes.\n")
                if not rope_rename_refactor(project, filename, possible_changes):
                    break

    project.close()

if __name__ == "__main__":

    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nProgram exited by keyboard interrupt.", file=sys.stdout)
    finally:
        remove_rejected_change_magic_cookies(modified_modules_set)

