
from modules.gemini_service import detect_transaction_intent
import json

message = "ഇന്ന് ഗതാഗതത്തിനായി 500 രൂപ UPI വഴി ചെലവാക്കി."

result = detect_transaction_intent(message)

print("\nFINWISE AI TRANSACTION DETECTION")
print("--------------------------------")
print(json.dumps(result, indent=4, ensure_ascii=False))
