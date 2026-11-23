
import sqlite3
from pathlib import Path

# Project paths
BASE_DIR = Path(__file__).resolve().parent
from config import Config

DATABASE_PATH = Config.DATABASE_PATH


def get_connection():
    """Create and return a database connection."""

    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def init_db():
    """Create all initial FinWise database tables."""

    connection = get_connection()
    cursor = connection.cursor()

    # 1. Businesses table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT NOT NULL,
            business_type TEXT,
            currency TEXT NOT NULL DEFAULT 'INR',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
        # 2. Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
                CHECK(role IN ('owner', 'manager')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (business_id)
                REFERENCES businesses(id)
        )
    """)

    # Allow only one owner per business
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_one_owner_per_business
        ON users (business_id)
        WHERE role = 'owner'
    """)

    # 2. Categories table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            category_name TEXT NOT NULL,
            category_type TEXT NOT NULL
                CHECK(category_type IN ('Income', 'Expense')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (business_id)
                REFERENCES businesses(id),

            UNIQUE (business_id, category_name, category_type)
        )
    """)

    # 3. Transactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            category_id INTEGER,
            transaction_type TEXT NOT NULL
                CHECK(transaction_type IN ('Income', 'Expense')),
            amount REAL NOT NULL CHECK(amount > 0),
            description TEXT,
            transaction_date DATE NOT NULL,
            payment_method TEXT DEFAULT 'Other',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (business_id)
                REFERENCES businesses(id),

            FOREIGN KEY (category_id)
                REFERENCES categories(id)
        )
    """)

    # 4. Budgets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            category_id INTEGER,
            budget_amount REAL NOT NULL CHECK(budget_amount > 0),
            budget_month TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (business_id)
                REFERENCES businesses(id),

            FOREIGN KEY (category_id)
                REFERENCES categories(id),

            UNIQUE (business_id, category_id, budget_month)
        )
    """)
        # 5. Pending transaction drafts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            transaction_data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (business_id)
                REFERENCES businesses(id),

            FOREIGN KEY (user_id)
                REFERENCES users(id)
        )
    """)

    # Improve transaction search performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_transactions_business_date
        ON transactions (business_id, transaction_date)
    """)

    # Create a demo business if one does not exist
    cursor.execute("""
        SELECT id FROM businesses LIMIT 1
    """)

    business = cursor.fetchone()

    if business is None:
        cursor.execute("""
            INSERT INTO businesses (business_name, business_type, currency)
            VALUES (?, ?, ?)
        """, ("FinWise Demo Business", "Small Business", "INR"))

        business_id = cursor.lastrowid

        # Default income and expense categories
        categories = [
            ("Sales Revenue", "Income"),
            ("Service Revenue", "Income"),
            ("Other Income", "Income"),
            ("Inventory", "Expense"),
            ("Rent", "Expense"),
            ("Salaries", "Expense"),
            ("Utilities", "Expense"),
            ("Marketing", "Expense"),
            ("Transportation", "Expense"),
            ("Equipment", "Expense"),
            ("Other Expenses", "Expense")
        ]

        cursor.executemany("""
            INSERT INTO categories
            (business_id, category_name, category_type)
            VALUES (?, ?, ?)
        """, [
            (business_id, name, category_type)
            for name, category_type in categories
        ])

    connection.commit()
    connection.close()

    print("FinWise AI database initialized successfully!")


if __name__ == "__main__":
    init_db()
