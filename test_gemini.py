
from modules.gemini_service import test_gemini_connection

print("FINWISE AI - GEMINI CONNECTION TEST")
print("-----------------------------------")

try:
    answer = test_gemini_connection()

    print("Gemini connection successful!")
    print("\nGemini response:")
    print(answer)

except Exception as error:
    print("Gemini connection failed.")
    print("Error:", error)
