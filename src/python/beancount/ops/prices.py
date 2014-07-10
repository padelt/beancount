"""This module has code that can build a database of historical prices at
various times, from which unrealized capital gains and market value can be
deduced.

Prices are deduced from Price entries found in the file, or perhaps
created by scripts (for example you could build a script that will fetch
live prices online and create entries on-the-fly).
"""
import collections

from beancount.core.amount import ONE
from beancount.core import amount
from beancount.core.data import Transaction, Price
from beancount.core import data
from beancount.core import inventory
from beancount.utils import misc_utils
from beancount.parser import printer


def get_last_price_entries(entries, date):
    """Run through the entries until the given date and return the last
    Price entry encountered for each (currency, cost-currency) pair.

    Args:
      entries: A list of directives.
      date: An instance of datetime.date. If None, the very latest price
        is returned.
    Returns:
      A list of price entries.
    """
    price_entry_map = {}
    for entry in entries:
        if date is not None and entry.date >= date:
            break
        if isinstance(entry, Price):
            base_quote = (entry.currency, entry.amount.currency)
            price_entry_map[base_quote] = entry
    return sorted(price_entry_map.values(), key=data.entry_sortkey)


class PriceMap(dict):
    """A price map dictionary.

    The keys include both the set of forward (base, quote) pairs and their
    inverse. In order to determine which are the forward pairs, access the
    'forward_pairs' attribute

    Atttributes:
      forward_pairs: A list of (base, quote) keys for the forward pairs.
    """
    __slots__ = ('forward_pairs')


def build_price_map(entries):

    """Build a price map from a list of arbitrary entries.

    If multiple prices are found for the same (currency, cost-currency) pair at
    the same date, the latest date is kept and the earlier ones (for that day)
    are discarded.

    If inverse price pairs are found, e.g. USD in AUD and AUD in USD, the
    inverse that has the smallest number of price points is converted into the
    one that has the most price points. In that way they are reconciled into a
    single one.

    Args:
      entries: A list of directives, hopefully including some Price and/or
      Transaction entries.
    Returns:
      A dict of (currency, cost-currency) keys to sorted lists of (date, number)
      pairs, where 'date' is the date the price occurs at and 'number' a Decimal
      that represents the price, or rate, between these two
      currencies/commodities. Each date occurs only once in the sorted list of
      prices of a particular key. All of the inverses are automatically
      generated in the price map.
    """
    # Fetch a list of all the price entries seen in the ledger.
    price_entries = [entry
                     for entry in entries
                     if isinstance(entry, Price)]

    # Build a map of exchange rates between these units.
    # (base-currency, quote-currency) -> List of (date, rate).
    price_map = collections.defaultdict(list)
    for price in price_entries:
        base_quote = (price.currency, price.amount.currency)
        price_map[base_quote].append((price.date, price.amount.number))

    # Find pairs of inversed units.
    inversed_units = []
    for base_quote, values in price_map.items():
        base, quote = base_quote
        if (quote, base) in price_map:
            inversed_units.append(base_quote)

    # Find pairs of inversed units, and swallow the conversion with the smaller
    # number of rates into the other one.
    for base, quote in inversed_units:
        bq_prices = price_map[(base, quote)]
        qb_prices = price_map[(quote, base)]
        remove = ((base, quote)
                  if len(bq_prices) < len(qb_prices)
                  else (quote, base))
        base, quote = remove

        remove_list = price_map[remove]
        insert_list = price_map[(quote, base)]
        del price_map[remove]

        inverted_list = [(date, ONE/rate)
                         for (date, rate) in remove_list]
        insert_list.extend(inverted_list)

    # Unzip and sort each of the entries and eliminate duplicates on the date.
    sorted_price_map = PriceMap({
        base_quote: list(misc_utils.uniquify_last(date_rates, lambda x: x[0]))
        for (base_quote, date_rates) in price_map.items()})

    # Compute and insert all the inverted rates.
    forward_pairs = list(sorted_price_map.keys())
    for (base, quote), price_list in list(sorted_price_map.items()):
        sorted_price_map[(quote, base)] = [
            (date, ONE/price) for date, price in price_list]

    sorted_price_map.forward_pairs = forward_pairs
    return sorted_price_map


def normalize_base_quote(base_quote):
    """Convert a slash-separated string to a pair of strings.

    Args:
      base_quote: A pair of strings, the base currency to lookup, and the quote
        currency to lookup, which expresses which units the base currency is
        denominated in. This may also just be a string, with a '/' separator.
    Returns:
      A pair of strings.
    """
    if isinstance(base_quote, str):
        base_quote_norm = tuple(base_quote.split('/'))
        assert len(base_quote_norm) == 2, base_quote
        base_quote = base_quote_norm
    assert isinstance(base_quote, tuple), base_quote
    return base_quote


def _lookup_price_and_inverse(price_map, base_quote):
    """Lookup the (base, quote) tuple in the price map and its inverse.
    If not found, raise an appropriate exception.

    Note: this is meant to be an INTERNAL helper function, use the get_*
    functions to obtain values from a price_map object.

    Args:
      price_map: A price map, which is a dict of (base, quote) -> list of (date,
        number) tuples, as created by build_price_map.
      base_quote: A pair of strings, (base, quote) currencies.
        No normalizatin is done.
    Returns:
      A list of price-dates, if succesful.
    Raises:
      KeyError: If the base_quote and its inverse both weren't able to be looked
      up.
    """
    try:
        return price_map[base_quote]
    except KeyError as exc:
        base, quote = base_quote
        prices = price_map.get((quote, base), None)
        if prices:
            return prices
        else:
            raise exc


def get_all_prices(price_map, base_quote):
    """Return a sorted list of all (date, number) price pairs.

    Args:
      price_map: A price map, which is a dict of (base, quote) -> list of (date,
        number) tuples, as created by build_price_map.
      base_quote: A pair of strings, the base currency to lookup, and the quote
        currency to lookup, which expresses which units the base currency is
        denominated in. This may also just be a string, with a '/' separator.
    Returns:
      A list of (date, Decimal) pairs, sorted by date.

    """
    base_quote = normalize_base_quote(base_quote)
    return _lookup_price_and_inverse(price_map, base_quote)


def get_latest_price(price_map, base_quote):
    """Return the latest price/rate from a prica map for the given base/quote pair.
    This is often used to just get the 'current' price if you're looking at the
    entire set of entries.

    Args:
      price_map: A price map, which is a dict of (base, quote) -> list of (date,
        number) tuples, as created by build_price_map.
    Returns:
      A pair of (date, number), where 'date' is a datetime.date instancea dn
      'number' is a Decimal of the price, or rate, at that date. The date is the
      latest date which we have an available price for in the price map.
    """
    base_quote = normalize_base_quote(base_quote)

    # Handle the degenerate case of a currency priced into its own.
    base, quote = base_quote
    if quote is None or base == quote:
        return (None, ONE)

    # Look up the list and return the latest element. The lists are assumed to
    # be sorted.
    price_list = _lookup_price_and_inverse(price_map, base_quote)
    if price_list:
        return price_list[-1]
    else:
        return None


def get_price(price_map, base_quote, date=None):
    """Return the price as of the given date.

    If the date is unspecified, return the latest price.

    Args:
      price_map: A price map, which is a dict of (base, quote) -> list of (date,
        number) tuples, as created by build_price_map.
      base_quote: A pair of strings, the base currency to lookup, and the quote
        currency to lookup, which expresses which units the base currency is
        denominated in. This may also just be a string, with a '/' separator.
      date: A datetime.date instance, the date at which we want the conversion
        rate.
    Returns:
      A pair of (datetime.date, Decimal) instance. If no price information could
      be found, return (None, None).
    """
    if date is None:
        return get_latest_price(price_map, base_quote)

    base_quote = normalize_base_quote(base_quote)

    # Handle the degenerate case of a currency priced into its own.
    base, quote = base_quote
    if quote is None or base == quote:
        return (None, ONE)

    price_list = _lookup_price_and_inverse(price_map, base_quote)
    index = misc_utils.bisect_right_with_key(price_list, date, key=lambda x: x[0])
    if index == 0:
        return None, None
    else:
        return price_list[index-1]


def convert_amount(price_map, target_currency, amount_):
    """Convert commodities held at a cost that differ from the value currency.

    Args:
      price_map: A price map dict, as created by build_price_map.
      target_currency: A string, the currency to convert to.
      amount_: An Amount instance, the amount to convert from.
    Returns:
      An instance of Amount, or None, if we could not convert it to the target
      currency.
    """
    if amount_.currency != target_currency:
        base_quote = (amount_.currency, target_currency)
        try:
            _, rate = get_latest_price(price_map, base_quote)
            converted_amount = amount.Amount(amount_.number * rate, target_currency)
        except KeyError:
            # If a rate is not found, simply remove the market value.
            converted_amount = None
    else:
        converted_amount = amount_
    return converted_amount
