
from modules.financial_tools import get_budget_status

print("FINWISE AI - BUDGET STATUS TEST")
print("--------------------------------")

result = get_budget_status(1, "2026-11")

print("Budget Month:", result["budget_month"])
print("Total Budget:", result["total_budget"])
print("Total Spent:", result["total_spent"])
print("Remaining:", result["total_remaining"])

print("\nCategory Details:")

for item in result["categories"]:
    print(
        f'{item["category"]} | '
        f'Budget: ₹{item["budget"]} | '
        f'Spent: ₹{item["spent"]} | '
        f'Remaining: ₹{item["remaining"]} | '
        f'Used: {item["percentage_used"]}% | '
        f'Status: {item["status"]}'
    )

print("\nBudget status test completed!")
