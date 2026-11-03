"""Reusable saved properties, including names retained by inventory history."""
from db import connect


SOURCES = {
    'material': 'SELECT material value FROM parts UNION ALL SELECT material FROM inventory_skus UNION ALL SELECT material FROM catalog_components',
    'part': 'SELECT name value FROM parts UNION ALL SELECT part FROM inventory_skus UNION ALL SELECT name FROM catalog_components',
    'product': 'SELECT name value FROM items UNION ALL SELECT product FROM inventory_skus UNION ALL SELECT name FROM catalog_products',
    'client': "SELECT client value FROM orders UNION ALL SELECT client FROM inventory_movements UNION ALL SELECT json_extract(payload,'$.client') FROM quotations UNION ALL SELECT json_extract(payload,'$.client') FROM sales",
}


def clean(value: str | None) -> str:
    return ' '.join((value or '').split())


def saved_values(property_name: str) -> list[str]:
    """Ignore blanks and combine casing/spacing variants without rewriting records."""
    with connect() as conn:
        rows = conn.execute(SOURCES[property_name]).fetchall()
    values = {}
    for row in rows:
        value = clean(row['value'])
        if value:
            values.setdefault(value.casefold(), value)
    return sorted(values.values(), key=str.casefold)
