#!/usr/bin/env python2
"""

Refactoring tool to convert camel case to snake case in a Python program in
conformity with the PEP-8 style guide.

Usage: camel_to_snake_pep8.py <packageOrProjectDir> <fileToModify> [<fileToModify> ...]

For example, goto the main source directory (package root) and type:
    camel_to_snake_pep8.py . *.py
Be sure to include submodule Python files, too, if there are any submodules.

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

# TODO: This program could easily be modified to change module names to camel
# case, too.  Currently module names are recognized in rope_iterate_worder, but
# are simply ignored.  Could add a switch to get the class name changes (using
# a snake to camel kind of routine).

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
# Dict for saving original names from files and related.
#

original_names_sets = {} # Original names in files, keyed by realpath to the files.
modified_modules_set = set() # The realpaths of modified modules.

def save_original_names_set(file_realpath, save_dict=original_names_sets):
    """Get the names in the file and save in the `original_names_dict` by default."""
    names_in_module = rope_iterate_worder(file_realpath, unfiltered=True)
    name_set = set(c[0] for c in names_in_module)
    if file_realpath not in original_names_sets:
        save_dict[file_realpath] = name_set

user_rejected_changes_sets = {} # Changes rejected by the user.
rope_rejected_changes_sets = {} # Changes rejected by rope.

def save_rejected_change(realpath_list, change, user=True):
    """Save rejected changes and the corresponding module pathnames.  Offset
    information is removed from the middle of any 3-tuple changes since it does
    not remain valid."""
    if len(change) > 2:
        change = (change[1], change[3])
    for path in realpath_list:
        if user:
            user_rejected_changes_sets[path] = change
        else:
            rope_rejected_changes_sets[path] = change

def analyze_names_in_final_state(module_realpath_list):
    """Analyze the final names in the each module originally passed into the program,
    giving warnings about those which could potentially have problems."""
    print_banner("Doing post-processing analysis on the names.", big=True)
    final_names_sets = {}
    for module_realpath in module_realpath_list:
        save_original_names_set(module_realpath, save_dict=final_names_sets)

    print_banner("User-rejected changes.", char="-")
    # For each rejected change, look for any module which has the suggested name.
    # These might have been missed by Rope or might not be problems at all.
    print("user rejected change sets", user_rejected_changes_sets)
    for path, change_set in user_rejected_changes_sets:
        for change in change_set:
            for module_realpath in module_realpath_list:
                if change[1] in final_names_sets[module_realpath]:
                    print_color(Fore.YELLOW, "A name change from {0} name {1} was"
                            " user-rejected for module\n    {2}\nbut the changed name"
                            " {3} occurs in file\n    {4}".format(change[0], change[1],
                                path, change[1], module_realpath))
    print_banner("Rope-rejected changes.", char="-")
    # TODO: Go over code above again, and extend to rope-rejected, too.
    # Code above currently crashes.  Consider if there are more/better warnings easy to do.

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

    # Separate the arguments and call process_params on them.
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
                # TODO NOTE: Adding -10 below was needed to make the CURRENT
                # fun name detected match the function and args returned below!
                # Otherwise, you always got a fun name, but got the string for
                # the one that is ahead in text...  This also makes the offsets
                # match better...
                #
                # NOTE that -4 is the minimum abs to make them match, and it makes
                # the offsets exactly match the ones found below in
                # "unidentified" section... but I do not know why this works.
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
            unidentified_words.append([word, offset])

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
    # NOTE: Rename(project, resource, offset), where project and offset are
    # described below.  Offset is a character count into a resource, which in
    # this case is a module.  Offset of None refers to the resource itself.
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
            warning = False # Could just use warning_modules list in place of boolean...
            warning_modules = []
            modules_to_change_realpaths = []
            modules_to_change_names = []
            for c in changed_resources:
                #print("   Path of resource changed:", c.path)
                #print("   Name of resource changed:", c.name)
                #print("   Name of resource changed:", c.real_path)
                modules_to_change_realpaths.append(c.real_path)
                modules_to_change_names.append(c.name)
                save_original_names_set(c.real_path)
                if new_name in original_names_sets[c.real_path]:
                    warning = True
                    warning_modules.append(c.name)
                modified_modules_set.add(c.real_path)

            if warning:
                print_color(Fore.YELLOW,
                        "Caution: The new name '{0}' already existed somewhere"
                        "\nin the selected modules before this run of the program made"
                        "\nany changes.  This may or may not cause a name collision."
                        "\nScoping was not taken into account in the analysis.\n"
                        "\nThe modules it was found in are:"
                        .format(new_name))
                for m in warning_modules:
                    print_color(Fore.YELLOW, "   ", m)
                print()

            # Colorize the description and print it out for the user to view.
            color_new_name = color(Fore.GREEN, new_name)
            color_name = color(Fore.CYAN, name)
            change_string = change_string.replace(name, color_name)
            change_string = change_string.replace(new_name, color_new_name)
            print_color(blue_info_color, "Changes are:")
            print("   ", change_string)
            print_color(blue_info_color, "Modules which would be changed:")
            for m in modules_to_change_names:
                print("   ", m)
            print()

            # Query the user.
            print("warning bool is", warning)
            print_color(blue_info_color, "Do the changes? [ync] ", end="")
            yes_no = raw_input("").strip()
            print("yes_no is", yes_no)
            if not yes_no or yes_no not in "cyYnN": # Set default reply.
                if warning: yes_no = "n"
                else: yes_no = "y"
            if yes_no == "c":
                print_color(blue_info_color, "Enter a different string: ", end="")
                new_name = raw_input("")
                print()
                continue
            elif yes_no in "yY":
                print("DOING CHANGES")
                project.do(changes)
            else:
                print("REJECTING CHANGES, putting in dummy")
                skip_change = False
                save_rejected_change(modules_to_change_realpaths, (name, new_name),
                                     user=True)
                changes = get_renaming_changes(project, module, offset,
                              create_rejected_change_preserve_name(name),
                              name, source_file_name)
                if not changes:
                    skip_change = True
                    break
                project.do(changes)

            break
        if skip_change: # Changes skipped because Rope raised an exception.
            print("Rope could not properly resolve the change, or some other Rope problem.")
            print("Skipping the change...\n")
            print_color(blue_info_color, "-" * banner_width)
            print()
            save_rejected_change([source_file_name], (name, new_name), user=False)
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
    print("\nEntering 'c' will query for a changed name string from the user."
          "\nIf the new name is not snake case you will then be queried about changing"
          "\nit to snake case (which you can reject if that is what you want).")

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
        print_banner("Python module name: " + filename_to_module_name(filename),
                     char="%", big=True)

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
        analyze_names_in_final_state(os.path.realpath(f) for f in fname_list)

