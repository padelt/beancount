"""Loader code. This is the main entry point to load up a file.
"""
import functools
import textwrap
import importlib
import sys
import collections
import re

from beancount.utils import misc_utils
from beancount.core import data
from beancount.parser import parser
from beancount.parser import documents
from beancount.parser import printer
from beancount.ops import pad
from beancount.ops import validation
from beancount.ops import balance
from beancount.ops import prices


LoadError = collections.namedtuple('LoadError', 'fileloc message entry')


def load(filename,
         do_print_errors=False,
         quiet=False,
         parse_method='filename'):
    """Load an input file: open the file and parse it, pad, check and validate it.
    This also optionally prints out the error messages.

    This file provides convenience routines that do all that's necessary to obtain a
    list of entries ready for realization and working with them. This is the most
    common entry point.

    Args:
      filename: the name of the file to be parsed.
      do_print_errors: a boolean, true if this function should format and print out
                       errors. This is only available here because it's a common
                       thing to do with this function.

      quiet: a boolean, if true, the timing of each section of the parsing and
             validation process will be printed out on logging.info.

      parse_method: a string, 'filename' or 'string', that describes the contents
                    of 'filename'.
    Returns:
      A triple of (sorted list of entries from the file, a list of errors
      generated while parsing and validating the file, and a dict of the options
      parsed from the file).
    """

    # Parse the input file.
    if parse_method == 'filename':
        parse_fun = parser.parse
    elif parse_method == 'string':
        parse_fun = parser.parse_string
    else:
        raise NotImplementedError("Method: {}".format(parse_method))
    with misc_utils.print_time('parse', quiet):
        entries, parse_errors, options_map = parse_fun(filename)

    # Transform the entries.
    entries, errors = run_transformations(entries, parse_errors, options_map,
                                          filename, quiet)

    # Validate the list of entries.
    with misc_utils.print_time('validate', quiet):
        valid_errors = validation.validate(entries, options_map)
        errors.extend(valid_errors)

        # FIXME: Check here that the entries haven't been modified, by comparing
        # hashes before and after.

    # Print out the list of errors.
    if do_print_errors and errors:
        print(',----------------------------------------------------------------------')
        printer.print_errors(errors, file=sys.stdout)
        print('`----------------------------------------------------------------------')

    return entries, errors, options_map


def run_transformations(entries, parse_errors, options_map, filename, quiet):
    """Run the various transformations on the entries.

    This is where entries are being synthesized, checked, plugins are run, etc.

    Args:
      entries: A list of directives as read from the parser.
      parse_errors: A list of errors so far.
      options_map: An options dict as read from the parser.
      filename: A string, the name of the file that's just been parsed.
      quiet: A boolean, true if we should be quiet.
    Returns:
      A list of modified entries, and a list of errors, also possibly modified.
    """

    # A list of errors to flatten.
    errors = list(parse_errors)

    # Pad the resulting entries (create synthetic Pad entries to balance checks
    # where desired).
    #
    # Note: I think a lot of these should be moved to plugins!
    with misc_utils.print_time('pad', quiet):
        entries, pad_errors = pad.pad(entries, options_map)
        errors.extend(pad_errors)

    # Add implicitly defined prices.
    with misc_utils.print_time('prices', quiet):
        entries, price_errors = prices.add_implicit_prices(entries, options_map)
        errors.extend(price_errors)

    with misc_utils.print_time('check', quiet):
        entries, check_errors = balance.check(entries, options_map)
        errors.extend(check_errors)

    # Process the document entries and find documents automatically.
    with misc_utils.print_time('documents', quiet):
        # FIXME: Maybe the filename can be passed in through the options_map in
        # order to comply with the interface of all other plugins. Maybe
        # documents can just become yet another plugin...
        entries, doc_errors = documents.process_documents(entries, options_map, filename)
        errors.extend(doc_errors)

    # Ensure that the entries are sorted.
    entries.sort(key=data.entry_sortkey)

    # Process the plugins.
    for plugin_name in options_map["plugin"]:

        # Parse out the option if one was specified.
        mo = re.match('(.*):(.*)', plugin_name)
        if mo:
            plugin_name, plugin_option = mo.groups()
        else:
            plugin_option = None

        # Try to import the module.
        try:
            module = importlib.import_module(plugin_name)
            if hasattr(module, '__plugins__'):
                for function_name in module.__plugins__:
                    callback = getattr(module, function_name)
                    callback_name = '{}.{}'.format(plugin_name, function_name)
                    with misc_utils.print_time(callback_name, quiet):
                        if plugin_option is not None:
                            entries, plugin_errors = callback(entries, options_map,
                                                              plugin_option)
                        else:
                            entries, plugin_errors = callback(entries, options_map)
                        errors.extend(plugin_errors)

        except ImportError as exc:
            # Upon failure, just issue an error.
            errors.append(LoadError(data.FileLocation("<load>", 0),
                                    'Error importing "{}": {}'.format(
                                        plugin_name, str(exc)), None))

    # Ensure that the entries are sorted.
    entries.sort(key=data.entry_sortkey)

    return entries, errors


def loaddoc(fun):
    """A decorator that will load the docstring and call the wrapped function with
    the results."""
    @functools.wraps(fun)
    def wrapper(self):
        contents = textwrap.dedent(fun.__doc__)
        entries, errors, options_map = load(contents,
                                            parse_method='string',
                                            quiet=True)
        return fun(self, entries, errors, options_map)
    wrapper.__doc__ = None
    return wrapper
