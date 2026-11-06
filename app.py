from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector

app = Flask(__name__)
app.secret_key = "change-this-to-any-random-text"

def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="mdce_fleethub"
    )

@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM admin WHERE email = %s AND password = %s",
            (email, password)
        )
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user:
            session["admin_id"] = user["id"]
            session["admin_name"] = user["full_name"]
            return redirect(url_for("dashboard"))
        error = "Wrong email or password."
    return render_template("login.html", error=error)

@app.route("/dashboard")
def dashboard():
    if "admin_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute("SELECT COUNT(*) AS n FROM jeeps")
    jeeps = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM drivers")
    drivers = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM documents")
    docs = cur.fetchone()["n"]

    cur.execute("""
        SELECT d.doc_type, d.expiry_date, j.plate_no, dr.full_name
        FROM documents d
        LEFT JOIN jeeps j ON d.jeep_id = j.id
        LEFT JOIN drivers dr ON d.driver_id = dr.id
        WHERE d.expiry_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 30 DAY)
        ORDER BY d.expiry_date
    """)
    expiring = cur.fetchall()

    cur.close()
    db.close()
    return render_template("dashboard.html", name=session["admin_name"],
                           jeeps=jeeps, drivers=drivers, docs=docs, expiring=expiring)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)