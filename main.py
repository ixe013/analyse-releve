#!/usr/bin/env python
import argparse
import csv
import contextlib
from datetime import datetime
import enum
import re
import sys

try:
    import openpyxl
    excel_format_available = True
except ImportError:
    excel_format_available = False

import pdfplumber

class Col(enum.IntEnum):
    DATE_TRANSACTION = 0
    DATE_INSCRIPTION = 1
    DESCRIPTION = 2
    REMISES = 3
    MONTANT = 4

STATEMENT_DATE_PATTERN = re.compile(r"DATE DU.*?Jour\s(\d\d)\s\sMois\s(\d\d)\s\sAnnée\s(\d\d\d\d)")
CARDHOLDER_PATTERN = re.compile(r'[A-Z]+\ [A-Z]+')
EXCHANGE_RATE_PATTERN = re.compile(r'TX:\s+\d+\.\d+$')

HEADERS = [
   "Fichier",
   "Titulaire",
   "Page",
   "Transaction",
   "Inscription",
   "Description",
   "Remise",
   "Montant",
]

def extract_statement_date(pdf):
    text = pdf.pages[0].extract_text_simple()
    match = STATEMENT_DATE_PATTERN.search(text)
    if match:
        day, month, year = match.groups()
        return year, month, day


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


def format_date_with_year(year, column):
    for i in range(len(column)):
        d = datetime.strptime(f"{column[i]} {year}", "%d %m %Y")
        column[i] = d.strftime("%Y-%m-%d")


def extrat_transaction_from_table(filename):
    lines = []
    print(f"📕 Processing {filename}")
    with pdfplumber.open(filename) as pdf:
        try:
            year, month, day = extract_statement_date(pdf)
        except:
            print(f"Impossible d'extraire la date du relevé {filename}", file=sys.stderr)

        for page in pdf.pages:
            print(f"Looking at page {page.page_number}", file=sys.stderr)
            try:
                for cardholder, transactions in detect_transaction_table(page):
                    columns = [column.split("\n") for column in transactions]

                    format_date_with_year(year, columns[Col.DATE_TRANSACTION])
                    format_date_with_year(year, columns[Col.DATE_INSCRIPTION])

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
                            columns[Col.MONTANT][i] = f"-{columns[Col.MONTANT][i].strip('CR')}"
                            columns[Col.REMISES].insert(i, "0,00 %")

                    new_lines = [(filename, cardholder, str(page.page_number)) + line for line in zip(*columns)]
                    lines.extend(new_lines)

            except Exception as e:
                print(f"Error processing page {page.page_number} of {filename}: {e}", file=sys.stderr)

    return lines


@contextlib.contextmanager
def smart_open(filename=None, mode='wb', newline='', encoding='utf-8-sig'):
    if filename and filename != '-':
        fh = open(filename, mode, newline=newline, encoding=encoding)
    else:
        fh = sys.stdout
    try:
        yield fh
    finally:
        if fh is not sys.stdout:
            fh.close()


def output_transactions_to_csv(transactions, output):
    with smart_open(output, 'a') as csvfile:
        spamwriter = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_MINIMAL)

        for transaction in transactions:
            spamwriter.writerow(transaction)


def main():
    parser = argparse.ArgumentParser(prog=sys.argv[0])

    parser.add_argument('-f', '--format', choices=['csv', 'xlsx'], default="csv")
    parser.add_argument('-t', '--headers', action='store_true', default=True)
    parser.add_argument('-o', '--output')

    parser.add_argument('filename', nargs="+")

    args = parser.parse_args()

    if args.format == "xlsx":
        print("Format Excel pas encore supporté", file=sys.stderr)
    else:
        for filename in args.filename:
            transactions = extrat_transaction_from_table(filename)
            if args.headers:
                output_transactions_to_csv([HEADERS], args.output)

            output_transactions_to_csv(transactions, args.output)


if __name__ == '__main__':
   main()
