import sqlite3

from pipeline import config


def get_connection() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    schema_sql = (config.SQL_DIR / "schema.sql").read_text(encoding="utf-8")
    conn = get_connection()
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    conn = get_connection()
    objects = conn.execute(
        "SELECT type, name FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    ).fetchall()
    conn.close()

    print(f"Database ready at {config.DB_PATH}")
    for obj in objects:
        print(f"  {obj['type']:<8} {obj['name']}")