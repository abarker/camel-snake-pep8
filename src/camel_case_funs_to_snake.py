#!/usr/bin/env python2
"""

Simple refactoring tool to convert camel case to snake case.  Doesn't
automatically handle scopes, etc., just queries the user about each possible
change.  All changes are global, across all the files on command line.

"""

# TODO: Consider a better way to query.  List all occurrences of each
# variable that would be modified, across all files, and accept or
# reject the lot.  Seems a lot safer.  Easy mod, BUT you need to change
# the actual files on each iteration.

# TODO consider using this program:
# https://github.com/gristlabs/asttokens/blob/master/asttokens/line_numbers.py
# It seems to do at least some of the AST calculations.

from __future__ import print_function, division
import sys
import rope
import re

if not sys.argv[1]:
    raise Exception("Program takes filename arguments of the files to process.")

fname_list = sys.argv[1:]

print("Converting files '{0}'.  Hit 'n' to reject change; 'y' or enter accepts.\n".
        format(fname_list))

substitution_dict = {}

#def camel_to_snake(name):
#    """Convert possible camelcase string to snake case."""
#    new_name = ""
#    for letter in name:
#        if letter.isupper():
#            letter = "_" + letter.lower()
#        new_name = new_name + letter
#    return new_name

first_cap_re = re.compile('(.)([A-Z][a-z]+)')
all_cap_re = re.compile('([a-z0-9])([A-Z])')
def camel_to_snake(name):
    """Convert possible camelcase string to snake case."""
    # From: http://stackoverflow.com/questions/1175208/
    s1 = first_cap_re.sub(r'\1_\2', name)
    return all_cap_re.sub(r'\1_\2', s1).lower()

def query_conversion(name, line):
    """Query user for each possible conversion, showing the two lines."""
    converted_line = line.replace(name, substitution_dict[name])
    print("\nOld line:\n", line)
    print("Replace with:\n", converted_line)
    yes_no = input("Do the conversion? [yn] ")
    if yes_no in ["y", "Y", ""]:
        print("Change made.")
        line = converted_line
    print()
    return line

def get_source_strings(fname_list):
    source_dict = {} # Dict of source strings keyed by filenames.
    for fname in fname_list:
        with open(fname, "r") as source_file:
            source_dict[fname] = source_file.read()
    return source_dict

def convert_line_and_col_to_char_offset(line, col, line_split_source):
    """Convert a line and char number to an absolute character offset in the source."""
    # AST line numbers start at one.
    char_count = 0
    for curr_line in range(len(line_split_source)):
        if curr_line + 1 == line:
            char_count += col
            break
        char_count += len(line_split_source[curr_line])
    return char_count


#
# Test rope stuff.
#

# TODO below fun seems to work great!  Just use this to find the names and
# offsets, and then call the refactor to make the changes.  Can get all names
# list from AST, too, and maybe refuse to clobber... rope might not be smart
# enough... could add some disambiguating suffix or something...

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

# Create a project.
from rope.base.project import Project
from rope.refactor.rename import Rename
project = Project('.')

possible_fun_defs_to_change = []

def rope_iterate_worder():
    """Get all the names of a given type and their offsets."""
    # Currently based on Worder:
    # https://github.com/python-rope/rope/blob/master/rope/base/worder.py
    source_string_dict = get_source_strings(fname_list)
    fname = fname_list[0]
    source_string = source_string_dict[fname]
    #print("Source string is", source_string)

    possible_fun_defs_to_change = []

    from rope.base import worder
    w = worder.Worder(source_string)
    i = 0
    upcoming = None
    while True:
        try:
            word = w.get_word_at(i)
        except (ValueError, IndexError):
            break
        #print("===>", word)

        if w.is_function_keyword_parameter(i):
            #print("keyword here", word)
            pass
        elif w.is_assigned_here(i):
            #print("var being assigned", word)
            pass

        if word == "def":
            upcoming = "def"
        elif word == "class":
            upcoming = "class"
        else:
            if upcoming == "def" and w.is_a_class_or_function_name_in_header(i):
                offset = i
                #print(i, word, upcoming)
                possible_fun_defs_to_change.append([word, i])
                upcoming = None
                #fun_and_args = w.get_function_and_args_in_header(offset)

                #print("function and args", fun_and_args)

                # Can find offset to end of function, so can locate the fun
                # args!  May want to query, though.
                try:
                    fun_offset = w.find_function_offset(offset)
                    lparens, rparens = w.get_word_parens_range(fun_offset)
                except (ValueError, IndexError):
                    pass # Doesn't always work...
                arg_string = source_string[fun_offset:rparens + 1]
                #print("arg string is", arg_string)


        #primary_range = w.get_primary_range(i)
        #print("primary range is", source_string[primary_range[0]:primary_range[1]])

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
    return possible_fun_defs_to_change

def rope_rename_refactor():
    source_string_dict = get_source_strings(fname_list)
    source_string = source_string_dict.items()[0][1]
    print("Source string is", source_string)
    # NOTE Rope only supports Python2 for now!!!  Port said to be in progress...
    # Example modified from:
    #    https://github.com/python-rope/rope/blob/master/docs/library.rst

    # NOTE alb, Rename(project, resource, offset), where project and offset
    # are described below.  Offset seems to be a character count into a resource,
    # which seems to be a module.  Offset of None refers to the resource itself.

    # Working with files to create a module
    #mod1 = project.root.create_file('mod1.py')
    #mod1.write('a_var = 10\n')

    # Alternatively you can use `generate` module.
    # Creating modules and packages using `generate` module
    #from rope.contrib import generate
    #pkg = generate.create_package(project, 'pkg')
    #mod2 = generate.create_module(project, 'mod2', pkg)
    #mod2.write('import mod1\nprint mod1.a_var\n')

    # We can use `Project.find_module` for finding modules, too
    # TODO how to load package?  Load all modules?
    module = project.find_module('external_program_calls')

    # Performing rename refactoring on `mod1.a_var`
    for name, offset in possible_fun_defs_to_change:
        new_name = camel_to_snake(name)
        if new_name == name:
            continue
        changes = Rename(project, module, offset).get_changes(new_name)
        yes_no = raw_input("Do the changes? ")
        if yes_no not in ["n", "N"]:
            project.do(changes)
        return False

    return True
    #u'new_var = 10\n'
    #mod2.read()
    #u'import mod1\nprint mod1.new_var\n'

    # Undoing rename refactoring
    #project.history.undo()
    #mod1.read()
    #u'a_var = 10\n'
    #mod2.read()
    #u'import mod1\nprint mod1.a_var\n'

    # Cleaning up

while True:
    possible_fun_defs_to_change = rope_iterate_worder()
    print("possible changes:")
    print(possible_fun_defs_to_change)

    if rope_rename_refactor():
        break

project.close()
sys.exit(0)

def example_rope_rename_refactor():
    # NOTE Rope only supports Python2 for now!!!  Port said to be in progress...
    # Example modified from:
    #    https://github.com/python-rope/rope/blob/master/docs/library.rst

    # NOTE alb, Rename(project, resource, offset), where project and offset
    # are described below.  Offset seems to be a character count into a resource,
    # which seems to be a module.  Offset of None refers to the resource itself.

    # Create a project.
    from rope.base.project import Project
    project = Project('.')

    # Working with files to create a module
    mod1 = project.root.create_file('mod1.py')
    mod1.write('a_var = 10\n')

    # Alternatively you can use `generate` module.
    # Creating modules and packages using `generate` module
    from rope.contrib import generate
    pkg = generate.create_package(project, 'pkg')
    mod2 = generate.create_module(project, 'mod2', pkg)
    mod2.write('import mod1\nprint mod1.a_var\n')

    # We can use `Project.find_module` for finding modules, too
    assert mod2 == project.find_module('pkg.mod2')

    # Performing rename refactoring on `mod1.a_var`
    from rope.refactor.rename import Rename
    changes = Rename(project, mod1, 1).get_changes('new_var')
    project.do(changes)
    mod1.read()
    #u'new_var = 10\n'
    mod2.read()
    #u'import mod1\nprint mod1.new_var\n'

    # Undoing rename refactoring
    project.history.undo()
    mod1.read()
    #u'a_var = 10\n'
    mod2.read()
    #u'import mod1\nprint mod1.a_var\n'

    # Cleaning up
    pkg.remove()
    mod1.remove()   # alb note, this actually removes the file
    project.close()

#rope_rename_refactor()

#
# Test AST stuff.
#

def ast_get_names(source_string, fname):
    """The AST can be used, but no line numbers."""
    # http://stackoverflow.com/questions/33554036/how-to-get-all-variable-and-method-names-used-in-script
    # The AST nodes are documented here:
    # https://greentreesnakes.readthedocs.io/en/latest/nodes.html#function-and-class-definitions
    line_split_source_string = source_string.splitlines()

    import ast
    root = ast.parse(source_string, fname)
    # Try lineno and col_offset attributes on below...
    fun_defs = []
    all_names = []
    assigned_names = []
    for node in ast.walk(root):
        if isinstance(node, ast.FunctionDef):
            absolute_offset = convert_line_and_col_to_char_offset(node.lineno,
                                                                  node.col_offset,
                                                                  line_split_source_string)
            fun_name_and_position = [node.name, node.lineno, node.col_offset, absolute_offset]
            arguments_node = node.args
            fun_args = []
            for arg in arguments_node.args:
                fun_args.append([arg.arg, arg.lineno, arg.col_offset])
            print(fun_args)
            fun_name_and_position.append(fun_args)
            fun_defs.append(fun_name_and_position)

        if isinstance(node, ast.Name):
           all_names.append([node.id, node.lineno, node.col_offset])

        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
           assigned_names.append([node.id, node.lineno, node.col_offset])

    print("\nfun_defs:")
    for f in fun_defs:
        print("   ", f)

    print("\nassigned_names:")
    for n in assigned_names:
        print("   ", n)
    return fun_defs

source_string_dict = get_source_strings(fname_list)
for fname, source_string in source_string_dict.items():
    names = ast_get_names(source_string, fname)

#
# Back to simple method....
#

#
# Collect all the changes that might need to be made.
#

for filename in fname_list:
    with open(filename) as f:
        for line in f:
            stripped_line = line.strip()
            if not stripped_line.startswith("def "):
                continue
            #print("stripped line starting with def is", stripped_line)
            stripped_line = stripped_line[4:]
            split_stripped_line = stripped_line.split("(")
            if len(split_stripped_line) < 2:
                continue
            fun_name = split_stripped_line[0]
            if not fun_name.isidentifier(): # Only Python 3!
                continue
            #print("Found a function name", fun_name)
            new_fun_name = camel_to_snake(fun_name)
            if fun_name == new_fun_name:
                continue
            substitution_dict[fun_name] = new_fun_name
            #print("New name is", substitution_dict[fun_name])

#
# Query whether to do the substitutions.
#

print()
for filename in fname_list:
    with open(filename) as f:
        with open("zzztmpfile" + filename, "w") as outfile:
            for line in f:
                for name in substitution_dict:
                    if name in line:
                        print("="*60)
                        print("Found occurrence of name '{0}'".format(name))
                        line = query_conversion(name, line)
                print(line, file=outfile, end="")
        print("="*60)


