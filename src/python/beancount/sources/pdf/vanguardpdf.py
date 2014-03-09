"""HSBC PDF statement importer.
"""
import re
import dateutil

from beancount.imports import importer


class Importer(importer.ImporterBase):

    REQUIRED_CONFIG = {
        'FILE'       : 'Account for filing',
    }

    def import_date(self, filename, match_text):
        """Try to get the date of the report from the filename."""

        mo = re.search('ACCOUNT SUMMARY: (\d\d/\d\d/\d\d\d\d) - (\d\d/\d\d/\d\d\d\d)', match_text)
        assert mo
        return dateutil.parser.parse(mo.group(2)).date()



