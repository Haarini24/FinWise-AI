
from database import get_connection
from datetime import date


def add_transaction(
    business_id,
    transaction_type,
    amount,
    category_id,
    description,
    transaction_date=None,
    payment_method="Other"
):
    """Add a new business income or expense."""

    if transaction_type not in ("Income", "Expense"):
        raise ValueError("Transaction type must be Income or Expense.")

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        raise ValueError("Amount must be a valid number.")

    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    transaction_date = transaction_date or date.today().isoformat()

    connection = get_connection()

    try:
        if category_id is not None:
            category = connection.execute("""
                SELECT id FROM categories
                WHERE id = ?
                AND business_id = ?
                AND category_type = ?
            """, (category_id, business_id, transaction_type)).fetchone()

            if category is None:
                raise ValueError(
                    "Selected category does not match this business and transaction type."
                )

        cursor = connection.execute("""
            INSERT INTO transactions (
                business_id,
                category_id,
                transaction_type,
                amount,
                description,
                transaction_date,
                payment_method
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            business_id,
            category_id,
            transaction_type,
            amount,
            description,
            transaction_date,
            payment_method
        ))

        connection.commit()
        return cursor.lastrowid

    finally:
        connection.close()


def get_transactions(business_id):
    """Get all transactions for a business."""

    connection = get_connection()

    try:
        rows = connection.execute("""
            SELECT
                t.id,
                t.business_id,
                t.category_id,
                t.transaction_type,
                t.amount,
                t.description,
                t.transaction_date,
                t.payment_method,
                c.category_name
            FROM transactions t
            LEFT JOIN categories c
                ON t.category_id = c.id
            WHERE t.business_id = ?
            ORDER BY t.transaction_date DESC, t.id DESC
        """, (business_id,)).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def update_transaction(
    transaction_id,
    business_id,
    transaction_type,
    amount,
    category_id,
    description,
    transaction_date,
    payment_method="Other"
):
    """Update an existing transaction."""

    if transaction_type not in ("Income", "Expense"):
        raise ValueError("Invalid transaction type.")

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        raise ValueError("Amount must be a valid number.")

    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    connection = get_connection()

    try:
        if category_id is not None:
            category = connection.execute("""
                SELECT id FROM categories
                WHERE id = ?
                AND business_id = ?
                AND category_type = ?
            """, (category_id, business_id, transaction_type)).fetchone()

            if category is None:
                raise ValueError("Invalid category for this transaction.")

        cursor = connection.execute("""
            UPDATE transactions
            SET
                transaction_type = ?,
                amount = ?,
                category_id = ?,
                description = ?,
                transaction_date = ?,
                payment_method = ?
            WHERE id = ? AND business_id = ?
        """, (
            transaction_type,
            amount,
            category_id,
            description,
            transaction_date,
            payment_method,
            transaction_id,
            business_id
        ))

        connection.commit()
        return cursor.rowcount > 0

    finally:
        connection.close()


def delete_transaction(transaction_id, business_id):
    """Delete a transaction belonging to a business."""

    connection = get_connection()

    try:
        cursor = connection.execute("""
            DELETE FROM transactions
            WHERE id = ? AND business_id = ?
        """, (transaction_id, business_id))

        connection.commit()
        return cursor.rowcount > 0

    finally:
        connection.close()
