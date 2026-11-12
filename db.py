import mysql.connector


class Database:
    def __init__(
        self,
        host="localhost",
        user="root",
        password="",
        database="mdce_fleethub",
    ):
        self.host = host
        self.user = user
        self.password = password
        self.database = database

    def connect(self, admin_id=None):
        conn = mysql.connector.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
        )

        try:
            cur = conn.cursor()
            try:
                cur.execute("SET @admin_id = %s", (admin_id,))
            finally:
                cur.close()
        except Exception:
            conn.close()
            raise

        return conn
