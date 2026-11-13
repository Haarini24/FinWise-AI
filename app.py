import plotly.graph_objects as go
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify
)

from database import init_db, get_connection

from modules.transactions import (
    add_transaction,
    get_transactions,
    update_transaction,
    delete_transaction
)

from modules.gemini_service import ask_finwise_ai


app = Flask(__name__)
app.secret_key = "finwise-development-key"

BUSINESS_ID = 1


# -------------------------------
# DASHBOARD
# -------------------------------


@app.route("/")
def dashboard():
    connection = get_connection()

    # Overall financial summary
    summary = connection.execute("""
        SELECT
            COALESCE(SUM(CASE
                WHEN transaction_type = 'Income' THEN amount
                ELSE 0 END), 0) AS total_income,

            COALESCE(SUM(CASE
                WHEN transaction_type = 'Expense' THEN amount
                ELSE 0 END), 0) AS total_expenses

        FROM transactions
        WHERE business_id = ?
    """, (BUSINESS_ID,)).fetchone()

    # Monthly income and expenses
    monthly_data = connection.execute("""
        SELECT
            strftime('%Y-%m', transaction_date) AS month,
            SUM(CASE WHEN transaction_type = 'Income'
                THEN amount ELSE 0 END) AS income,
            SUM(CASE WHEN transaction_type = 'Expense'
                THEN amount ELSE 0 END) AS expenses

        FROM transactions
        WHERE business_id = ?
        GROUP BY strftime('%Y-%m', transaction_date)
        ORDER BY month
    """, (BUSINESS_ID,)).fetchall()

    # Expense category breakdown
    expense_data = connection.execute("""
        SELECT
            c.category_name,
            SUM(t.amount) AS total_amount

        FROM transactions t
        JOIN categories c ON t.category_id = c.id

        WHERE t.business_id = ?
          AND t.transaction_type = 'Expense'

        GROUP BY c.category_name
        ORDER BY total_amount DESC
    """, (BUSINESS_ID,)).fetchall()

    connection.close()

    total_income = summary["total_income"]
    total_expenses = summary["total_expenses"]
    net_profit = total_income - total_expenses

    profit_margin = (
        (net_profit / total_income) * 100
        if total_income > 0 else 0
    )

    financial_summary = {
        "income": total_income,
        "expenses": total_expenses,
        "profit": net_profit,
        "profit_margin": profit_margin
    }

    # -------------------------------
    # CHART 1: INCOME VS EXPENSES
    # -------------------------------

    months = [row["month"] for row in monthly_data]
    incomes = [row["income"] for row in monthly_data]
    expenses = [row["expenses"] for row in monthly_data]

    income_expense_fig = go.Figure()

    income_expense_fig.add_trace(go.Bar(
        name="Income",
        x=months,
        y=incomes,
        marker_color="#34d399"
    ))

    income_expense_fig.add_trace(go.Bar(
        name="Expenses",
        x=months,
        y=expenses,
        marker_color="#fb7185"
    ))

    income_expense_fig.update_layout(
        title="Monthly Income vs Expenses",
        barmode="group",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#f4f6fc"),
       margin=dict(l=20, r=20, t=70, b=55),
legend=dict(
    orientation="h",
    y=-0.18,
    x=0.5,
    xanchor="center"
),
        yaxis_title="Amount (₹)",
        xaxis=dict(
    type="category",
    tickmode="array",
    tickvals=months,
    ticktext=months
)
)
    

    income_expense_chart = income_expense_fig.to_html(
        full_html=False,
        include_plotlyjs="cdn",
        config={"responsive": True, "displayModeBar": False}
    )

    # -------------------------------
    # CHART 2: EXPENSE DISTRIBUTION
    # -------------------------------

    expense_fig = go.Figure()

    if expense_data:
        expense_fig.add_trace(go.Pie(
            labels=[row["category_name"] for row in expense_data],
            values=[row["total_amount"] for row in expense_data],
            hole=0.65,
            textinfo="label+percent"
        ))
    else:
        expense_fig.add_annotation(
            text="No expense data available",
            showarrow=False
        )

    expense_fig.update_layout(
        title="Expense Distribution",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#f4f6fc"),
        margin=dict(l=20, r=20, t=55, b=20),
        showlegend=True
    )

    expense_chart = expense_fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        config={"responsive": True, "displayModeBar": False}
    )

    # -------------------------------
    # CHART 3: PROFIT PERFORMANCE
    # -------------------------------

    profits = [
        row["income"] - row["expenses"]
        for row in monthly_data
    ]

    profit_fig = go.Figure()

    profit_fig.add_trace(go.Scatter(
        x=months,
        y=profits,
        mode="lines+markers",
        name="Net Profit",
        line=dict(color="#8b5cf6", width=3),
        fill="tozeroy",
        fillcolor="rgba(139, 92, 246, 0.12)"
    ))

    
    profit_fig.update_layout(
    title="Monthly Net Profit",
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#f4f6fc"),
    margin=dict(l=20, r=20, t=55, b=45),
    yaxis_title="Profit (₹)",
    xaxis_title="Month",
    xaxis=dict(
        type="category",
        tickmode="array",
        tickvals=months,
        ticktext=months
    )
)

    

    profit_chart = profit_fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        config={"responsive": True, "displayModeBar": False}
    )

    transactions = get_transactions(BUSINESS_ID)[:5]

    return render_template(
        "dashboard.html",
        summary=financial_summary,
        transactions=transactions,
        income_expense_chart=income_expense_chart,
        expense_chart=expense_chart,
        profit_chart=profit_chart
    )



# -------------------------------
# TRANSACTIONS
# -------------------------------

@app.route("/transactions")
def transactions():
    records = get_transactions(BUSINESS_ID)

    connection = get_connection()

    categories = connection.execute("""
        SELECT * FROM categories
        WHERE business_id = ?
        ORDER BY category_name
    """, (BUSINESS_ID,)).fetchall()

    connection.close()

    return render_template(
        "transactions.html",
        transactions=records,
        categories=categories
    )


@app.route("/transactions/add", methods=["POST"])
def add_transaction_route():
    try:
        add_transaction(
            BUSINESS_ID,
            request.form.get("transaction_type"),
            request.form.get("amount"),
            int(request.form.get("category_id")),
            request.form.get("description", ""),
            request.form.get("transaction_date"),
            request.form.get("payment_method", "Other")
        )

        flash("Transaction added successfully!", "success")

    except (ValueError, TypeError) as error:
        flash(str(error), "error")

    return redirect(url_for("transactions"))


@app.route("/transactions/delete/<int:transaction_id>", methods=["POST"])
def delete_transaction_route(transaction_id):
    deleted = delete_transaction(transaction_id, BUSINESS_ID)

    if deleted:
        flash("Transaction deleted successfully!", "success")
    else:
        flash("Transaction not found.", "error")

    return redirect(url_for("transactions"))

# -------------------------------
# AI ASSISTANT PAGE
# -------------------------------

@app.route("/assistant")
def ai_assistant():
    return render_template("assistant.html")


# -------------------------------
# FINWISE AI CHAT API
# -------------------------------

@app.route("/api/chat", methods=["POST"])
def chat_with_finwise():

    data = request.get_json(silent=True) or {}

    user_message = data.get("message", "")

    if not isinstance(user_message, str) or not user_message.strip():
        return jsonify({
            "success": False,
            "error": "Please enter a message."
        }), 400

    if len(user_message) > 2000:
        return jsonify({
            "success": False,
            "error": "Your message is too long. Please keep it under 2000 characters."
        }), 400

    try:
        answer = ask_finwise_ai(
            user_message=user_message.strip(),
            business_id=BUSINESS_ID
        )

        return jsonify({
            "success": True,
            "answer": answer
        })

    except Exception as error:
        print("FinWise AI Error:", error)

        return jsonify({
            "success": False,
            "error": "I'm having trouble processing your request right now. Please try again."
        }), 500


# -------------------------------
# RUN APPLICATION
# -------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
