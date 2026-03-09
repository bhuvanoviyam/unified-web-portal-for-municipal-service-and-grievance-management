from flask import Flask, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import mysql.connector
import os
import math

app = Flask(__name__)
app.secret_key = "your_secret_key"

# ---------------- DATABASE CONNECTION ------------------
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="problem_system"
)

# ---------------- FILE UPLOAD PATH ----------------------
UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


# ---------------- AUTO DETECT DEPARTMENT ---------------
def auto_detect_department(text):
    text = text.lower()

    if any(w in text for w in ["road", "street", "pothole", "bridge"]):
        return "Road Department"

    if any(w in text for w in ["water", "pipe", "leak"]):
        return "Water Department"

    if any(w in text for w in ["light", "electric", "transformer"]):
        return "Electricity Department"

    if any(w in text for w in ["garbage", "waste", "trash", "dustbin"]):
        return "Waste Management"

    if any(w in text for w in ["health", "clean", "mosquito"]):
        return "Health Department"

    return None


# ---------------- PARSE LOCATION -----------------------
def parse_location(loc):
    try:
        lat, lon = loc.split(",")
        return float(lat), float(lon)
    except:
        return None, None


# ---------------- DUPLICATE CHECK ----------------------
def is_duplicate(location, user_id):
    lat1, lon1 = parse_location(location)

    if lat1 is None:
        return None

    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, location FROM problems WHERE user_id=%s ORDER BY id DESC LIMIT 20",
        (user_id,)
    )
    data = cursor.fetchall()

    for row in data:
        lat2, lon2 = parse_location(row["location"])

        if lat2 is None:
            continue

        dist = math.dist([lat1, lon1], [lon2, lon2])

        if dist < 0.003:  # ~300 meters
            return row["id"]

    return None


# ---------------- LOGIN PAGE ---------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        cursor.execute(
            "SELECT * FROM users WHERE username=%s AND role=%s",
            (username, role)
        )
        user = cursor.fetchone()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]

            return redirect("/dashboard")

        flash("Invalid login!", "error")

    return render_template("login.html")


# ---------------- DASHBOARD -----------------------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    return render_template("dashboard.html")


# ---------------- UPLOAD PROBLEM ------------------------
@app.route("/upload_problem", methods=["GET", "POST"])
def upload_problem():

    if "user_id" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)

    # Load departments from DB
    cursor.execute("SELECT name FROM departments")
    departments = [d["name"] for d in cursor.fetchall()]

    if request.method == "POST":

        desc = request.form.get("description")
        priority = request.form.get("priority")
        dept_from_user = request.form.get("department")

        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")

        location = f"{latitude},{longitude}"

        # Auto department override
        auto_dep = auto_detect_department(desc)
        final_dep = auto_dep if auto_dep else dept_from_user

        # Duplicate check
        dup = is_duplicate(location, session["user_id"])
        if dup:
            flash(f"Duplicate detected! Similar report exists (ID: {dup}).", "error")
            return redirect("/my_problems")

        # IMAGE UPLOAD
        image = request.files.get("image")
        filename = None

        if image and image.filename:
            filename = secure_filename(image.filename)
            image.save(os.path.join(UPLOAD_FOLDER, filename))

        # INSERT INTO DB
        sql = """
            INSERT INTO problems 
              (user_id, department, description, priority, image_path, location, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'Pending')
        """

        values = (
            session["user_id"],
            final_dep,
            desc,
            priority,
            filename,
            location
        )

        cursor.execute(sql, values)
        db.commit()

        flash("Problem submitted successfully!", "success")
        return redirect("/my_problems")

    return render_template("upload_problem.html", departments=departments)


# ---------------- MY PROBLEMS --------------------------
@app.route("/my_problems")
def my_problems():

    if "user_id" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM problems WHERE user_id=%s ORDER BY id DESC", (session["user_id"],))
    records = cursor.fetchall()

    return render_template("my_problems.html", problems=records)


# ---------------- LOGOUT -------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- RUN APP ------------------------------
if __name__ == "__main__":
    app.run(debug=True)
