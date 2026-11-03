"""Additive visual assets and idempotent board requests; existing data is untouched."""
def create_visual_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS product_photos (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      sku_id INTEGER UNIQUE REFERENCES inventory_skus(id) ON DELETE CASCADE,
      product_id INTEGER UNIQUE REFERENCES catalog_products(id) ON DELETE CASCADE,
      component_id INTEGER UNIQUE REFERENCES catalog_components(id) ON DELETE CASCADE,
      content BLOB NOT NULL, mime TEXT NOT NULL CHECK(mime IN ('image/png','image/jpeg')),
      width INTEGER NOT NULL, height INTEGER NOT NULL,
      revision TEXT NOT NULL, updated_at TEXT NOT NULL,
      CHECK((sku_id IS NOT NULL)+(product_id IS NOT NULL)+(component_id IS NOT NULL)=1))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS board_requests (
      request_key TEXT PRIMARY KEY,
      order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
      signature TEXT NOT NULL, created_at TEXT NOT NULL)''')
