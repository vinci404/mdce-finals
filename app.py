from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort
import mysql.connector
import os
import uuid
from functools import wraps

app = Flask(__name__)
app.secret_key = "change-this-to-any-random-text"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


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
@login_required
def dashboard():
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)

    cur.execute("SELECT COUNT(*) AS n FROM jeeps")
    jeeps = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM drivers")
    drivers = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM documents")
    docs = cur.fetchone()["n"]

    expiring = get_expiring(cur)

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

# ---------- DOCKTRACK ----------
DOC_DIR = os.path.join(app.root_path, "uploads", "documents")
ALLOWED_DOCS = {"pdf", "png", "jpg", "jpeg", "webp"}
DOC_TYPES = ["OR", "CR", "PA", "Decision", "ICAR", "ID", "License", "Other"]

def save_document(file):
    if not file or file.filename == "":
        raise ValueError("Please choose a file to upload.")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_DOCS:
        raise ValueError("File must be a pdf, png, jpg, jpeg or webp.")
    os.makedirs(DOC_DIR, exist_ok=True)
    name = uuid.uuid4().hex + "." + ext
    file.save(os.path.join(DOC_DIR, name))
    return name

def get_expiring(cur, days=30):
    """Everything expired or expiring within `days`: documents, jeep registrations, driver licenses."""
    cur.execute("""
        SELECT 'Jeep registration' AS what, j.plate_no AS who,
               j.registration_expiry AS expiry,
               DATEDIFF(j.registration_expiry, CURDATE()) AS days_left
        FROM jeeps j
        WHERE j.registration_expiry IS NOT NULL
          AND j.registration_expiry <= DATE_ADD(CURDATE(), INTERVAL %s DAY)
        UNION ALL
        SELECT 'Driver license', dr.full_name, dr.license_expiry,
               DATEDIFF(dr.license_expiry, CURDATE())
        FROM drivers dr
        WHERE dr.license_expiry IS NOT NULL
          AND dr.license_expiry <= DATE_ADD(CURDATE(), INTERVAL %s DAY)
        UNION ALL
        SELECT d.doc_type, COALESCE(j.plate_no, dr.full_name), d.expiry_date,
               DATEDIFF(d.expiry_date, CURDATE())
        FROM documents d
        LEFT JOIN jeeps j ON d.jeep_id = j.id
        LEFT JOIN drivers dr ON d.driver_id = dr.id
        WHERE d.expiry_date IS NOT NULL
          AND d.expiry_date <= DATE_ADD(CURDATE(), INTERVAL %s DAY)
        ORDER BY expiry
    """, (days, days, days))
    return cur.fetchall()

@app.route("/docs")
@login_required
def docs_list():
    doc_type = request.args.get("type")
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    sql = """
        SELECT d.*, j.jeep_no, j.plate_no, dr.full_name AS driver_name,
               DATEDIFF(d.expiry_date, CURDATE()) AS days_left
        FROM documents d
        LEFT JOIN jeeps j ON d.jeep_id = j.id
        LEFT JOIN drivers dr ON d.driver_id = dr.id
    """
    if doc_type in DOC_TYPES:
        cur.execute(sql + " WHERE d.doc_type = %s ORDER BY d.doc_date DESC, d.id DESC", (doc_type,))
    else:
        doc_type = None
        cur.execute(sql + " ORDER BY d.doc_date DESC, d.id DESC")
    docs = cur.fetchall()
    expiring = get_expiring(cur)
    cur.close()
    db.close()
    return render_template("docs.html", docs=docs, expiring=expiring,
                           doc_types=DOC_TYPES, current_type=doc_type)

@app.route("/docs/add", methods=["GET", "POST"])
@login_required
def docs_add():
    db = get_db()
    cur = db.cursor(dictionary=True, buffered=True)
    error = None
    try:
        if request.method == "POST":
            f = request.form
            kind, _, oid = f.get("owner", "").partition(":")
            if kind not in ("jeep", "driver") or not oid.isdigit():
                error = "Choose which jeep or driver this document belongs to."
            elif f.get("doc_type") not in DOC_TYPES:
                error = "Choose a document type."
            else:
                try:
                    stored = save_document(request.files.get("file"))
                except ValueError as e:
                    error = str(e)
                else:
                    cur.execute("""
                        INSERT INTO documents
                          (jeep_id, driver_id, doc_type, doc_date, expiry_date, file_path)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (int(oid) if kind == "jeep" else None,
                          int(oid) if kind == "driver" else None,
                          f["doc_type"], f.get("doc_date") or None,
                          f.get("expiry_date") or None, stored))
                    db.commit()
                    return redirect(url_for("docs_list"))
        cur.execute("SELECT id, jeep_no, plate_no FROM jeeps ORDER BY jeep_no")
        jeeps = cur.fetchall()
        cur.execute("SELECT id, full_name FROM drivers ORDER BY full_name")
        drivers = cur.fetchall()
        return render_template("doc_form.html", form=request.form, jeeps=jeeps,
                               drivers=drivers, doc_types=DOC_TYPES, error=error)
    finally:
        cur.close()
        db.close()

@app.route("/docs/<int:doc_id>/file")
@login_required
def docs_file(doc_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT file_path FROM documents WHERE id = %s", (doc_id,))
    row = cur.fetchone()
    cur.close()
    db.close()
    if not row:
        abort(404)
    return send_from_directory(DOC_DIR, row["file_path"])

@app.route("/docs/<int:doc_id>/delete", methods=["POST"])
@login_required
def docs_delete(doc_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT file_path FROM documents WHERE id = %s", (doc_id,))
    row = cur.fetchone()
    if row:
        cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
        db.commit()
        try:
            os.remove(os.path.join(DOC_DIR, row["file_path"]))
        except OSError:
            pass
    cur.close()
    db.close()
    return redirect(url_for("docs_list"))

if __name__ == "__main__":
    app.run(debug=True)