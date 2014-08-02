"""Base class for all reports classes.

Each report class should be able to render a filtered list of entries to a
variety of formats. Each report has a name, some command-line options, and
supports some subset of formats.
"""
import argparse
import io
import re

from beancount.reports import table
from beancount.parser import options
from beancount.core import realization


class ReportError(Exception):
    "Error that occurred during report generation."


class Report:
    """Base class for all reports.

    Attributes:
      names: A list of strings, the various names of this report. The first name
        is taken to be the authoritative name of the report; the rest are
        considered aliases.
      parser: The parser for the command's arguments. This is used to raise errors.
      args: An object that contains the values of this command's parsed arguments.
    """

    # The names of this report. Must be overridden by derived classes.
    names = None

    def __init__(self, args, parser):
        self.parser = parser
        self.args = args

    @classmethod
    def from_args(cls, argv=None):
        """A convenience method used to create an instance from arguments.

        This creates an instance of the report with default arguments. This is a
        convenience that may be used for tests. Our actual script uses subparsers
        and invokes add_args() and creates an appropriate instance directly.

        Args:
          argv: A list of strings, command-line arguments to use to construct tbe report.
        Returns:
          A new instace of the report.
        """
        parser = argparse.ArgumentParser()
        cls.add_args(parser)
        return cls(parser.parse_args(argv or []), parser)

    @classmethod
    def add_args(cls, parser):
        """Add arguments to parse for this report.

        Args:
          parser: An instance of argparse.ArgumentParser.
        """
        # No-op.

    @classmethod
    def get_supported_formats(cls):
        """Enumerates the list of supported formats, by inspecting methods of this object.

        Returns:
          A list of strings, such as ['html', 'text'].
        """
        formats = []
        for name in dir(cls):
            mo = re.match('render_([a-z0-9]+)$', name)
            if mo:
                formats.append(mo.group(1))
        return sorted(formats)

    def render(self, entries, errors, options_map, output_format, file=None):
        """Render a report of filtered entries to any format.

        This function dispatches to a specific method.

        Args:
          entries: A list of directives to render.
          errors: A list of errors that occurred during processing.
          options_map: A dict of options, as produced by the parser.
          output_format: A string, the name of the format.
          file: The file to write the output to.
        Returns:
          If no 'file' is provided, return the contents of the report as a
          string.
        Raises:
          ReportError: If the requested format is not supported.
        """
        try:
            render_method = getattr(self, 'render_{}'.format(output_format or
                                                             self.default_format))
        except AttributeError:
            raise ReportError("Unsupported format: '{}'".format(output_format))

        outfile = io.StringIO() if file is None else file
        result = render_method(entries, errors, options_map, outfile)
        assert result is None, "Render method must write to file."
        if file is None:
            return outfile.getvalue()

    __call__ = render


class TableReport(Report):
    """A base class for reports that supports automatic conversions from Table."""

    default_format = 'text'

    def generate_table(self, entries, errors, options_map):
        """Render the report to a Table instance.

        Args:
          entries: A list of directives to render.
          errors: A list of errors that occurred during processing.
          options_map: A dict of options, as produced by the parser.
        Returns:
          An instance of Table, that will get converted to another format.
        """
        raise NotImplementedError

    def render_text(self, entries, errors, options_map, file):
        table_ = self.generate_table(entries, errors, options_map)
        table.generate_table(table_, file, 'text')

    def render_html(self, entries, errors, options_map, file):
        table_ = self.generate_table(entries, errors, options_map)
        table.generate_table(table_, file, 'html')

    def render_htmldiv(self, entries, errors, options_map, file):
        table_ = self.generate_table(entries, errors, options_map)
        table.generate_table(table_, file, 'htmldiv')

    def render_csv(self, entries, errors, options_map, file):
        table_ = self.generate_table(entries, errors, options_map)
        table.generate_table(table_, file, 'csv')


class RealizationMeta(type):
    """A metaclass for reports that render a realization.

    The main use of this metaclass is to allow us to create report classes with
    render_real_*() methods that accept a RealAccount instance as the basis for
    producing a report.

    RealAccount can be expensive to build, and may be pre-computed and kept
    around to generate the various reports related to a particular filter of a
    subset of transactions, and it would be inconvenient to have to recalculate
    it every time we need to produce a report. In particular, this is the case
    for the web interface: the user selects a particular subset of transactions
    to view, and can then click to the various reports related to this subset of
    transactions. This is why this is useful.

    The classes generated with this metaclass respond to the same interface as
    the regular report classes, so that if invoked from the command-line, it
    will automatically build the realization from the given set of entries. This
    metaclass looks at the class' existing render_real_*() methods and generate
    the corresponding render_*() methods automatically.
    """

    # Note: I'm not a big fan of metaclass magic, but this use case is squarely
    # relevant for it, so I'm using it.
    def __new__(cls, name, bases, namespace):
        new_type = super(RealizationMeta, cls).__new__(cls, name, bases, namespace)

        # Go through the methods of the new type and look for render_real() methods.
        new_methods = {}
        for attr, value in new_type.__dict__.items():
            mo = re.match('render_real_(.*)', attr)
            if not mo:
                continue

            # Make sure that if an explicit version of render_*() has already
            # been declared, that we don't override it.
            render_function_name = 'render_{}'.format(mo.group(1))
            if render_function_name in new_type.__dict__:
                continue

            # Define a render_*() method on the class.
            def forward_method(self, entries, errors, options_map, file, fwdfunc=value):
                account_types = options.get_account_types(options_map)
                real_root = realization.realize(entries, account_types)
                return fwdfunc(self, real_root, options_map, file)
            forward_method.__name__ = render_function_name
            new_methods[render_function_name] = forward_method

        # Update the type with the newly defined methods..
        for name, value in new_methods.items():
            setattr(new_type, name, value)

        return new_type


def get_all_reports():
    """Return all report classes.

    Returns:
      A list of all available report classes.
    """
    from beancount.reports import misc_reports
    from beancount.reports import holdings_reports
    from beancount.reports import balance_reports
    return (misc_reports.__reports__ +
            holdings_reports.__reports__ +
            balance_reports.__reports__)
