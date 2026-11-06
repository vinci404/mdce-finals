from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
import os
import uuid
from functools import wraps

app = Flask(__name__)
app.secret_key = "change-this-to-any-random-text"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

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

# ---------- DRIVERS ----------
UPLOAD_DIR = os.path.join(app.root_path, "static", "uploads", "drivers")
ALLOWED_PHOTOS = {"png", "jpg", "jpeg", "webp"}

def save_photo(file):
    """Save an uploaded photo and return its path, or None if no file was chosen."""
    if not file or file.filename == "":
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_PHOTOS:
        raise ValueError("Photo must be a png, jpg, jpeg or webp file.")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = uuid.uuid4().hex + "." + ext
    file.save(os.path.join(UPLOAD_DIR, name))
    return "uploads/drivers/" + name

def free_jeeps(cur, current=None):
    """Jeeps with no driver yet, plus the driver's current jeep when editing."""
    cur.execute("""
        SELECT id, jeep_no, plate_no FROM jeeps
        WHERE id NOT IN (SELECT jeep_id FROM drivers WHERE jeep_id IS NOT NULL)
           OR id = %s
        ORDER BY jeep_no
    """, (current,))
    return cur.fetchall()

def clean_driver_form(form):
    keys = ["full_name", "birth_date", "address", "contact_no", "license_no",
            "license_expiry", "date_joined", "emergency_name", "emergency_contact_no"]
    data = {k: (form.get(k) or None) for k in keys}
    data["jeep_id"] = int(form["jeep_id"]) if form.get("jeep_id") else None
    data["assigned_since"] = form.get("assigned_since") or None
    return data

def driver_values(data, photo):
    return (data["full_name"], photo, data["birth_date"], data["address"],
            data["contact_no"], data["license_no"], data["license_expiry"],
            data["jeep_id"], data["date_joined"], data["emergency_name"],
            data["emergency_contact_no"])

@app.route("/drivers")
@login_required
def drivers_list():
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    cur.execute("""
        SELECT d.*, TIMESTAMPDIFF(YEAR, d.birth_date, CURDATE()) AS age,
               j.jeep_no, j.plate_no
        FROM drivers d
        LEFT JOIN jeeps j ON d.jeep_id = j.id
        ORDER BY d.full_name
    """)
    rows = cur.fetchall()
    cur.close()
    db.close()
    return render_template("drivers.html", drivers=rows)

@app.route("/drivers/add", methods=["GET", "POST"])
@login_required
def driver_add():
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    error = None
    try:
        if request.method == "POST":
            data = clean_driver_form(request.form)
            try:
                photo = save_photo(request.files.get("photo"))
                cur.execute("""
                    INSERT INTO drivers (full_name, photo_path, birth_date, address,
                        contact_no, license_no, license_expiry, jeep_id, date_joined,
                        emergency_name, emergency_contact_no)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, driver_values(data, photo))
                if data["jeep_id"]:
                    cur.execute(
                        "UPDATE jeeps SET driver_assigned_since = COALESCE(%s, CURDATE()) WHERE id = %s",
                        (data["assigned_since"], data["jeep_id"]))
                db.commit()
                return redirect(url_for("drivers_list"))
            except ValueError as e:
                error = str(e)
            except mysql.connector.IntegrityError:
                db.rollback()
                error = "That jeep is already assigned to another driver."
        jeeps = free_jeeps(cur)
        return render_template("driver_form.html", driver=request.form, jeeps=jeeps,
                               error=error, title="Add driver")
    finally:
        cur.close()
        db.close()

@app.route("/drivers/<int:driver_id>/edit", methods=["GET", "POST"])
@login_required
def driver_edit(driver_id):
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    error = None
    try:
        cur.execute("""
            SELECT d.*, j.driver_assigned_since AS assigned_since
            FROM drivers d LEFT JOIN jeeps j ON d.jeep_id = j.id
            WHERE d.id = %s
        """, (driver_id,))
        driver = cur.fetchone()
        if not driver:
            return redirect(url_for("drivers_list"))
        current_jeep = driver["jeep_id"]

        if request.method == "POST":
            data = clean_driver_form(request.form)
            try:
                photo = save_photo(request.files.get("photo")) or driver["photo_path"]
                cur.execute("""
                    UPDATE drivers SET full_name=%s, photo_path=%s, birth_date=%s,
                        address=%s, contact_no=%s, license_no=%s, license_expiry=%s,
                        jeep_id=%s, date_joined=%s, emergency_name=%s,
                        emergency_contact_no=%s
                    WHERE id=%s
                """, driver_values(data, photo) + (driver_id,))
                if current_jeep and current_jeep != data["jeep_id"]:
                    cur.execute("UPDATE jeeps SET driver_assigned_since = NULL WHERE id = %s",
                                (current_jeep,))
                if data["jeep_id"]:
                    cur.execute(
                        "UPDATE jeeps SET driver_assigned_since = COALESCE(%s, CURDATE()) WHERE id = %s",
                        (data["assigned_since"], data["jeep_id"]))
                db.commit()
                return redirect(url_for("drivers_list"))
            except ValueError as e:
                error = str(e)
            except mysql.connector.IntegrityError:
                db.rollback()
                error = "That jeep is already assigned to another driver."
            driver = {**driver, **request.form.to_dict()}

        jeeps = free_jeeps(cur, current_jeep)
        return render_template("driver_form.html", driver=driver, jeeps=jeeps,
                               error=error, title="Edit driver")
    finally:
        cur.close()
        db.close()

@app.route("/drivers/<int:driver_id>/delete", methods=["POST"])
@login_required
def driver_delete(driver_id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE jeeps SET driver_assigned_since = NULL
            WHERE id = (SELECT jeep_id FROM drivers WHERE id = %s)
        """, (driver_id,))
        cur.execute("DELETE FROM drivers WHERE id = %s", (driver_id,))
        db.commit()
    except mysql.connector.IntegrityError:
        db.rollback()
        flash("Can't delete this driver: documents or issue reports are linked to them.")
    finally:
        cur.close()
        db.close()
    return redirect(url_for("drivers_list"))

if __name__ == "__main__":
    app.run(debug=True)