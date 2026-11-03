"""One CSV writer for every export: UTF-8 with BOM for Excel, and no cell a spreadsheet would run as a formula."""
import csv
import io


def safe(value):
    return "'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')) else value


def amount(cents):
    return '' if cents is None else f'{cents / 100:.2f}'


def csv_bytes(header, rows):
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(header)
    for row in rows:
        writer.writerow(['' if v is None else safe(v) for v in row])
    return out.getvalue().encode('utf-8-sig')
