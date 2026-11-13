
from database import get_connection


def get_financial_summary(business_id):
    """
    Calculate total income, expenses, profit and profit margin
    for a business using its actual transaction records.
    """

    connection = get_connection()

    try:
        summary = connection.execute("""
            SELECT
                COALESCE(SUM(
                    CASE
                        WHEN transaction_type = 'Income'
                        THEN amount
                        ELSE 0
                    END
                ), 0) AS total_income,

                COALESCE(SUM(
                    CASE
                        WHEN transaction_type = 'Expense'
                        THEN amount
                        ELSE 0
                    END
                ), 0) AS total_expenses

            FROM transactions
            WHERE business_id = ?
        """, (business_id,)).fetchone()

        total_income = float(summary["total_income"])
        total_expenses = float(summary["total_expenses"])

        net_profit = total_income - total_expenses

        if total_income > 0:
            profit_margin = (net_profit / total_income) * 100
        else:
            profit_margin = 0

        return {
            "business_id": business_id,
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expenses, 2),
            "net_profit": round(net_profit, 2),
            "profit_margin": round(profit_margin, 2),
            "currency": "INR"
        }

    finally:
        connection.close()


def get_expense_breakdown(business_id):
    """
    Get business expenses grouped by category.
    """

    connection = get_connection()

    try:
        records = connection.execute("""
            SELECT
                c.category_name,
                SUM(t.amount) AS total_amount,
                COUNT(t.id) AS transaction_count

            FROM transactions t

            JOIN categories c
                ON t.category_id = c.id

            WHERE t.business_id = ?
              AND t.transaction_type = 'Expense'

            GROUP BY c.id, c.category_name

            ORDER BY total_amount DESC
        """, (business_id,)).fetchall()

        total_expenses = sum(
            float(record["total_amount"]) for record in records
        )

        breakdown = []

        for record in records:
            amount = float(record["total_amount"])

            percentage = (
                (amount / total_expenses) * 100
                if total_expenses > 0 else 0
            )

            breakdown.append({
                "category": record["category_name"],
                "amount": round(amount, 2),
                "transaction_count": record["transaction_count"],
                "percentage": round(percentage, 2)
            })

        return {
            "business_id": business_id,
            "total_expenses": round(total_expenses, 2),
            "categories": breakdown,
            "currency": "INR"
        }

    finally:
        connection.close()


def get_transaction_history(business_id, limit=10, transaction_type=None):
    """
    Retrieve recent transactions for a business.
    Optionally filter by Income or Expense.
    """

    if not isinstance(limit, int) or limit < 1 or limit > 100:
        raise ValueError("Limit must be between 1 and 100.")

    if transaction_type is not None:
        transaction_type = transaction_type.capitalize()

        if transaction_type not in ("Income", "Expense"):
            raise ValueError("Transaction type must be Income or Expense.")

    connection = get_connection()

    try:
        query = """
            SELECT
                t.id,
                t.transaction_date,
                t.transaction_type,
                c.category_name,
                t.amount,
                t.description,
                t.payment_method
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.business_id = ?
        """

        params = [business_id]

        if transaction_type:
            query += " AND t.transaction_type = ?"
            params.append(transaction_type)

        query += " ORDER BY t.transaction_date DESC, t.id DESC LIMIT ?"
        params.append(limit)

        cursor = connection.cursor()
        cursor.execute(query, params)

        rows = cursor.fetchall()

        transactions = [
            {
                "id": row["id"],
                "date": row["transaction_date"],
                "type": row["transaction_type"],
                "category": row["category_name"],
                "amount": round(row["amount"], 2),
                "description": row["description"],
                "payment_method": row["payment_method"]
            }
            for row in rows
        ]

        return {
            "business_id": business_id,
            "transaction_count": len(transactions),
            "transactions": transactions,
            "currency": "INR"
        }

    finally:
        connection.close()



def get_budget_status(business_id, budget_month):
    """
    Compare monthly expense budgets with actual expenses.

    budget_month format: YYYY-MM
    """

    import re

    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", budget_month):
        raise ValueError("Budget month must be in YYYY-MM format.")

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                b.budget_amount,
                b.budget_month,
                c.category_name,
                COALESCE(SUM(t.amount), 0) AS actual_spending
            FROM budgets b
            JOIN categories c
                ON b.category_id = c.id
            LEFT JOIN transactions t
                ON t.category_id = b.category_id
                AND t.business_id = b.business_id
                AND t.transaction_type = 'Expense'
                AND strftime('%Y-%m', t.transaction_date) = b.budget_month
            WHERE b.business_id = ?
                AND b.budget_month = ?
            GROUP BY
                b.id,
                b.budget_amount,
                b.budget_month,
                c.category_name
            ORDER BY c.category_name
        """, (business_id, budget_month))

        rows = cursor.fetchall()

        categories = []

        for row in rows:
            budget = float(row["budget_amount"])
            spent = float(row["actual_spending"])
            remaining = budget - spent

            percentage = (
                (spent / budget) * 100
                if budget > 0 else 0
            )

            categories.append({
                "category": row["category_name"],
                "budget": round(budget, 2),
                "spent": round(spent, 2),
                "remaining": round(remaining, 2),
                "percentage_used": round(percentage, 2),
                "status": (
                    "Exceeded" if spent > budget else "Within Budget"
                )
            })

        total_budget = sum(item["budget"] for item in categories)
        total_spent = sum(item["spent"] for item in categories)

        return {
            "business_id": business_id,
            "budget_month": budget_month,
            "total_budget": round(total_budget, 2),
            "total_spent": round(total_spent, 2),
            "total_remaining": round(total_budget - total_spent, 2),
            "categories": categories,
            "currency": "INR"
        }

    finally:
        connection.close()




def set_monthly_budget(
    business_id,
    category_id,
    budget_amount,
    budget_month
):
    """
    Create or update a monthly budget for an expense category.
    """

    import re

    if not isinstance(budget_amount, (int, float)) or isinstance(budget_amount, bool) or budget_amount <= 0:
        raise ValueError("Budget amount must be greater than zero.")

    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", budget_month):
        raise ValueError("Budget month must be in YYYY-MM format.")

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT id
            FROM categories
            WHERE id = ?
                AND business_id = ?
                AND category_type = 'Expense'
        """, (category_id, business_id))

        category = cursor.fetchone()

        if category is None:
            raise ValueError("Invalid expense category.")

        cursor.execute("""
            INSERT INTO budgets (
                business_id,
                category_id,
                budget_amount,
                budget_month
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(business_id, category_id, budget_month)
            DO UPDATE SET budget_amount = excluded.budget_amount
        """, (
            business_id,
            category_id,
            budget_amount,
            budget_month
        ))

        connection.commit()

        return {
            "success": True,
            "business_id": business_id,
            "category_id": category_id,
            "budget_amount": round(float(budget_amount), 2),
            "budget_month": budget_month,
            "message": "Monthly budget saved successfully."
        }

    finally:
        connection.close()






