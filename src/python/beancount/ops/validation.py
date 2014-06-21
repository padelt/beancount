"""
Sanity checks.
(Note that these don't have anything to do with 'Balance' directives.
"""
from os import path
import collections

from beancount.core import account_types
from beancount.core import data
from beancount.core.data import Open, Close, Balance, Transaction, Document
from beancount.core import data
from beancount.core import getters
from beancount.core import inventory
from beancount.utils import misc_utils


# An error from one of the checks.
ValidationError = collections.namedtuple('ValidationError', 'fileloc message entry')


def validate_inventory_booking(entries):
    """Validate that no position at cost is allowed to go negative.

    This routine checks that when a posting reduces a position, existing or not,
    that the subsequent inventory does not result in a position with a negative
    number of units. A negative number of units would only be required for short
    trades of trading spreads on futures, and right now this is not supported.
    It would not be difficult to support this, however, but we want to be strict
    about it, because being pedantic about this is otherwise a great way to
    detect user data entry mistakes.

    Args:
      entries: A list of directives.
    Returns:
      A list of errors.
    """
    errors = []

    balances = collections.defaultdict(inventory.Inventory)
    for entry in entries:
        if not isinstance(entry, data.Transaction):
            continue

        for posting in entry.postings:
            # Update the balance of each posting on its respective account
            # without allowing booking to a negative position, and if an error
            # is encountered, catch it and return it.
            running_balance = balances[posting.account]
            try:
                running_balance.add_position(posting.position, allow_negative=False)
            except ValueError as e:
                errors.append(
                    ValidationError(
                        posting.entry.fileloc,
                        e,
                        posting.entry))

    return errors


def validate_open_close(entries):
    """Check constraints on open and close directives themselves.

    This method checks two kinds of constraints:

    1. An open or a close directive may only show up once for each account. If a
       duplicate is detected, an error is generated.

    2. Close directives may only appears if an open directive has been seen
       previous (chronologically).

    3. The date of close directives must be strictly greater than their
      corresponding open directive.

    Args:
      entries: A list of directives.
    Returns:
      A list of new errors, if any were found.

    """
    errors = []
    open_map = {}
    close_map = {}
    for entry in entries:

        if isinstance(entry, Open):
            if entry.account in open_map:
                errors.append(
                    ValidationError(
                        entry.fileloc,
                        "Duplicate open directive for {}.".format(entry.account),
                        entry))
            else:
                open_map[entry.account] = entry

        elif isinstance(entry, Close):
            if entry.account in close_map:
                errors.append(
                    ValidationError(
                        entry.fileloc,
                        "Duplicate close directive for {}.".format(entry.account),
                        entry))
            else:
                try:
                    open_entry = open_map[entry.account]
                    if entry.date <= open_entry.date:
                        errors.append(
                            ValidationError(
                                entry.fileloc,
                                "Internal error: closing date for {} "
                                "appears before opening date.".format(entry.account),
                                entry))
                except KeyError:
                    errors.append(
                        ValidationError(
                            entry.fileloc,
                            "Unopened account {}is being closed.".format(entry.account),
                            entry))

                close_map[entry.account] = entry

    return errors





# def validate_duplicate_balances(entries):

# def validate_transactions_on_closed(entries):



def validate_open_close__old(entries, accounts):
    """Check that open and close directives are not duplicated.

    Open and Close directives may only show up once per account. Balance is
    unique for each date. There are more. Return a list of errors on non-unique
    entries.

    """

    open_map = {}
    close_map = {}
    check_errors = []

    def check_one(entry, account):
        """Check a single entry."""
        open = open_map.get(account)
        if open is None or entry.date < open.date:
            check_errors.append(
                ValidationError(
                    entry.fileloc,
                    "Unknown account {} (or perhaps wrong date?).".format(account),
                    entry))

        close = close_map.get(account)
        if close is not None and entry.date > close.date:
            check_errors.append(
                ValidationError(entry.fileloc,
                                "Entry after account {} closed.".format(account),
                                entry))

    # Check all entries for missing open directives and references to accounts
    # which haven't been opened.
    for entry in entries:
        if isinstance(entry, Transaction):
            for posting in entry.postings:
                check_one(entry, posting.account)

        elif isinstance(entry, Open):
            account = entry.account
            if account in open_map:
                check_errors.append(
                    ValidationError(entry.fileloc,
                                    "Duplicate open entry for {}.".format(account),
                                    entry))
            else:
                open_map[account] = entry

        elif isinstance(entry, Close):
            account = entry.account
            if account in close_map:
                check_errors.append(
                    ValidationError(entry.fileloc,
                                    "Duplicate close entry for {}.".format(account),
                                    entry))
            else:
                close_map[account] = entry

        elif isinstance(entry, Balance):
            if entry.account in accounts:
                # The account is an account with transactions; check the fast
                # path.
                check_one(entry, entry.account)
            else:
                # Parent accounts with subaccounts. Check that there exist at
                # least one sub-account that is currently open for the check,
                # where the check is valid.
                error_entry = None
                for account, open in open_map.items():
                    if not account.startswith(entry.account):
                        continue
                    if entry.date >= open.date:
                        close = close_map.get(account)
                        if close is None or entry.date <= close.date:
                            error_entry = None
                            break
                        else:
                            error_entry = close
                    else:
                        error_entry = open

                if error_entry:
                    if isinstance(error_entry, Open):
                        check_errors.append(
                            ValidationError(error_entry.fileloc,
                                            ("Unknown account {} (or perhaps wrong "
                                             "date?).".format(error_entry.account)),
                                            error_entry))
                    else:
                        assert isinstance(error_entry, Close)
                        check_errors.append(
                            ValidationError(error_entry.fileloc,
                                            "Entry after account {} closed.".format(
                                                error_entry.account),
                                            error_entry))

        # Documents are allowed to show up after closure, as they may be received after.
        elif hasattr(entry, 'account') and not isinstance(entry, Document):
            check_one(entry, entry.account)

    # Check to make sure that all accounts parsed have a corresponding open directive.
    for account in accounts:
        if account not in open_map:
            check_errors.append(
                ValidationError(data.FileLocation('<validate_open_close>', 0),
                                "No open directive for account {}.".format(account),
                                None))

    return check_errors, open_map, close_map


def validate_unused_accounts(entries, accounts):
    """Find the list of accounts referred to by non-open entries,
    and check that against the total list of accounts. Accounts which are only
    referred to by open entries are probably unused."""

    # Find all the accounts referenced by entries which are not Open, and the
    # open directives for error reporting below.
    open_map = {}
    referenced_accounts = set()
    for entry in entries:
        if isinstance(entry, Open):
            open_map[entry.account] = entry
            continue
        referenced_accounts.update(
            misc_utils.get_tuple_values(entry, account_types.is_valid_account_name))

    # Unreferenced accounts are unused accounts.
    unused_accounts = accounts - referenced_accounts

    # Create a list of suitable errors, with the location of the spurious Open
    # directives.
    return [ValidationError(open_map[account].fileloc,
                            "Unused account {}.".format(account),
                            open_map[account])
            for account in unused_accounts]


def validate_currency_constraints(entries):
    """Check that each account has currencies within its declared constraints."""

    open_map = {entry.account: entry
                for entry in misc_utils.filter_type(entries, Open)}

    errors = []
    for entry in misc_utils.filter_type(entries, Transaction):
        for posting in entry.postings:
            try:
                open_entry = open_map[posting.account]
                valid_currencies = open_entry.currencies
            except KeyError:
                valid_currencies = []

            if not valid_currencies:
                continue
            if posting.position.lot.currency not in valid_currencies:
                errors.append(ValidationError(
                    entry.fileloc,
                    "Invalid currency {} for account '{}'.".format(
                        posting.position.lot.currency, posting.account),
                    entry))

    return errors


def validate_documents_paths(entries):
    """Check that all filenames in Document entries are absolute filenames."""

    return [ValidationError(entry.fileloc, "Invalid relative path for entry.", entry)
            for entry in misc_utils.filter_type(entries, Document)
            if not path.isabs(entry.filename)]


def validate(entries):
    """Perform all the standard checks on parsed contents."""

    accounts = getters.get_accounts(entries)

    # Check for negative amounts at cost.
    booking_errors = validate_inventory_booking(entries)

    # Check the validity of open close directives.
    open_close_errors, _, _ = validate_open_close(entries, accounts)




    # Check for unused accounts.
    unused_errors = validate_unused_accounts(entries, accounts)

    # Validate open/close directives and accounts referred outside of those.
    check_errors, _, _ = validate_open_close__old(entries, accounts)

    # Check the currency constraints.
    constraint_errors = validate_currency_constraints(entries)

    # Sanity checks for documents.
    doc_errors = validate_documents_paths(entries)

    return (booking_errors +
            open_close_errors +

            unused_errors +
            check_errors +
            constraint_errors +
            doc_errors)



# FIXME: TODO - check that there are no duplicates on open entries.
# FIXME: TODO - check again that all transactions balance
# FIXME: TODO - check posting entries
# FIXME: TODO - check the parent entries
