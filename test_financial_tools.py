
from modules.financial_tools import get_financial_summary

print("FINWISE AI - FINANCIAL SUMMARY TEST")
print("------------------------------------")

summary = get_financial_summary(1)

for key, value in summary.items():
    print(f"{key}: {value}")

print("\nFinancial summary test completed!")

