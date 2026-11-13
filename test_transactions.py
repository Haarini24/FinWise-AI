
from modules.transactions import (
    add_transaction,
    get_transactions,
    update_transaction,
    delete_transaction
)

BUSINESS_ID = 1

print("\nFINWISE AI - TRANSACTION TEST")
print("------------------------------")

# Find default categories
from database import get_connection

connection = get_connection()

income_category = connection.execute("""
    SELECT id FROM categories
    WHERE business_id = ? AND category_name = ?
""", (BUSINESS_ID, "Sales Revenue")).fetchone()

expense_category = connection.execute("""
    SELECT id FROM categories
    WHERE business_id = ? AND category_name = ?
""", (BUSINESS_ID, "Inventory")).fetchone()

connection.close()

try:
    # Test income
    income_id = add_transaction(
        BUSINESS_ID,
        "Income",
        15000,
        income_category["id"],
        "Test business sales"
    )

    print("Income added:", income_id)

    # Test expense
    expense_id = add_transaction(
        BUSINESS_ID,
        "Expense",
        2500,
        expense_category["id"],
        "Test inventory purchase"
    )

    print("Expense added:", expense_id)

    # View transactions
    print("\nTransaction History:")
    for transaction in get_transactions(BUSINESS_ID):
        print(transaction)

    # Test update
    updated = update_transaction(
        income_id,
        BUSINESS_ID,
        "Income",
        16000,
        income_category["id"],
        "Updated test business sales",
        "2026-11-12",
        "Bank Transfer"
    )

    print("\nUpdate successful:", updated)

    # Test delete
    deleted = delete_transaction(expense_id, BUSINESS_ID)

    print("Delete successful:", deleted)

    # Clean up test income
    delete_transaction(income_id, BUSINESS_ID)

    print("\nAll transaction tests completed!")

except Exception as error:
    print("\nTest failed:", error)
