
from modules.gemini_service import ask_finwise_ai

print("FINWISE AI - FUNCTION CALLING TEST")
print("----------------------------------")

questions = [
    "How much profit did my business make?",
    "What is my biggest expense?",
    "Show me my monthly Rent budget status for November 2026."
]

for question in questions:

    print("\nUser:", question)

    try:
        answer = ask_finwise_ai(question)

        print("\nFinWise AI:")
        print(answer)

    except Exception as error:
        print("\nTest failed:")
        print(type(error).__name__, error)

    print("\n" + "-" * 45)

