#!/usr/bin/env python
import enum
import re
import sys

import pdfplumber

class Col(enum.IntEnum):
    DATE_TRANSACTION = 0
    DATE_INSCRIPTION = 1
    DESCRIPTION = 2
    REMISES = 3
    MONTANT = 4

CARDHOLDER_PATTERN = re.compile(r'[A-Z]+\ [A-Z]+')
EXCHANGE_RATE_PATTERN = re.compile(r'TX:\s+\d+\.\d+$')

def detect_transaction_table(page):
    all_tables = page.find_tables()
    print(f"Found {len(all_tables)}")
    for table in [ t.extract() for t in page.find_tables() ]:
        if not table[0][0].startswith("Transactions effectuées"):
            print(f"Does not start with 'Transactions effectuées' but with {table[0][0]}", file=sys.stderr)
            continue

        match = CARDHOLDER_PATTERN.search(table[0][0])

        if match:
            cardholder = match.group(0)
        else:
            print(f"Can't read cardholder name from {table[0][0]}", file=sys.stderr)
            continue

        if not table[1][0].startswith("Date de transaction"):
            print("Does not start with 'Date de transactions' but with '{table[1][0]}'", file=sys.stderr)
            continue

        if len(table[1]) != 5:
            print(f"The table does not have 5 column but {len(table[1])}", file=sys.stderr)
            continue

        print(f"Returning a table", file=sys.stderr)
        yield cardholder, table[2]


def extrat_transaction_from_table(filename):
    lines = []
    with pdfplumber.open(filename) as pdf:
        for page in pdf.pages:
            print(f"Looking at page {page.page_number}", file=sys.stderr)
            try:
                for cardholder, transactions in detect_transaction_table(page):
                    columns = [column.split("\n") for column in transactions]

                    # If there is at least one entry with the exchange rate
                    # like "2,30 DOLLAR AMERICAIN TX: 1.408695", remove them
                    if len(columns[Col.DATE_TRANSACTION]) < len(columns[Col.DESCRIPTION]):
                        columns[Col.DESCRIPTION] = [
                            item for item in columns[Col.DESCRIPTION]
                            if not EXCHANGE_RATE_PATTERN.search(item)
                        ]

                    # Items with a credit in Col.MONTANT don't have an entry in Col.REMISES
                    # so we remove it and use a minus instead of CR
                    for i, amount in enumerate(columns[Col.MONTANT]):
                        if amount.endswith("CR"):
                            #columns[Col.MONTANT] = f"-{columns[Col.MONTANT][i].strip('CR')}"
                            columns[Col.REMISES].insert(i, "0,00 %")                            
 
                    new_lines = [(cardholder, filename, str(page.page_number)) + line for line in zip(*columns)]
                    lines.extend(new_lines)

            except Exception as e:
                print(f"Could not find a table on page {page.page_number} of {filename}: {e}", file=sys.stderr)

    return lines


def main():
    for filename in sys.argv[1:]:
        transactions = extrat_transaction_from_table(filename)
        for transaction in transactions:
            print(' | '.join(transaction))

    pass

if __name__ == '__main__':
   main()
