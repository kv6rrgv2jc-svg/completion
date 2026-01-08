import sqlite3


def connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            uploaded_at TEXT NOT NULL,
            can_pick INTEGER NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            sku TEXT NOT NULL,
            qty_requested INTEGER NOT NULL,
            qty_available INTEGER NOT NULL,
            qty_requested_original INTEGER NOT NULL,
            qty_available_original INTEGER NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id)
        )
        """
    )
    connection.commit()
