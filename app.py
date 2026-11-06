from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from functools import wraps

app = Flask(__name__)
app.secret_key = "change-this-to-any-random-text"

def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="mdce_fleethub"
    )
    from functools import wraps

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

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

@app.route("/jeeps")
@login_required
def jeeps_list():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT j.*, d.full_name AS driver_name
        FROM jeeps j
        LEFT JOIN drivers d ON d.jeep_id = j.id
        ORDER BY j.jeep_no
    """)
    rows = cur.fetchall()
    cur.close()
    db.close()
    return render_template("jeeps.html", jeeps=rows)

@app.route("/jeeps/add", methods=["GET", "POST"])
@login_required
def jeep_add():
    error = None
    if request.method == "POST":
        f = request.form
        db = get_db()
        cur = db.cursor()
        try:
            cur.execute(
                "INSERT INTO jeeps (jeep_no, plate_no, route, registration_expiry) "
                "VALUES (%s, %s, %s, %s)",
                (f["jeep_no"], f["plate_no"], f["route"], f["registration_expiry"] or None)
            )
            db.commit()
            return redirect(url_for("jeeps_list"))
        except mysql.connector.IntegrityError:
            error = "That jeep no. or plate no. already exists."
        finally:
            cur.close()
            db.close()
    return render_template("jeep_form.html", jeep=request.form, error=error, title="Add jeep")

@app.route("/jeeps/<int:jeep_id>/edit", methods=["GET", "POST"])
@login_required
def jeep_edit(jeep_id):
    error = None
    db = get_db()
    cur = db.cursor(dictionary=True)
    try:
        if request.method == "POST":
            f = request.form
            try:
                cur.execute(
                    "UPDATE jeeps SET jeep_no=%s, plate_no=%s, route=%s, registration_expiry=%s "
                    "WHERE id=%s",
                    (f["jeep_no"], f["plate_no"], f["route"],
                     f["registration_expiry"] or None, jeep_id)
                )
                db.commit()
                return redirect(url_for("jeeps_list"))
            except mysql.connector.IntegrityError:
                error = "That jeep no. or plate no. already exists."
        cur.execute("SELECT * FROM jeeps WHERE id = %s", (jeep_id,))
        jeep = cur.fetchone()
        if not jeep:
            return redirect(url_for("jeeps_list"))
        return render_template("jeep_form.html", jeep=jeep, error=error, title="Edit jeep")
    finally:
        cur.close()
        db.close()

@app.route("/jeeps/<int:jeep_id>/delete", methods=["POST"])
@login_required
def jeep_delete(jeep_id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM jeeps WHERE id = %s", (jeep_id,))
        db.commit()
    except mysql.connector.IntegrityError:
        flash("Can't delete this jeep: it still has a driver, documents or issues linked to it.")
    finally:
        cur.close()
        db.close()
    return redirect(url_for("jeeps_list"))

if __name__ == "__main__":
    app.run(debug=True)