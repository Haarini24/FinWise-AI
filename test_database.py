
from database import get_connection

def test_database():
    connection = get_connection()

    print("\nFINWISE AI - DATABASE TEST")
    print("---------------------------")

    # Check database tables
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()

    print("\nDatabase Tables:")
    for table in tables:
        print("-", table["name"])

    # Check demo business
    businesses = connection.execute(
        "SELECT * FROM businesses"
    ).fetchall()

    print("\nRegistered Businesses:")
    for business in businesses:
        print(dict(business))

    # Check categories
    categories = connection.execute(
        "SELECT * FROM categories"
    ).fetchall()

    print("\nDefault Categories:")
    for category in categories:
        print(dict(category))

    connection.close()

    print("\nDatabase test completed successfully!")


if __name__ == "__main__":
    test_database()

