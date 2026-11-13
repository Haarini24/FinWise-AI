
from modules.financial_tools import get_expense_breakdown

print("FINWISE AI - EXPENSE BREAKDOWN TEST")
print("-----------------------------------")

result = get_expense_breakdown(1)

print("Total Expenses:", result["total_expenses"])
print("\nExpense Categories:")

for item in result["categories"]:
    print(
        f'{item["category"]}: '
        f'₹{item["amount"]} | '
        f'{item["percentage"]}% | '
        f'{item["transaction_count"]} transactions'
    )

print("\nExpense breakdown test completed!")
