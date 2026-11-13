
from modules.financial_tools import get_transaction_history

print("FINWISE AI - TRANSACTION HISTORY TEST")
print("-------------------------------------")

result = get_transaction_history(1)

print("Total Transactions:", result["transaction_count"])

for item in result["transactions"]:
    print(
        f'{item["date"]} | '
        f'{item["type"]} | '
        f'{item["category"]} | '
        f'₹{item["amount"]} | '
        f'{item["description"]}'
    )

print("\nIncome Transactions:")

income = get_transaction_history(1, transaction_type="Income")
print(income)

print("\nTransaction history test completed!")
