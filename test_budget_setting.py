
from database import get_connection
from modules.financial_tools import (
    set_monthly_budget,
    get_budget_status
)

connection = get_connection()

try:
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, category_name
        FROM categories
        WHERE business_id = 1
            AND category_type = 'Expense'
    """)

    categories = cursor.fetchall()

    print("Available Expense Categories:")

    for category in categories:
        print(category["id"], "-", category["category_name"])

finally:
    connection.close()


print("\nSetting Rent Budget...")

# Replace 5 with the actual Rent category ID
result = set_monthly_budget(
    business_id=1,
    category_id=5,
    budget_amount=8000,
    budget_month="2026-11"
)

print(result)

print("\nChecking Budget Status...")

status = get_budget_status(1, "2026-11")

print(status)

