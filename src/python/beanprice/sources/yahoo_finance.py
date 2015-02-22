"""Fetch prices from Yahoo Finance.
"""
import datetime
from urllib import request
from urllib import parse

from beancount.core.amount import D


# There is also a web service XML/JSON API:
# http://finance.yahoo.com/webservice/v1/symbols/allcurrencies/quote


class YahooFinancePriceFetcher:

    def __init__(self, symbol, base, quote):
        """Create a price fetcher for Yahoo Finance.

        Args:
          symbol: A string, the name of the instrument, in the Yahoo symbology.
          base: A string, the asset we're actually pricing.
          quote: A string, the currency units of the price quote.
        """
        self._symbol = symbol

        # These are intended to be public.
        self.base = base
        self.quote = quote

    def get_latest_price(self):
        """Return the latest price found for the symbol.

        Returns:
          A Decimal object.
        """
        url = 'http://finance.yahoo.com/d/quotes.csv?s={}&f={}'.format(self._symbol, 'b3b2')
        data = request.urlopen(url).read().decode('utf-8')
        bid_str, ask_str = data.split(',')
        if bid_str == 'N/A' or ask_str == 'N/A':
            return None, None
        bid, ask = D(bid_str), D(ask_str)
        return ((bid + ask)/2, datetime.datetime.now())

    def get_historical_price(self, date):
        """Return the historical price found for the symbol at the given date.

        This should work even if querying for a date that is on a weekend or a
        market holiday.

        Args:
          date: A datetime.date instance.
        Returns:
          A pair of a price (a Decimal object) and the actual date of that price
          (a datetime.date instance).
        """
        # Look back some number of days in the past in order to make sure we hop
        # over national holidays.
        begin_date = date - datetime.timedelta(days=5)
        end_date = date

        # Make the query.
        params = parse.urlencode(sorted({
            's': self._symbol,
            'a': begin_date.month - 1,
            'b': begin_date.day,
            'c': begin_date.year,
            'd': end_date.month - 1,
            'e': end_date.day,
            'f': end_date.year,
            'g': 'd',
            'ignore': '.csv',
        }.items()))
        url = 'http://ichart.yahoo.com/table.csv?{}'.format(params)
        data = request.urlopen(url).read().decode('utf-8').strip()

        lines = data.splitlines()
        assert len(lines) >= 2, "Too few lines in returned data: {}".format(len(lines))

        # Parse the header, find the column for the adjusted close.
        columns = lines[0].split(',')
        index_price = columns.index('Adj Close')
        assert index_price >= 0, "Could not find 'Adj Close' data column."
        index_date = columns.index('Date')
        assert index_date >= 0, "Could not find 'Date' data column."

        # Get the latest data returned.
        most_recent_data = lines[1].split(',')
        close_price = D(most_recent_data[index_price])
        date = datetime.datetime.strptime(most_recent_data[index_date], '%Y-%m-%d').date()

        return (close_price, date)
