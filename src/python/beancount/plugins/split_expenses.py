#!/usr/bin/env python3
"""Split expenses of a Beancount ledger between multiple people.

This plugin is given a list of names. It assumes that any Expenses account whose
components do not include any of the given names are to be split between the
members. It goes through all the transactions and converts all such postings
into multiple postings, one for each member.

For example, given the names 'Martin' and 'Caroline', the following transaction:

  2015-02-01 * "Aqua Viva Tulum - two nights"
     Income:Caroline:CreditCard      -269.00 USD
     Expenses:Accommodation

Will be converted to this:

  2015-02-01 * "Aqua Viva Tulum - two nights"
    Income:Caroline:CreditCard       -269.00 USD
    Expenses:Accommodation:Martin     134.50 USD
    Expenses:Accommodation:Caroline   134.50 USD

After these transformations, all account names should include the name of a
member. You can generate reports for a particular person by filtering postings
to accounts with a component by their name.
"""
__author__ = 'Martin Blais <blais@furius.ca>'

from os import path
import argparse
import copy
import logging
import os
import re
import sys

from beancount import loader
from beancount.core import account
from beancount.core import account_types
from beancount.core import amount
from beancount.core import data
from beancount.core import getters
from beancount.core import interpolate
from beancount.parser import options
from beancount.query import query
from beancount.query import query_render


__plugins__ = ('split_expenses',)


def split_expenses(entries, options_map, config):
    # Validate and sanitize configuration.
    if isinstance(config, str):
        members = config.split()
    elif isinstance(config, (tuple, list)):
        members = config
    else:
        raise RuntimeError("Invalid plugin configuration: configuration for split_expenses "
                           "should be a string or a sequence.")

    acctypes = options.get_account_types(options_map)
    def is_expense_account(account):
        return account_types.get_account_type(account) == acctypes.expenses

    # A predicate to quickly identify if an account contains the name of a
    # member.
    is_individual_account = re.compile('|'.join(map(re.escape, members))).search

    # Existing and previously unseen accounts.
    new_accounts = set()

    # Filter the entries and transform transactions.
    new_entries = []
    for entry in entries:
        if isinstance(entry, data.Transaction):
            new_postings = []
            for posting in entry.postings:
                if (is_expense_account(posting.account) and
                    not is_individual_account(posting.account)):

                    # Split this posting into multiple postings.
                    split_position = copy.copy(posting.position)
                    split_position.set_units(
                        amount.Amount(split_position.units.number / len(members),
                                      split_position.units.currency))

                    for member in members:
                        # Mark the account as new if never seen before.
                        subaccount = account.join(posting.account, member)
                        new_accounts.add(subaccount)

                        # Ensure the modified postings are marked as
                        # automatically calculated, so that the resulting
                        # calculated amounts aren't used to affect inferred
                        # tolerances.
                        meta = posting.meta.copy()
                        meta[interpolate.AUTOMATIC_META] = True

                        # Add a new posting for each member, to a new account
                        # with the name of this member.
                        new_postings.append(
                            posting._replace(meta=meta,
                                             account=subaccount,
                                             position=split_position))
                else:
                    new_postings.append(posting)

            # Modify the entry in-place, replace its postings.
            entry = entry._replace(postings=new_postings)

        new_entries.append(entry)

    # Create Open directives for new subaccounts if necessary.
    oc_map = getters.get_account_open_close(entries)
    open_date = entries[0].date
    meta = data.new_metadata('<split_expenses>', 0)
    open_entries = []
    for new_account in new_accounts:
        if new_account not in oc_map:
            entry = data.Open(meta, open_date, new_account, None, None)
            open_entries.append(entry)

    return open_entries + new_entries, []


def save_query(title, participant, entries, options_map, sql_query, *format_args,
               boxed=True, spaced=False, args=None):
    """Save the multiple files for this query.

    Args:
      title: A string, the title of this particular report to render.
      participant: A string, the name of the participant under consideration.
      entries: A list of directives (as per the loader).
      options_map: A dict of options (as per the loader).
      sql_query: A string with the SQL query, possibly with some placeholders left for
        *format_args to replace.
      *format_args: A tuple of arguments to be formatted into the SQL query string.
        This is provided as a convenience.
      boxed: A boolean, true if we should render the results in a fancy-looking ASCII box.
      spaced: If true, leave an empty line between each of the rows. This is useful if the
        results have a lot of rows that render over multiple lines.
      args: A dummy object with the following attributes:
        output_text: An optional directory name, to produce a text rendering of
          the report.
        output_csv: An optional directory name, to produce a CSV rendering of
          the report.
        currency: An optional currency (a string). If you use this, you should
          wrap query targets to be converted with the pseudo-function
          "CONV[...]" and it will get replaced to CONVERT(..., CURRENCY)
          automatically.
    """
    # Replace CONV() to convert the currencies or not; if so, replace to
    # CONVERT(..., currency).
    replacement = (r'\1'
                   if args.currency is None else
                   r'CONVERT(\1, "{}")'.format(args.currency))
    sql_query = re.sub(r'CONV\[(.*?)\]', replacement, sql_query)

    # Run the query.
    rtypes, rrows = query.run_query(entries, options_map,
                                    sql_query, *format_args,
                                    numberify=True)

    # The base of all filenames.
    filebase = '-'.join(filter(None, [title.replace(' ', '-'), participant]))

    fmtopts = dict(boxed=boxed,
                   spaced=spaced)

    # Output the text files.
    if args.output_text:
        filename_txt = path.join(args.output_text, filebase + '.txt')
        with open(filename_txt, 'w') as file:
            query_render.render_text(rtypes, rrows, options_map['dcontext'],
                                     file, **fmtopts)

    # Output the CSV files.
    if args.output_csv:
        logging.error("CSV rendering i not supported yet.")
        if False:
            filename_csv = path.join(args.output_text, filebase + '.csv')
            with open(filename_csv, 'w') as file:
                query_render.render_csv(rtypes, rrows, options_map['dcontext'],
                                        file, **fmtopts)

    # Write out the query to stdout.
    query_render.render_text(rtypes, rrows, options_map['dcontext'],
                             sys.stdout, **fmtopts)


def get_participants(filename, options_map):
    """Get the list of participants from the plugin configuration in the input file.

    Args:
      options_map: The options map, as produced by the parser.
    Returns:
      A list of strings, the names of participants as they should appear in the
      account names.
    Raises:
      KeyError: If the configuration does not contain configuration for the list
      of participants.
    """
    plugin_options = dict(options_map["plugin"])
    try:
        return plugin_options["beancount.plugins.split_expenses"].split()
    except KeyError:
        raise KeyError("Could not find the split_expenses plugin configuration.")


def main():
    """Generate final reports for a shared expenses on a trip or project.

    For each of many participants, generate a detailed list of expenses,
    contributions, a categorized summary of expenses, and a final balance. Also
    produce a global list of final balances so that participants can reconcile
    between each other.
    """

    logging.basicConfig(level=logging.INFO, format='%(levelname)-8s: %(message)s')
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument('filename', help='Beancount input filename')

    parser.add_argument('-c', '--currency', action='store',
                        help="Convert all the amounts to a single common currency")

    oparser = parser.add_argument_group('Outputs')
    oparser.add_argument('-o', '--output-text', '--text', action='store',
                         help="Render results to text boxes")
    oparser.add_argument('--output-csv', '--csv', action='store',
                         help="Render results to CSV files")

    args = parser.parse_args()

    # Ensure the directories exist.
    for directory in [args.output_text, args.output_csv]:
        if directory and not path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    # Load the input file and get the list of participants.
    entries, errors, options_map = loader.load_file(args.filename)
    participants = get_participants(args.filename, options_map)

    for participant in participants:
        print()
        print("Participant: {}".format(participant))

        save_query("Expenses by category", participant, entries, options_map, r"""
          SELECT
            PARENT(account) AS account,
            CONV[SUM(position)] AS amount
          WHERE account ~ 'Expenses.*\b{}'
          GROUP BY 1
          ORDER BY 2 DESC
        """, participant, boxed=False, args=args)

        save_query("Expenses Detail", participant, entries, options_map, r"""
          SELECT
            date, flag, payee, narration,
            PARENT(account) AS account,
            CONV[position], CONV[balance]
          WHERE account ~ 'Expenses.*\b{}'
        """, participant, args=args)

        save_query("Contributions Detail", participant, entries, options_map, r"""
          SELECT
            date, flag, payee, narration, account, CONV[position], CONV[balance]
          WHERE account ~ 'Income.*\b{}'
        """, participant, args=args)

    save_query("Final Balances", None, entries, options_map, r"""
      SELECT
        GREP('\b({})\b', account) AS participant,
        CONV[SUM(position)] AS balance
      GROUP BY 1
      ORDER BY 2
    """, '|'.join(participants), args=args)

    # FIXME: Make this output to CSV files and upload to a spreadsheet.
    # FIXME: Add a fixed with option. This requires changing adding this to the
    # the renderer to be able to have elastic space and line splitting..


if __name__ == '__main__':
    main()
