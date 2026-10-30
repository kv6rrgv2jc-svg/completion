from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from app.db import connect, ensure_schema


@dataclass(frozen=True)
class SheetTemplate:
    order_id: int
    sku: int
    qty_available: int
    qty_requested: int


TEMPLATE_FIELDS = {
    "order_id": ["Order ID", "Заказ", "Номер заказа", "order_id"],
    "sku": ["SKU", "Артикул", "Номенклатура"],
    "qty_available": ["Можно отгрузить"],
    "qty_requested": ["Кол-во", "Количество"],
}


def detect_template(headers: Iterable[str]) -> SheetTemplate:
    indices: dict[str, int] = {}
    normalized_headers = [header.strip() for header in headers]
    for key, candidates in TEMPLATE_FIELDS.items():
        index = next(
            (i for i, header in enumerate(normalized_headers) if header in candidates),
            None,
        )
        if index is None:
            raise ValueError(
                f"Missing required column for {key}: expected one of {candidates}"
            )
        indices[key] = index
    return SheetTemplate(
        order_id=indices["order_id"],
        sku=indices["sku"],
        qty_available=indices["qty_available"],
        qty_requested=indices["qty_requested"],
    )


def parse_int(value: str) -> int:
    cleaned = value.strip().replace(" ", "")
    if not cleaned:
        return 0
    return int(float(cleaned))


def import_sheet(csv_path: str, db_path: str, uploaded_at: str | None = None) -> None:
    timestamp = uploaded_at or datetime.now(timezone.utc).isoformat()
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        headers = next(reader)
        template = detect_template(headers)
        rows = list(reader)

    orders: dict[str, dict[str, object]] = {}
    items: list[dict[str, object]] = []
    for row in rows:
        order_id = row[template.order_id].strip()
        sku = row[template.sku].strip()
        qty_available = parse_int(row[template.qty_available])
        qty_requested = parse_int(row[template.qty_requested])
        if not order_id or not sku:
            continue

        order_state = orders.setdefault(
            order_id, {"can_pick": True, "uploaded_at": timestamp}
        )
        if qty_available < qty_requested:
            order_state["can_pick"] = False

        items.append(
            {
                "order_id": order_id,
                "sku": sku,
                "qty_requested": qty_requested,
                "qty_available": qty_available,
                "qty_requested_original": qty_requested,
                "qty_available_original": qty_available,
            }
        )

    connection = connect(db_path)
    ensure_schema(connection)
    cursor = connection.cursor()
    cursor.execute("BEGIN")
    try:
        for order_id, payload in orders.items():
            cursor.execute(
                """
                INSERT INTO orders (id, uploaded_at, can_pick)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    uploaded_at = excluded.uploaded_at,
                    can_pick = excluded.can_pick
                """,
                (
                    order_id,
                    payload["uploaded_at"],
                    1 if payload["can_pick"] else 0,
                ),
            )
        # Each imported order is a complete snapshot of its current items.
        # Replace only orders present in this upload, in the same transaction.
        for order_id in orders:
            cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        for item in items:
            cursor.execute(
                """
                INSERT INTO order_items (
                    order_id,
                    sku,
                    qty_requested,
                    qty_available,
                    qty_requested_original,
                    qty_available_original
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item["order_id"],
                    item["sku"],
                    item["qty_requested"],
                    item["qty_available"],
                    item["qty_requested_original"],
                    item["qty_available_original"],
                ),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
