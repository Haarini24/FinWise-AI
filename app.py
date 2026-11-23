import math
import json
import os
import tempfile
import uuid
import csv
import io
from xml.parsers.expat import errors
from config import Config
from datetime import datetime, date

from modules.financial_tools import (
    get_budget_status,
    set_monthly_budget
)
import plotly.graph_objects as go
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    session
)

from functools import wraps

from modules.auth.authentication import (
    create_owner,
    create_manager,
    verify_login
)

from database import init_db, get_connection

from modules.transactions import (
    add_transaction,
    get_transactions,
    update_transaction,
    delete_transaction
)

from modules.gemini_service import (
    ask_finwise_ai,
    detect_transaction_intent,
    update_transaction_draft
)


app = Flask(__name__)
app.config.from_object(Config)
def get_category_id(business_id, transaction_type, category_name):
    connection = get_connection()

    try:
        category = connection.execute("""
            SELECT id
            FROM categories
            WHERE business_id = ?
              AND category_type = ?
              AND LOWER(category_name) = LOWER(?)
        """, (
            business_id,
            transaction_type,
            category_name
        )).fetchone()

        if category is None:
            return None

        return category["id"]

    finally:
        connection.close()
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

def validate_transaction_draft(business_id, draft):

    errors = []

    transaction_type = draft.get("transaction_type")
    amount = draft.get("amount")
    category = draft.get("category")
    transaction_date = draft.get("transaction_date")
    payment_method = draft.get("payment_method")
    description = draft.get("description")

    if transaction_type not in ("Income", "Expense"):
        errors.append("transaction_type")

    try:
        amount = float(amount)

        if not math.isfinite(amount) or amount <= 0:
            errors.append("amount")

    except (ValueError, TypeError):
        errors.append("amount")

    if transaction_type in ("Income", "Expense"):
        category_id = get_category_id(
            business_id,
            transaction_type,
            category
        )

        if category_id is None:
            errors.append("category")
    else:
        category_id = None
        errors.append("category")

    try:
        datetime.strptime(transaction_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        errors.append("transaction_date")

    allowed_methods = (
        "Other", "Cash", "UPI", "Card", "Bank Transfer"
    )

    if payment_method not in allowed_methods:
        errors.append("payment_method")

    if description is None:
         description = ""
    elif not isinstance(description, str) or len(description.strip()) > 200:
        errors.append("description")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "category_id": category_id
    }

def save_pending_transaction(business_id, user_id, transaction_data):
    connection = get_connection()

    try:
        # Keep only one active draft per user and business
        connection.execute("""
            DELETE FROM pending_transactions
            WHERE business_id = ? AND user_id = ?
        """, (business_id, user_id))

        cursor = connection.execute("""
            INSERT INTO pending_transactions (
                business_id,
                user_id,
                transaction_data
            )
            VALUES (?, ?, ?)
        """, (
            business_id,
            user_id,
            json.dumps(transaction_data)
        ))

        connection.commit()
        return cursor.lastrowid

    finally:
        connection.close()


def get_pending_transaction(business_id, user_id):
    connection = get_connection()

    try:
        draft = connection.execute("""
            SELECT id, transaction_data
            FROM pending_transactions
            WHERE business_id = ? AND user_id = ?
            ORDER BY id DESC
            LIMIT 1
        """, (business_id, user_id)).fetchone()

        if draft is None:
            return None

        return {
            "id": draft["id"],
            "data": json.loads(draft["transaction_data"])
        }

    finally:
        connection.close()


def delete_pending_transaction(business_id, user_id):
    connection = get_connection()

    try:
        connection.execute("""
            DELETE FROM pending_transactions
            WHERE business_id = ? AND user_id = ?
        """, (business_id, user_id))

        connection.commit()

    finally:
        connection.close()


# -------------------------------
# AUTHENTICATION
# -------------------------------

def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))

        return route_function(*args, **kwargs)

    return wrapper
def owner_required(route_function):
    @wraps(route_function)
    @login_required
    def wrapper(*args, **kwargs):
        if session["user"]["role"] != "owner":
            flash("Only the business owner can access this page.", "error")
            return redirect(url_for("dashboard"))

        return route_function(*args, **kwargs)

    return wrapper
def current_business_id():
    return session["user"]["business_id"]

def owner_exists():
    connection = get_connection()

    try:
        owner = connection.execute("""
            SELECT id FROM users
            WHERE role = 'owner'
            LIMIT 1
        """).fetchone()

        return owner is not None

    finally:
        connection.close()


@app.route("/register", methods=["GET", "POST"])
def register():

    # Registration is available only before the first owner exists.
    if owner_exists():
        flash("Owner registration is already closed.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        try:
            create_owner(
                request.form.get("full_name", ""),
                request.form.get("email", ""),
                request.form.get("password", "")
            )

            flash("Owner account created. Please log in.", "success")
            return redirect(url_for("login"))

        except ValueError as error:
            flash(str(error), "error")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if "user" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")

        if not email.strip() or not password:
            flash("Please enter your email and password.", "error")
            return render_template("login.html")

        user = verify_login(email, password)

        if user:
            session.clear()
            session["user"] = user

            flash(
                f"Welcome back, {user['full_name']}!",
                "success"
            )

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

@app.route("/managers/add", methods=["GET", "POST"])
@owner_required
def add_manager():

    if request.method == "POST":
        try:
            create_manager(
                request.form.get("full_name", ""),
                request.form.get("email", ""),
                request.form.get("password", ""),
                current_business_id()
            )

            flash("Manager account created successfully!", "success")
            return redirect(url_for("add_manager"))

        except ValueError as error:
            flash(str(error), "error")

    return render_template("add_manager.html")



# -------------------------------
# DASHBOARD
# -------------------------------


@app.route("/")
@login_required
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
    """, (current_business_id(),)).fetchone()

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
    """, (current_business_id(),)).fetchall()

    # Expense category breakdown
    expense_data = connection.execute("""
        SELECT
            c.category_name,
            SUM(t.amount) AS total_amount

        FROM transactions t
        JOIN categories c ON t.category_id = c.id

        WHERE 	t.business_id = ?
          AND t.transaction_type = 'Expense'

        GROUP BY c.category_name
        ORDER BY total_amount DESC
    """, (current_business_id(),)).fetchall()

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
        marker_color="#7897B8",
        marker_line_width=0,
        marker_cornerradius=6
    ))

    income_expense_fig.add_trace(go.Bar(
        name="Expenses",
        x=months,
        y=expenses,
        marker_color="#D58C91",
        marker_line_width=0,
        marker_cornerradius=6
    ))

    income_expense_fig.update_layout(
        title=dict(
            text="Monthly Income vs Expenses",
            font=dict(size=17, color="#263B57")
        ),
        barmode="group",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="Inter, Segoe UI, sans-serif",
            color="#52677F",
            size=12
        ),
        margin=dict(l=25, r=20, t=65, b=65),
        legend=dict(
            orientation="h",
            y=-0.22,
            x=0.5,
            xanchor="center",
            font=dict(color="#52677F", size=12)
        ),
        yaxis_title="Amount (₹)",
        xaxis=dict(
            type="category",
            tickmode="array",
            tickvals=months,
            ticktext=months,
            showgrid=False,
            zeroline=False
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#E8EDF3",
            zeroline=False
        ),
        hoverlabel=dict(
            bgcolor="#263B57",
            font_color="#FFFFFF"
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
            textinfo="label+percent",
            textfont=dict(color="#40566F", size=12),
            marker=dict(
                colors=[
                    "#587DA5",
                    "#7897B8",
                    "#A8BDD2",
                    "#C6D5E4",
                    "#91A99F",
                    "#D6B9A5",
                    "#D58C91",
                    "#A9A6C5"
                ],
                line=dict(color="#FFFFFF", width=3)
            )
        ))
    else:
        expense_fig.add_annotation(
            text="No expense data available",
            showarrow=False,
            font=dict(color="#8291A5", size=14)
        )

    expense_fig.update_layout(
        title=dict(
            text="Expense Distribution",
            font=dict(size=17, color="#263B57")
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="Inter, Segoe UI, sans-serif",
            color="#52677F",
            size=12
        ),
        margin=dict(l=20, r=20, t=65, b=25),
        showlegend=True,
        legend=dict(
            font=dict(color="#52677F", size=11)
        ),
        hoverlabel=dict(
            bgcolor="#263B57",
            font_color="#FFFFFF"
        )
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
        line=dict(color="#587DA5", width=3),
        marker=dict(
            color="#587DA5",
            size=8,
            line=dict(color="#FFFFFF", width=2)
        ),
        fill="tozeroy",
        fillcolor="rgba(120, 151, 184, 0.13)"
    ))

    profit_fig.update_layout(
        title=dict(
            text="Monthly Net Profit",
            font=dict(size=17, color="#263B57")
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="Inter, Segoe UI, sans-serif",
            color="#52677F",
            size=12
        ),
        margin=dict(l=25, r=20, t=65, b=55),
        yaxis_title="Profit (₹)",
        xaxis_title="Month",
        xaxis=dict(
            type="category",
            tickmode="array",
            tickvals=months,
            ticktext=months,
            showgrid=False,
            zeroline=False
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#E8EDF3",
            zeroline=False
        ),
        hoverlabel=dict(
            bgcolor="#263B57",
            font_color="#FFFFFF"
        )
    )

    profit_chart = profit_fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        config={"responsive": True, "displayModeBar": False}
    )


    transactions = get_transactions(current_business_id())[:5]

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
@login_required
def transactions():
    business_id = current_business_id()

    connection = get_connection()

    categories = connection.execute("""
        SELECT * FROM categories
        WHERE business_id = ?
        ORDER BY category_name
    """, (business_id,)).fetchall()

    connection.close()

    transaction_type = request.args.get("type", "").strip()
    category_id = request.args.get("category_id", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    search = request.args.get("search", "").strip()

    records = get_transactions(business_id)

    if transaction_type in ("Income", "Expense"):
        records = [
            record for record in records
            if record["transaction_type"] == transaction_type
        ]

    if category_id:
        try:
            category_id = int(category_id)
            records = [
                record for record in records
                if record["category_id"] == category_id
            ]
        except ValueError:
            category_id = ""

    if start_date:
        records = [
            record for record in records
            if record["transaction_date"] >= start_date
        ]

    if end_date:
        records = [
            record for record in records
            if record["transaction_date"] <= end_date
        ]

    if search:
        records = [
            record for record in records
            if search.lower() in (record["description"] or "").lower()
        ]

    return render_template(
        "transactions.html",
        transactions=records,
        categories=categories,
        selected_type=transaction_type,
        selected_category=category_id,
        start_date=start_date,
        end_date=end_date,
        search=search
    )




@app.route("/transactions/add", methods=["POST"])
@login_required
def add_transaction_route():
    try:
        add_transaction(
            current_business_id(),
            request.form.get("transaction_type"),
            request.form.get("amount"),
            request.form.get("category_id"),
            request.form.get("description", ""),
            request.form.get("transaction_date"),
            request.form.get("payment_method", "Other")
        )

        flash("Transaction added successfully!", "success")

        if request.form.get("submit_action") == "add_another":
            return redirect(url_for("transactions"))

    except (ValueError, TypeError) as error:
        flash(str(error), "error")

    return redirect(url_for("transactions"))


@app.route("/transactions/import-csv", methods=["POST"])
@login_required
def upload_transactions_csv():
    csv_file = request.files.get("csv_file")

    if not csv_file or csv_file.filename == "":
        flash("Please select a CSV file.", "error")
        return redirect(url_for("transactions"))

    if not csv_file.filename.lower().endswith(".csv"):
        flash("Please upload a CSV file.", "error")
        return redirect(url_for("transactions"))

    try:
        file_content = csv_file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(file_content))

        required_columns = [
            "Date",
            "Transaction Type",
            "Category",
            "Amount",
            "Description",
            "Payment Method"
        ]

        if reader.fieldnames != required_columns:
            flash("CSV columns do not match the required format.", "error")
            return redirect(url_for("transactions"))

        rows = list(reader)

        if not rows:
            flash("The CSV file is empty.", "error")
            return redirect(url_for("transactions"))

        if len(rows) > 500:
            flash("Maximum 500 transactions allowed.", "error")
            return redirect(url_for("transactions"))

        connection = get_connection()

        try:
            categories = connection.execute("""
                SELECT id, category_name, category_type
                FROM categories
                WHERE business_id = ?
            """, (current_business_id(),)).fetchall()
        finally:
            connection.close()

        category_lookup = {
            (
                category["category_name"].strip().lower(),
                category["category_type"]
            ): category["id"]
            for category in categories
        }

        valid_rows = []
        errors = []

        allowed_methods = (
            "Other", "Cash", "UPI", "Card", "Bank Transfer"
        )

        for row_number, row in enumerate(rows, start=2):
            try:
                transaction_date = row["Date"].strip()
                transaction_type = row["Transaction Type"].strip()
                category_name = row["Category"].strip().lower()
                amount = float(row["Amount"])
                description = row["Description"].strip()
                payment_method = row["Payment Method"].strip()

                parsed_date = datetime.strptime(
                    transaction_date, "%Y-%m-%d"
                )

                if parsed_date.strftime("%Y-%m-%d") != transaction_date:
                    raise ValueError("Date must use YYYY-MM-DD format.")

                if transaction_type not in ("Income", "Expense"):
                    raise ValueError("Invalid transaction type.")

                if not math.isfinite(amount) or amount <= 0:
                    raise ValueError("Amount must be greater than zero.")

                if len(description) > 200:
                    raise ValueError("Description cannot exceed 200 characters.")

                if payment_method not in allowed_methods:
                    raise ValueError("Invalid payment method.")

                category_id = category_lookup.get(
                    (category_name, transaction_type)
                )

                if category_id is None:
                    raise ValueError(
                        "Category does not match this transaction type."
                    )

                valid_rows.append({
                    "transaction_date": transaction_date,
                    "transaction_type": transaction_type,
                    "category_id": category_id,
                    "amount": amount,
                    "description": description,
                    "payment_method": payment_method
                })

            except (ValueError, KeyError, TypeError) as error:
                errors.append(f"Row {row_number}: {error}")

        if errors:
            return render_template(
                "csv_preview.html",
                rows=rows,
                errors=errors,
                valid_count=len(valid_rows)
            )

        import_folder = os.path.join(
            tempfile.gettempdir(),
            "finwise_csv_imports"
        )

        os.makedirs(import_folder, exist_ok=True)

        import_id = str(uuid.uuid4())
        file_path = os.path.join(import_folder, f"{import_id}.json")

        import_data = {
            "business_id": current_business_id(),
            "rows": valid_rows
        }

        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(import_data, file)

        session["csv_import_id"] = import_id

        return render_template(
            "csv_preview.html",
            rows=rows,
            errors=[],
            valid_count=len(valid_rows)
        )

    except (UnicodeDecodeError, csv.Error):
        flash("Unable to read this CSV file.", "error")
        return redirect(url_for("transactions"))



@app.route("/transactions/confirm-csv-import", methods=["POST"])
@login_required
def confirm_csv_import():
    import_id = session.get("csv_import_id")

    if not import_id:
        flash("No pending CSV import found. Please upload again.", "error")
        return redirect(url_for("transactions"))

    import_folder = os.path.join(
        tempfile.gettempdir(),
        "finwise_csv_imports"
    )

    file_path = os.path.join(import_folder, f"{import_id}.json")

    if not os.path.isfile(file_path):
        session.pop("csv_import_id", None)
        flash("CSV preview expired. Please upload again.", "error")
        return redirect(url_for("transactions"))

    connection = get_connection()

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            import_data = json.load(file)

        if import_data.get("business_id") != current_business_id():
            flash("You cannot import another business's transactions.", "error")
            return redirect(url_for("transactions"))

        rows = import_data.get("rows", [])

        if not rows or len(rows) > 500:
            flash("Invalid CSV import data. Please upload again.", "error")
            return redirect(url_for("transactions"))

        for row in rows:
            connection.execute("""
                INSERT INTO transactions (
                    business_id,
                    category_id,
                    transaction_type,
                    amount,
                    description,
                    transaction_date,
                    payment_method
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                current_business_id(),
                row["category_id"],
                row["transaction_type"],
                row["amount"],
                row["description"],
                row["transaction_date"],
                row["payment_method"]
            ))

        connection.commit()

        os.remove(file_path)
        session.pop("csv_import_id", None)

        flash(
            f"Successfully imported {len(rows)} transactions!",
            "success"
        )

    except Exception:
        connection.rollback()
        flash("CSV import failed. No transactions were saved.", "error")

    finally:
        connection.close()

    return redirect(url_for("transactions"))

@app.route("/transactions/cancel-csv-import", methods=["POST"])
@login_required
def cancel_csv_import():
    import_id = session.pop("csv_import_id", None)

    if import_id:
        import_folder = os.path.join(
            tempfile.gettempdir(),
            "finwise_csv_imports"
        )

        file_path = os.path.join(
            import_folder,
            f"{import_id}.json"
        )

        if os.path.isfile(file_path):
            os.remove(file_path)

    flash("CSV import cancelled.", "success")
    return redirect(url_for("transactions"))


@app.route("/transactions/delete/<int:transaction_id>", methods=["POST"])
@login_required
def delete_transaction_route(transaction_id):
    deleted = delete_transaction(transaction_id, current_business_id())

    if deleted:
        flash("Transaction deleted successfully!", "success")
    else:
        flash("Transaction not found.", "error")

    return redirect(url_for("transactions"))

@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget():

    if request.method == "POST":

        budget_month = request.form.get("budget_month")
        category_id = request.form.get("category_id")
        budget_amount = request.form.get("budget_amount")

        try:
            set_monthly_budget(
                business_id=current_business_id(),
                category_id=int(category_id),
                budget_amount=float(budget_amount),
                budget_month=budget_month
            )

            flash("Budget saved successfully!", "success")

        except (ValueError, TypeError) as error:
            flash(str(error), "error")

        return redirect(url_for("budget", month=budget_month))

    # Get selected month
    budget_month = request.args.get(
        "month",
        datetime.now().strftime("%Y-%m")
    )

    # Get budget information
    budget_data = get_budget_status(
        current_business_id(),
        budget_month
    )

    # Get expense categories
    connection = get_connection()

    categories = connection.execute("""
        SELECT id, category_name
        FROM categories
        WHERE business_id = ?
        AND category_type = 'Expense'
        ORDER BY category_name
    """, (current_business_id(),)).fetchall()

    connection.close()

    return render_template(
        "budget.html",
        budget=budget_data,
        categories=categories,
        selected_month=budget_month
    )

# -------------------------------
# AI ASSISTANT PAGE
# -------------------------------

@app.route("/assistant")
@login_required
def ai_assistant():
    return render_template("assistant.html")


# -------------------------------
# FINWISE AI CHAT API
# -------------------------------

@app.route("/api/chat", methods=["POST"])
@login_required
def chat_with_finwise():

    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "")

    if not isinstance(user_message, str) or not user_message.strip():
        return jsonify({
            "success": False,
            "error": "Please enter a message."
        }), 400

    user_message = user_message.strip()

    if len(user_message) > 2000:
        return jsonify({
            "success": False,
            "error": "Your message is too long. Please keep it under 2000 characters."
        }), 400

    business_id = current_business_id()
    user_id = session["user"]["id"]

    try:
        # Check whether this user already has a pending draft
        pending = get_pending_transaction(business_id, user_id)

        if pending:

            updated_draft = update_transaction_draft(
                user_message,
                pending["data"]
            )

            # Validate the updated draft
            validation = validate_transaction_draft(
                business_id,
                updated_draft
            )

            missing_fields = validation["errors"]
            updated_draft["missing_fields"] = missing_fields

            # Save the updated draft after validation
            save_pending_transaction(
                business_id,
                user_id,
                updated_draft
            )

            if missing_fields:
                answer = updated_draft.get(
                    "clarification_question",
                    "I still need some transaction details. Could you clarify?"
                )
            else:
                answer = (
                    "Here is your updated transaction:\n\n"
                    f"Type: {updated_draft.get('transaction_type')}\n"
                    f"Amount: ₹{updated_draft.get('amount')}\n"
                    f"Category: {updated_draft.get('category')}\n"
                    f"Date: {updated_draft.get('transaction_date')}\n"
                    f"Description: {updated_draft.get('description')}\n"
                    f"Payment Method: {updated_draft.get('payment_method')}\n\n"
                    "Please review the details before confirming."
                )

            return jsonify({
                "success": True,
                "answer": answer,
                "transaction_detected": True,
                "needs_clarification": bool(missing_fields),
                "requires_confirmation": not bool(missing_fields)
            })

        # No pending draft: check for a new transaction
        detection = detect_transaction_intent(user_message)

        if detection.get("is_transaction") is True:

            transaction_data = {
                "transaction_type": detection.get("transaction_type"),
                "amount": detection.get("amount"),
                "category": detection.get("category"),
                "transaction_date": detection.get("transaction_date"),
                "description": detection.get("description"),
                "payment_method": detection.get("payment_method"),
                "missing_fields": detection.get("missing_fields", [])
            }


            validation = validate_transaction_draft(
                business_id,
                transaction_data
            )

            missing_fields = validation["errors"]
            transaction_data["missing_fields"] = missing_fields

            save_pending_transaction(
                business_id,
                user_id,
                transaction_data
            )

            if missing_fields:
                answer = detection.get(
                    "clarification_question",
                    "I need a little more information before preparing this transaction."
                )
            else:
                answer = (
                    "I detected a new transaction:\n\n"
                    f"Type: {transaction_data['transaction_type']}\n"
                    f"Amount: ₹{transaction_data['amount']}\n"
                    f"Category: {transaction_data['category']}\n"
                    f"Date: {transaction_data['transaction_date']}\n"
                    f"Description: {transaction_data['description']}\n"
                    f"Payment Method: {transaction_data['payment_method']}\n\n"
                    "Please review these details before confirming."
                )

            return jsonify({
                "success": True,
                "answer": answer,
                "transaction_detected": True,
                "needs_clarification": bool(missing_fields),
                "requires_confirmation": not bool(missing_fields)
            })

        # Normal financial question
        answer = ask_finwise_ai(
            user_message=user_message,
            business_id=business_id
        )

        return jsonify({
            "success": True,
            "answer": answer,
            "transaction_detected": False
        })

    except Exception as error:
        print("FinWise AI Error:", error)

        return jsonify({
            "success": False,
            "error": "I'm having trouble processing your request right now. Please try again."
        }), 500

@app.route("/api/confirm-transaction", methods=["POST"])
@login_required
def confirm_transaction():

    business_id = current_business_id()
    user_id = session["user"]["id"]

    try:
        pending = get_pending_transaction(business_id, user_id)

        if pending is None:
            return jsonify({
                "success": False,
                "error": "There is no pending transaction to confirm."
            }), 404

        draft = pending["data"]

        # Validate the complete draft independently
        validation = validate_transaction_draft(
            business_id,
            draft
        )

        if not validation["valid"]:
            return jsonify({
                "success": False,
                "error": (
                    "Some transaction details are missing or invalid: "
                    + ", ".join(validation["errors"])
                )
            }), 400

        category_id = validation["category_id"]
        amount = float(draft["amount"])

        # Save only after explicit confirmation
        transaction_id = add_transaction(
            business_id=business_id,
            transaction_type=draft["transaction_type"],
            amount=amount,
            category_id=category_id,
            description=draft.get("description", ""),
            transaction_date=draft["transaction_date"],
            payment_method=draft["payment_method"]
        )

        delete_pending_transaction(business_id, user_id)

        return jsonify({
            "success": True,
            "message": "Transaction saved successfully.",
            "transaction_id": transaction_id
        })

    except Exception as error:
        print("Transaction Confirmation Error:", error)

        return jsonify({
            "success": False,
            "error": "Unable to save the transaction. Please try again."
        }), 400

@app.route("/api/cancel-transaction", methods=["POST"])
@login_required
def cancel_transaction():

    business_id = current_business_id()
    user_id = session["user"]["id"]

    try:
        pending = get_pending_transaction(business_id, user_id)

        if pending is None:
            return jsonify({
                "success": False,
                "error": "There is no pending transaction to cancel."
            }), 404

        delete_pending_transaction(business_id, user_id)

        return jsonify({
            "success": True,
            "message": "Pending transaction cancelled."
        })

    except Exception as error:
        print("Transaction Cancellation Error:", error)

        return jsonify({
            "success": False,
            "error": "Unable to cancel the pending transaction."
        }), 500

# -------------------------------
# RUN APPLICATION
# -------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=app.config["DEBUG"])
