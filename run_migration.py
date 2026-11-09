"""
One-click migration script to apply supabase_setup_and_migrate.sql to Supabase PostgreSQL.
Usage:
    python run_migration.py "postgresql://postgres.[ref]:[password]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?sslmode=require"
"""
import sys
import os
from pathlib import Path

def main():
    db_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not provided.")
        print("Usage: python run_migration.py <DATABASE_URL>")
        sys.exit(1)

    try:
        import psycopg2
    except ImportError:
        print("Installing psycopg2-binary...")
        os.system(f'"{sys.executable}" -m pip install psycopg2-binary')
        import psycopg2

    sql_path = Path(__file__).parent / "supabase_setup_and_migrate.sql"
    if not sql_path.exists():
        print(f"Error: {sql_path} not found.")
        sys.exit(1)

    sql_content = sql_path.read_text(encoding="utf-8")
    print("Connecting to Supabase PostgreSQL...")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()
    print("Applying schema and migrating data...")
    cur.execute(sql_content)
    cur.close()
    conn.close()
    print("✅ Migration completed successfully! All tables and data are now in Supabase.")

if __name__ == "__main__":
    main()

