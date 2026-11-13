
import json
from google import genai

from config import Config
from modules.financial_tools import (
    get_financial_summary,
    get_expense_breakdown,
    get_transaction_history,
    get_budget_status
)


MODEL_NAME = "gemini-3.5-flash-lite"


def get_gemini_client():
    api_key = Config.GEMINI_API_KEY

    if not api_key:
        raise ValueError(
            "Gemini API key not found. Check your .env file."
        )

    return genai.Client(api_key=api_key)



SYSTEM_INSTRUCTION = """
You are FinWise AI, a friendly and intelligent business finance assistant.

You are already connected to the current business's financial records.

IMPORTANT BUSINESS CONTEXT:
- The backend automatically provides the correct business_id.
- You must NEVER ask the user for a Business ID.
- You must NEVER ask which business they mean.
- When the user asks about financial data, immediately use the appropriate financial tool.
- The backend handles business identification automatically.

FINANCIAL RULES:
1. Use financial tools for questions about actual business data.
2. Never invent income, expenses, profit or budget figures.
3. Explain only verified results returned by Python.
4. Use Indian Rupees (INR).
5. Explain financial results clearly and provide practical insights.
6. If information is unavailable, say so honestly.
7. Be friendly, concise and helpful.
"""



FINANCIAL_TOOLS = [
    {
        "type": "function",
        "name": "get_financial_summary",
        "description": "Get total income, expenses, net profit and profit margin.",
        "parameters": {
            "type": "object",
            "properties": {
                "business_id": {"type": "integer"}
            },
            "required": ["business_id"]
        }
    },
    {
        "type": "function",
        "name": "get_expense_breakdown",
        "description": "Get expense totals grouped by category and percentage.",
        "parameters": {
            "type": "object",
            "properties": {
                "business_id": {"type": "integer"}
            },
            "required": ["business_id"]
        }
    },
    {
        "type": "function",
        "name": "get_transaction_history",
        "description": "Get recent transactions, optionally filtered by type.",
        "parameters": {
            "type": "object",
            "properties": {
                "business_id": {"type": "integer"},
                "limit": {"type": "integer"},
                "transaction_type": {
                    "type": "string",
                    "enum": ["Income", "Expense"]
                }
            },
            "required": ["business_id"]
        }
    },
    {
        "type": "function",
        "name": "get_budget_status",
        "description": "Check monthly budgets against actual spending.",
        "parameters": {
            "type": "object",
            "properties": {
                "business_id": {"type": "integer"},
                "budget_month": {
                    "type": "string",
                    "description": "Month in YYYY-MM format."
                }
            },
            "required": ["business_id", "budget_month"]
        }
    }
]



def execute_financial_tool(tool_name, arguments, business_id):

    allowed_tools = {
        "get_financial_summary": {
            "function": get_financial_summary,
            "parameters": []
        },

        "get_expense_breakdown": {
            "function": get_expense_breakdown,
            "parameters": []
        },

        "get_transaction_history": {
            "function": get_transaction_history,
            "parameters": ["limit", "transaction_type"]
        },

        "get_budget_status": {
            "function": get_budget_status,
            "parameters": ["budget_month"]
        }
    }

    if tool_name not in allowed_tools:
        raise ValueError("Unsupported financial tool.")

    tool = allowed_tools[tool_name]

    # Keep only approved arguments.
    clean_arguments = {
        key: value
        for key, value in dict(arguments).items()
        if key in tool["parameters"]
    }

    # Business ID always comes from Flask, never Gemini.
    clean_arguments["business_id"] = business_id

    return tool["function"](**clean_arguments)



def ask_finwise_ai(user_message, business_id=1):

    client = get_gemini_client()

    current_input = user_message
    previous_id = None

    # Limit tool rounds to prevent endless tool-calling loops.
    for _ in range(5):

        interaction = client.interactions.create(
            model=MODEL_NAME,
            input=current_input,
            system_instruction=SYSTEM_INSTRUCTION,
            tools=FINANCIAL_TOOLS,
            previous_interaction_id=previous_id
        )

        function_results = []

        for step in interaction.steps:

            if step.type == "function_call":

                result = execute_financial_tool(
                    tool_name=step.name,
                    arguments=step.arguments,
                    business_id=business_id
                )

                function_results.append({
                    "type": "function_result",
                    "name": step.name,
                    "call_id": step.id,
                    "result": [
                        {
                            "type": "text",
                            "text": json.dumps(result)
                        }
                    ]
                })

        # No more tool calls: return Gemini's final answer.
        if not function_results:
            return (
                interaction.output_text
                or "I couldn't generate a response."
            )

        # Send verified Python results back to Gemini.
        current_input = function_results
        previous_id = interaction.id

    return "I couldn't complete the financial analysis. Please try again."


def test_gemini_connection():

    client = get_gemini_client()

    interaction = client.interactions.create(
        model=MODEL_NAME,
        input="Introduce yourself as FinWise AI in one sentence."
    )

    return interaction.output_text

