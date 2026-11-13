
from modules.gemini_service import get_gemini_client

print("FINWISE AI - INTERACTIONS API TEST")
print("----------------------------------")

try:
    client = get_gemini_client()

    interaction = client.interactions.create(
        model="gemini-3.5-flash-lite",
        input="Introduce yourself as FinWise AI in one friendly sentence."
    )

    print("\nGemini response:")
    print(interaction.output_text)

    print("\nInteractions API connection successful!")

except Exception as error:
    print("\nTest failed:")
    print(type(error).__name__, error)
