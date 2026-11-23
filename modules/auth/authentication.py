import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_connection


def create_owner(full_name, email, password):
    """Create the first owner account for the existing business."""

    full_name = full_name.strip()
    email = email.strip().lower()

    if not full_name or not email or not password:
        raise ValueError("All fields are required.")

    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters.")

    connection = get_connection()

    try:
        # Ensure that no owner already exists
        owner = connection.execute("""
            SELECT id FROM users
            WHERE role = 'owner'
        """).fetchone()

        if owner:
            raise ValueError("An owner account already exists.")

        # Use the existing FinWise business
        business = connection.execute("""
            SELECT id FROM businesses
            ORDER BY id
            LIMIT 1
        """).fetchone()

        if not business:
            raise ValueError("No business found. Initialize the database first.")

        password_hash = generate_password_hash(password)

        cursor = connection.execute("""
            INSERT INTO users (
                business_id,
                full_name,
                email,
                password_hash,
                role
            )
            VALUES (?, ?, ?, ?, 'owner')
        """, (
            business["id"],
            full_name,
            email,
            password_hash
        ))

        connection.commit()

        return cursor.lastrowid

    finally:
        connection.close()


def create_manager(full_name, email, password, business_id):
    """Create a manager account for the owner's business."""

    full_name = full_name.strip()
    email = email.strip().lower()

    if not full_name or not email or not password:
        raise ValueError("All fields are required.")

    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters.")

    connection = get_connection()

    try:
        password_hash = generate_password_hash(password)

        cursor = connection.execute("""
            INSERT INTO users (
                business_id,
                full_name,
                email,
                password_hash,
                role
            )
            VALUES (?, ?, ?, ?, 'manager')
        """, (
            business_id,
            full_name,
            email,
            password_hash
        ))

        connection.commit()
        return cursor.lastrowid

    except sqlite3.IntegrityError:
        connection.rollback()
        raise ValueError("This email address is already registered.")

    finally:
        connection.close()



def verify_login(email, password):
    """Verify login credentials and return safe user information."""

    connection = get_connection()

    try:
        user = connection.execute("""
            SELECT id, business_id, full_name, email,
                   password_hash, role, is_active
            FROM users
            WHERE email = ?
        """, (email.strip().lower(),)).fetchone()

        if not user:
            return None

        if not user["is_active"]:
            return None

        if not check_password_hash(user["password_hash"], password):
            return None

        return {
            "id": user["id"],
            "business_id": user["business_id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "role": user["role"]
        }

    finally:
        connection.close()
