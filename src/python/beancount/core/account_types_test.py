import unittest

from beancount.core import account_types


class TestAccountTypes(unittest.TestCase):

    def test_basics(self):
        self.assertEqual(5, len(account_types.DEFAULT_ACCOUNT_TYPES))
        self.assertTrue(account_types.DEFAULT_ACCOUNT_TYPES is not None)

    def test_get_account_sort_function(self):
        account_names_input = [
            "Expenses:Toys:Computer",
            "Income:US:Intel",
            "Income:US:ETrade:Dividends",
            "Equity:OpeningBalances",
            "Liabilities:US:RBS:MortgageLoan",
            "Equity:NetIncome",
            "Assets:US:RBS:Savings",
            "Assets:US:RBS:Checking"
        ]
        account_names_expected = [
            "Assets:US:RBS:Checking",
            "Assets:US:RBS:Savings",
            "Liabilities:US:RBS:MortgageLoan",
            "Equity:NetIncome",
            "Equity:OpeningBalances",
            "Income:US:ETrade:Dividends",
            "Income:US:Intel",
            "Expenses:Toys:Computer",
        ]
        account_names_actual = sorted(
            account_names_input,
            key=account_types.get_account_sort_function(account_types.DEFAULT_ACCOUNT_TYPES))
        self.assertEqual(account_names_expected, account_names_actual)

    def test_get_account_type(self):
        self.assertEqual("Assets",
                         account_types.get_account_type("Assets:US:RBS:Checking"))
        self.assertEqual("Assets",
                         account_types.get_account_type("Assets:US:RBS:Savings"))
        self.assertEqual("Liabilities",
                         account_types.get_account_type("Liabilities:US:RBS:MortgageLoan"))
        self.assertEqual("Equity",
                         account_types.get_account_type("Equity:NetIncome"))
        self.assertEqual("Equity",
                         account_types.get_account_type("Equity:OpeningBalances"))
        self.assertEqual("Income",
                         account_types.get_account_type("Income:US:ETrade:Dividends"))
        self.assertEqual("Income",
                         account_types.get_account_type("Income:US:Intel"))
        self.assertEqual("Expenses",
                         account_types.get_account_type("Expenses:Toys:Computer"))
        self.assertEqual("Invalid",
                         account_types.get_account_type("Invalid:Toys:Computer"))

    def test_is_valid_account_name(self):
        is_valid = account_types.is_valid_account_name
        self.assertTrue(is_valid("Assets:US:RBS:Checking"))
        self.assertTrue(is_valid("Equity:OpeningBalances"))
        self.assertTrue(is_valid("Income:US:ETrade:Dividends-USD"))
        self.assertTrue(is_valid("Assets:US:RBS"))
        self.assertTrue(is_valid("Assets:US"))
        self.assertFalse(is_valid("Assets"))
        self.assertFalse(is_valid("Invalid"))
        self.assertFalse(is_valid("Other"))
        self.assertFalse(is_valid("Assets:US:RBS*Checking"))
        self.assertFalse(is_valid("Assets:US:RBS:Checking&"))
        self.assertFalse(is_valid("Assets:US:RBS:checking"))
        self.assertFalse(is_valid("Assets:us:RBS:checking"))

    def test_is_root_account(self):
        for types in (None, account_types.DEFAULT_ACCOUNT_TYPES):
            for account_name, expected in [
                    ("Assets:US:RBS:Checking", False),
                    ("Equity:OpeningBalances", False),
                    ("Income:US:ETrade:Dividends-USD", False),
                    ("Assets", True),
                    ("Liabilities", True),
                    ("Equity", True),
                    ("Income", True),
                    ("Expenses", True),
                    ("_invalid_", False),
            ]:
                self.assertEqual(
                    expected,
                    account_types.is_root_account(account_name, types))

        self.assertTrue(account_types.is_root_account('Invalid'))
        self.assertFalse(account_types.is_root_account(
            'Invalid', account_types.DEFAULT_ACCOUNT_TYPES))

    OPTIONS = {'name_assets'      : 'Assets',
               'name_liabilities' : 'Liabilities',
               'name_equity'      : 'Equity',
               'name_income'      : 'Income',
               'name_expenses'    : 'Expenses'}

    def test_is_account_categories(self):
        for account_name, expected in [
                ("Assets:US:RBS:Savings", True),
                ("Liabilities:US:RBS:MortgageLoan", True),
                ("Equity:OpeningBalances", True),
                ("Income:US:ETrade:Dividends", False),
                ("Expenses:Toys:Computer", False),
        ]:
            self.assertEqual(
                expected,
                account_types.is_balance_sheet_account(
                    account_name, account_types.DEFAULT_ACCOUNT_TYPES))

            self.assertEqual(
                not expected,
                account_types.is_income_statement_account(
                    account_name, account_types.DEFAULT_ACCOUNT_TYPES))
