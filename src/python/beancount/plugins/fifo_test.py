__author__ = "Martin Blais <blais@furius.ca>"

from beancount import loader
from beancount.parser import cmptest
from beancount.parser import printer


class TestbookFIFO(cmptest.TestCase):

    @loader.load_doc()
    def test_fifo_example(self, entries, errors, __):
        """
          plugin "beancount.plugins.fifo" "Assets:Bitcoin,Income:Bitcoin"

          2015-01-01 open Assets:Bitcoin
          2015-01-01 open Income:Bitcoin
          2015-01-01 open Assets:Bank
          2015-01-01 open Expenses:Something

          2015-09-04 * "Buy some bitcoins"
            Assets:Bank          -1000.00 USD
            Assets:Bitcoin       4.333507 BTC @ 230.76 USD

          2015-09-05 * "Buy some more bitcoins"
            Assets:Bank          -1000.00 USD
            Assets:Bitcoin       4.345747 BTC @ 230.11 USD

          2015-09-20 * "Use some bitcoins from two lots"
            Assets:Bitcoin       -6.000000 BTC @ 230.50 USD
            Expenses:Something
        """

        self.assertEqualEntries("""

          2015-01-01 open Assets:Bitcoin
          2015-01-01 open Income:Bitcoin
          2015-01-01 open Assets:Bank
          2015-01-01 open Expenses:Something

          2015-09-04 * "Buy some bitcoins"
            Assets:Bitcoin  4.333507 BTC {230.76 USD} @ 230.76 USD
            Assets:Bank     -1000.00 USD

          2015-09-05 * "Buy some more bitcoins"
            Assets:Bitcoin  4.345747 BTC {230.11 USD} @ 230.11 USD
            Assets:Bank     -1000.00 USD

          2015-09-20 * "Use some bitcoins from two lots"
            Assets:Bitcoin          -4.333507 BTC {230.76 USD} @ 230.50 USD
            Assets:Bitcoin          -1.666493 BTC {230.11 USD} @ 230.50 USD
            Income:Bitcoin         0.47677955 USD
            Expenses:Something  1383.00000000 USD

        """, entries)

    @loader.load_doc()
    def test_fifo_split_augmenting(self, entries, errors, __):
        """
          plugin "beancount.plugins.fifo" "Assets:Bitcoin,Income:Bitcoin"

          2015-01-01 open Assets:Bitcoin
          2015-01-01 open Income:Bitcoin
          2015-01-01 open Assets:Bank
          2015-01-01 open Expenses:Something

          2015-09-04 *
            Assets:Bank          -1000.00 USD
            Assets:Bitcoin       4.347826 BTC @ 230.00 USD

          2015-09-20 *
            Assets:Bitcoin       -2.000000 BTC @ 231.00 USD
            Expenses:Something

          2015-09-21 *
            Assets:Bitcoin       -2.000000 BTC @ 232.00 USD
            Expenses:Something

          2015-09-22 *
            Assets:Bitcoin       -0.347826 BTC @ 233.00 USD
            Expenses:Something

        """
        self.assertEqualEntries("""

          2015-01-01 open Assets:Bitcoin
          2015-01-01 open Income:Bitcoin
          2015-01-01 open Assets:Bank
          2015-01-01 open Expenses:Something

          2015-09-04 *
            Assets:Bitcoin  4.347826 BTC {230.00 USD} @ 230.00 USD
            Assets:Bank     -1000.00 USD

          2015-09-20 *
            Assets:Bitcoin         -2.000000 BTC {230.00 USD} @ 231.00 USD
            Income:Bitcoin       -2.00000000 USD
            Expenses:Something  462.00000000 USD

          2015-09-21 *
            Assets:Bitcoin         -2.000000 BTC {230.00 USD} @ 232.00 USD
            Income:Bitcoin       -4.00000000 USD
            Expenses:Something  464.00000000 USD

          2015-09-22 *
            Assets:Bitcoin        -0.347826 BTC {230.00 USD} @ 233.00 USD
            Income:Bitcoin      -1.04347800 USD
            Expenses:Something  81.04345800 USD

        """, entries)

    @loader.load_doc()
    def test_fifo_split_reducing(self, entries, errors, __):
        """
          plugin "beancount.plugins.fifo" "Assets:Bitcoin,Income:Bitcoin"

          2015-01-01 open Assets:Bitcoin
          2015-01-01 open Income:Bitcoin
          2015-01-01 open Assets:Bank
          2015-01-01 open Expenses:Something

          2015-09-04 *
            Assets:Bank           -500.00 USD
            Assets:Bitcoin       2.000000 BTC @ 250.00 USD

          2015-09-05 *
            Assets:Bank           -520.00 USD
            Assets:Bitcoin       2.000000 BTC @ 260.00 USD

          2015-09-06 *
            Assets:Bank           -540.00 USD
            Assets:Bitcoin       2.000000 BTC @ 270.00 USD

          2015-09-20 *
            Assets:Bitcoin       -5.000000 BTC @ 280.00 USD
            Expenses:Something

        """

        self.assertEqualEntries("""

          2015-01-01 open Assets:Bitcoin
          2015-01-01 open Income:Bitcoin
          2015-01-01 open Assets:Bank
          2015-01-01 open Expenses:Something

          2015-09-04 *
            Assets:Bitcoin  2.000000 BTC {250.00 USD} @ 250.00 USD
            Assets:Bank      -500.00 USD

          2015-09-05 *
            Assets:Bitcoin  2.000000 BTC {260.00 USD} @ 260.00 USD
            Assets:Bank      -520.00 USD

          2015-09-06 *
            Assets:Bitcoin  2.000000 BTC {270.00 USD} @ 270.00 USD
            Assets:Bank      -540.00 USD

          2015-09-20 *
            Assets:Bitcoin          -2.000000 BTC {250.00 USD} @ 280.00 USD
            Assets:Bitcoin          -2.000000 BTC {260.00 USD} @ 280.00 USD
            Assets:Bitcoin          -1.000000 BTC {270.00 USD} @ 280.00 USD
            Income:Bitcoin      -110.00000000 USD
            Expenses:Something  1400.00000000 USD

        """, entries)

    @loader.load_doc(expect_errors=True)
    def test_fifo_split_partial_failure(self, entries, errors, __):
        """
          plugin "beancount.plugins.fifo" "Assets:Bitcoin,Income:Bitcoin"
          plugin "beancount.plugins.auto_accounts"

          2015-09-04 *
            Assets:Bank           -500.00 USD
            Assets:Bitcoin       2.000000 BTC @ 250.00 USD

          2015-09-20 *
            Assets:Bitcoin      -2.000001 BTC @ 280.00 USD
            Expenses:Something
        """
        self.assertRegexpMatches(errors[0].message, "Could not match position")

    @loader.load_doc(expect_errors=True)
    def test_fifo_split_complete_failure(self, entries, errors, __):
        """
          plugin "beancount.plugins.fifo" "Assets:Bitcoin,Income:Bitcoin"
          plugin "beancount.plugins.auto_accounts"

          2015-09-04 *
            Assets:Bank           -500.00 USD
            Assets:Bitcoin       2.000000 BTC @ 250.00 USD

          2015-09-20 *
            Assets:Bitcoin      -2.000000 BTC @ 280.00 USD
            Expenses:Something

          2015-09-21 *
            Assets:Bitcoin      -0.000001 BTC @ 280.00 USD
            Expenses:Something
        """
        self.assertRegexpMatches(errors[0].message, "Could not match position")

    @loader.load_doc(expect_errors=True)
    def test_fifo_bad_configuration(self, entries, errors, __):
        """
          plugin "beancount.plugins.fifo" "Assets:Bitcoin"
        """
        self.assertRegexpMatches(errors[0].message, "Invalid configuration")
