# project.py
import os
import time
import imghdr
import math
import datetime

from flask import Flask, render_template, request, redirect, session, flash, url_for
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

import mysql.connector
from mysql.connector import Error

# Image libs
import cv2
from PIL import Image
import numpy as np

# -------------------
# Configuration
# -------------------
app = Flask(__name__)
app.secret_key = "replace_this_with_a_real_secret_key"

UPLOAD_FOLDER = "static/uploads"
PROOF_FOLDER = "static/proofs"

for p in (UPLOAD_FOLDER, PROOF_FOLDER):
    if not os.path.exists(p):
        os.makedirs(p)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["PROOF_FOLDER"] = PROOF_FOLDER

# -------------------
# DB helper
# -------------------
def get_db():
    try:
        connection = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",       # <-- set your password
            database="problem_reporting_system",
            charset='utf8'
        )
        return connection
    except Error as e:
        print("Database connection error:", e)
        return None

# -------------------
# Utility: auto detect department (simple keyword based)
# -------------------
def auto_detect_department(text):
    if not text:
        return None
    t = text.lower()
    if any(w in t for w in ["road", "street", "pothole", "asphalt", "bridge"]):
        return "Road Maintenance"
    if any(w in t for w in ["water", "pipe", "leak", "tap", "drain"]):
        return "Water Supply"
    if any(w in t for w in ["light", "electric", "transformer", "power", "electricity"]):
        return "Electricity"
    if any(w in t for w in ["garbage", "waste", "trash", "bin", "dump"]):
        return "Public Safety"
    if any(w in t for w in ["health", "clinic", "mosquito", "sanitation"]):
        return "Health Department"
    return None

# -------------------
# Image quality functions
# -------------------
def is_image_blurry(image_path, threshold=100):
    """Return True if blurry (variance below threshold)."""
    try:
        img = cv2.imread(image_path)
        if img is None:
            return True
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        var = cv2.Laplacian(gray, cv2.CV_64F).var()
        # debug print
        print("Blur score:", var)
        return var < threshold
    except Exception as e:
        print("is_image_blurry error:", e)
        return True

def is_low_resolution(image_path, min_width=350, min_height=350):
    """Return True if resolution is below limits."""
    try:
        img = Image.open(image_path)
        w, h = img.size
        print("Resolution:", w, "x", h)
        return w < min_width or h < min_height
    except Exception as e:
        print("is_low_resolution error:", e)
        return True

def is_old_image(image_path, max_days=3):
    """Return True if file modified time older than `max_days`."""
    try:
        mtime = os.path.getmtime(image_path)
        age_days = (time.time() - mtime) / 86400.0
        print("Image age (days):", age_days)
        return age_days > max_days
    except Exception as e:
        print("is_old_image error:", e)
        return True

# -------------------
# Duplicate location detection (Haversine)
# -------------------
def is_duplicate(location, user_id, radius_meters=50):
    """
    Returns True if an existing problem from the same user is within radius_meters.
    location: "lat,lon" string
    """
    try:
        lat1, lon1 = map(float, location.split(","))
    except:
        return False

    db = get_db()
    if db is None:
        return False
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT location FROM problems WHERE user_id=%s", (user_id,))
    rows = cur.fetchall()
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371.0  # km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c * 1000.0  # meters

    for r in rows:
        if not r.get("location"):
            continue
        try:
            lat2, lon2 = map(float, r["location"].split(","))
        except:
            continue
        dist = haversine(lat1, lon1, lat2, lon2)
        if dist <= radius_meters:
            return True
    return False

# -------------------
# ROUTES
# -------------------

@app.route("/")
def home():
    username = session.get("username")
    return render_template("home.html", title="Problem Reporting System", username=username)

# ----------------- AUTH -----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        username = request.form.get("username")
        mobile = request.form.get("mobile")
        address = request.form.get("address")
        password = request.form.get("password")

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT username FROM users WHERE username=%s", (username,))
        if cur.fetchone():
            flash("Username already exists! Choose another one.", "error")
            return redirect("/signup")

        hashed = generate_password_hash(password)
        cur.execute("INSERT INTO users (name, username, mobile, address, password) VALUES (%s,%s,%s,%s,%s)",
                    (name, username, mobile, address, hashed))
        db.commit()
        flash("Account created successfully! Please login.", "success")
        return redirect("/login")
    return render_template("signup.html")

@app.route("/officer_signup", methods=["GET", "POST"])
def officer_signup():
    # Admin should normally create officers; but keeping signup route as you had
    if request.method == "POST":
        name = request.form.get("name")
        username = request.form.get("username")
        department_id = request.form.get("department")  # this is the id from form
        mobile = request.form.get("mobile")
        address = request.form.get("address")
        password = request.form.get("password")

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT username FROM officers WHERE username=%s", (username,))
        if cur.fetchone():
            flash("Officer username already exists!", "error")
            return redirect("/officer_signup")

        # Get department name from id
        cur.execute("SELECT department_name FROM departments WHERE id=%s", (department_id,))
        dept_row = cur.fetchone()
        if dept_row:
            dept_name = dept_row[0]
        else:
            dept_name = department_id  # fallback

        hashed = generate_password_hash(password)
        # store department name in department_id (varchar)
        cur.execute("INSERT INTO officers (name, username, department_id, mobile, address, password) VALUES (%s,%s,%s,%s,%s,%s)",
                    (name, username, dept_name, mobile, address, hashed))
        db.commit()
        flash("Officer account created.", "success")
        return redirect("/login")
    # render form
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT id, department_name FROM departments")
    depts = cur.fetchall()
    return render_template("officer_signup.html", departments=depts)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        uname = request.form.get("username")
        pw = request.form.get("password")

        db = get_db()
        cur = db.cursor(dictionary=True)

        # citizen
        cur.execute("SELECT * FROM users WHERE username=%s", (uname,))
        user = cur.fetchone()
        if user:
            if check_password_hash(user["password"], pw):
                session["username"] = user["username"]
                session["role"] = "citizen"
                session["user_id"] = user["id"]
                return redirect("/dashboard")
            else:
                flash("Wrong password!", "error")
                return redirect("/login")

        # officer
        cur.execute("SELECT * FROM officers WHERE username=%s", (uname,))
        officer = cur.fetchone()
        if officer:
            if check_password_hash(officer["password"], pw):
                session["username"] = officer["username"]
                session["role"] = "officer"
                session["officer_id"] = officer["id"]
                return redirect("/dashboard")
            else:
                flash("Wrong password!", "error")
                return redirect("/login")

        # admin (your DB stores admin.password plain in dump; check both)
        cur.execute("SELECT * FROM admin WHERE username=%s and password=%s", (uname,pw))
        admin = cur.fetchone()
        if admin is None:
            flash("Wrong password!", "error")
            return redirect("/login")

        else:
                session["username"] = admin["username"]
                session["role"] = "admin"
                session["admin_id"] = admin["id"]
                return redirect("/dashboard")


        flash("Username not found!", "error")
        return redirect("/login")
    return render_template("login.html")
@app.route("/officer_login", methods=["GET", "POST"])
def officer_login():
    return render_template("login.html")
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    return render_template("login.html")
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect("/")

# ----------------- DASHBOARD -----------------
@app.route("/dashboard")
def dashboard():
    if "role" not in session:
        return redirect("/login")
    role = session["role"]

    db = get_db()
    cur = db.cursor(dictionary=True)

    if role == "citizen":
        user_id = session["user_id"]
        # counts
        cur.execute("SELECT COUNT(*) AS total FROM problems WHERE user_id=%s", (user_id,))
        total = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS total FROM problems WHERE status='Pending' AND user_id=%s", (user_id,))
        pending = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS total FROM problems WHERE status='Ongoing' AND user_id=%s", (user_id,))
        ongoing = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS total FROM problems WHERE status='Completed' AND user_id=%s", (user_id,))
        completed = cur.fetchone()["total"]

        recent_activities = [
            {"title": "Your complaint was assigned", "time": "10 min ago", "icon": "📌", "color": "blue"},
            {"title": "Officer updated your complaint", "time": "1 hour ago", "icon": "🔧", "color": "green"}
        ]

        # calendar small
        today = datetime.date.today()
        calendar = []
        day_num = 1
        for week in range(2):
            row = []
            for d in range(7):
                row.append({"num": day_num, "is_today": (day_num == today.day)})
                day_num += 1
            calendar.append(row)

        return render_template("citizen_dashboard.html",
                               total_problems=total, pending=pending, ongoing=ongoing, completed=completed,
                               recent_activities=recent_activities, calendar=calendar)

    if role == "officer":
        return render_template("officer_dashboard.html")

    if role == "admin":
        cur.execute("SELECT COUNT(*) AS total FROM users")
        users = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS total FROM officers")
        officers = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS total FROM problems")
        complaints = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS total FROM problems WHERE status='Pending'")
        pending = cur.fetchone()["total"]
        cur.execute("""
            SELECT p.id, u.username, p.description, p.department, p.status
            FROM problems p LEFT JOIN users u ON p.user_id=u.id
            ORDER BY p.created_at DESC LIMIT 10
        """)
        recent = cur.fetchall()
        return render_template("admin_dashboard.html",
                               users=users, officers=officers, complaints=complaints, pending=pending,
                               recent_problems=recent)
    return "Role not recognized", 403

# ----------------- MY PROBLEMS / VIEW -----------------
@app.route("/my_problems")
def my_problems():
    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect("/login")
    user_id = session["user_id"]
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT id, department,description, status, proof_image, image_path, created_at, latitude, longitude FROM problems WHERE user_id=%s ORDER BY created_at DESC", (user_id,))
    problems = cur.fetchall()
    print(problems)
    cur.execute("SELECT COUNT(*) AS total FROM problems WHERE user_id=%s", (user_id,))
    total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS c FROM problems WHERE user_id=%s AND status='Pending'", (user_id,))
    pending = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM problems WHERE user_id=%s AND status='Ongoing'", (user_id,))
    ongoing = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM problems WHERE user_id=%s AND status='Completed'", (user_id,))
    completed = cur.fetchone()["c"]
    recent = [
        {"title": "Your issue was assigned to Officer", "time": "10 min ago", "color": "blue", "icon": "📌"},
        {"title": "Officer updated your problem", "time": "1 hour ago", "color": "green", "icon": "🔧"}
    ]
    calendar_data = [
        [{"num":1},{"num":2},{"num":3},{"num":4},{"num":5},{"num":6},{"num":7}],
        [{"num":8},{"num":9},{"num":10},{"num":11},{"num":12},{"num":13},{"num":14}],
    ]
    return render_template("my_problems.html", problems=problems, total_problems=total,
                           pending=pending, ongoing=ongoing, completed=completed,
                           recent_activities=recent, calendar=calendar_data)



# ----------------- UPLOAD PROBLEM -----------------
@app.route("/upload_problem", methods=["GET", "POST"])
def upload_problem():
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    if db is None:
        flash("Database connection error", "error")
        return redirect("/dashboard")
    cursor = db.cursor(dictionary=True)

    # load departments
    cursor.execute("SELECT department_name FROM departments")
    departments = [d["department_name"] for d in cursor.fetchall()]

    if request.method == "POST":
        desc = request.form.get("description")
        priority = request.form.get("priority")
        dept_from_user = request.form.get("department")
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        location = f"{latitude},{longitude}"

        # Duplicate check (optional) — you can enable
        '''if is_duplicate(location, session["user_id"], radius_meters=50):
            flash("A similar complaint already exists near this location.", "error")
            return redirect("/upload_problem")'''

        auto_dep = auto_detect_department(desc)
        final_dep = auto_dep if auto_dep else dept_from_user

        # auto assign officer by department_id (your DB stores department_id as varchar)
        cursor.execute("SELECT id FROM officers WHERE department_id=%s ORDER BY id ASC LIMIT 1", (final_dep,))
        officer = cursor.fetchone()
        assigned_officer_id = officer["id"] if officer else None

        # IMAGE HANDLING
        image = request.files.get("image")
        filename = None
        if image and image.filename:
            # Save to uploads then check
            filename = secure_filename(image.filename)
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            image.save(file_path)

            # check type with imghdr
            ftype = imghdr.what(file_path)
            if ftype not in ("jpeg", "png", "jpg"):
                os.remove(file_path)
                flash("Only JPG/PNG images are allowed.", "error")
                return redirect("/upload_problem")

            # quality checks
            if is_image_blurry(file_path):
                os.remove(file_path)
                flash("Uploaded image is too blurry. Please upload a clear image.", "error")
                return redirect("/upload_problem")
            if is_low_resolution(file_path):
                os.remove(file_path)
                flash("Image resolution too low. Upload a higher resolution image.", "error")
                return redirect("/upload_problem")
            if is_old_image(file_path):
                os.remove(file_path)
                flash("Looks like an old image. Please upload a recent photo.", "error")
                return redirect("/upload_problem")

        # insert
        cursor.execute("""
            INSERT INTO problems
            (user_id, department, description, priority, image_path, location, status, latitude, longitude, assigned_officer_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (session["user_id"], final_dep, desc, priority, filename, location, "Pending", latitude, longitude, None))
        db.commit()

        flash("Problem submitted.", "success")
        return redirect("/my_problems")

    return render_template("upload_problem.html", departments=departments)

# ----------------- PROFILE -----------------
@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect("/login")
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],))
    user = cur.fetchone()
    return render_template("profile.html", user=user)

@app.route("/profile/update", methods=["POST"])
def update_profile():
    if "user_id" not in session:
        return redirect("/login")
    name = request.form.get("name")
    mobile = request.form.get("mobile")
    address = request.form.get("address")
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE users SET name=%s, mobile=%s, address=%s WHERE id=%s", (name, mobile, address, session["user_id"]))
    db.commit()
    flash("Profile updated successfully!", "success")
    return redirect("/profile")

# ----------------- HEATMAP -----------------
@app.route("/heatmap")
def heatmap():
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute("""
        SELECT latitude, longitude 
        FROM problems 
        WHERE latitude IS NOT NULL 
        AND longitude IS NOT NULL
    """)

    rows = cur.fetchall()

    # SAFE CLEAN HEAT DATA
    heat_data = []
    for r in rows:
        try:
            lat = float(r["latitude"])
            lon = float(r["longitude"])
            if lat != 0 and lon != 0:
                heat_data.append([lat, lon])
        except:
            continue

    return render_template("heatmap.html", heat_data=heat_data)

# ----------------- OFFICER TASKS -----------------
@app.route("/officer_tasks")
def officer_tasks():
    if "role" not in session or session["role"] != "officer":
        flash("Please login as an officer!", "error")
        return redirect("/login")
    officer_id = session["officer_id"]
    db = get_db()
    cur = db.cursor(dictionary=True)
    # Get officer's department
    cur.execute("SELECT department_id FROM officers WHERE id=%s", (officer_id,))
    officer = cur.fetchone()
    if not officer:
        flash("Officer not found.", "error")
        return redirect("/login")
    dept = officer["department_id"]
    cur.execute("SELECT id, description, location, status, image_path FROM problems WHERE department=%s ORDER BY created_at DESC", (dept,))
    tasks = cur.fetchall()
    cur.execute("SELECT COUNT(*) AS c FROM problems WHERE department=%s", (dept,))
    assigned = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM problems WHERE department=%s AND status='Ongoing'", (dept,))
    ongoing = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM problems WHERE department=%s AND status='Completed'", (dept,))
    completed = cur.fetchone()["c"]
    return render_template("officer_tasks.html", tasks=tasks, assigned=assigned, ongoing=ongoing, completed=completed)

@app.route("/update_task/<int:task_id>", methods=["GET", "POST"])
def update_task(task_id):
    if "role" not in session or session["role"] != "officer":
        return redirect("/login")
    db = get_db()
    cur = db.cursor(dictionary=True)
    if request.method == "POST":
        new_status = request.form.get("status")
        proof_path = None
        if "proof" in request.files:
            proof = request.files["proof"]
            if proof and proof.filename != "":
                fname = secure_filename(proof.filename)
                proof_path = os.path.join(app.config["PROOF_FOLDER"], fname)
                proof.save(proof_path)
                # optional checks for proof image can be added
        if proof_path:
            cur2 = db.cursor()
            cur2.execute("UPDATE problems SET status=%s, proof_image=%s, assigned_officer_id=%s WHERE id=%s", (new_status, proof_path, session["officer_id"], task_id))
            db.commit()
        else:
            cur2 = db.cursor()
            cur2.execute("UPDATE problems SET status=%s, assigned_officer_id=%s WHERE id=%s", (new_status, session["officer_id"], task_id))
            db.commit()
        flash("Task updated successfully!", "success")
        return redirect("/officer_tasks")
    cur.execute("SELECT * FROM problems WHERE id=%s", (task_id,))
    task = cur.fetchone()
    return render_template("update_task.html", task=task)

@app.route("/resolve_history")
def resolve_history():
    if "role" not in session or session["role"] != "officer":
        return redirect("/login")
    officer_id = session["officer_id"]
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT id, description, location, proof_image, status, created_at FROM problems WHERE assigned_officer_id=%s AND status='Completed' ORDER BY created_at DESC", (officer_id,))
    history = cur.fetchall()
    return render_template("resolve_history.html", history=history)

@app.route("/officer_profile")
def officer_profile():
    if "role" not in session or session["role"] != "officer":
        return redirect("/login")
    officer_id = session["officer_id"]
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT o.*, d.department_name AS department FROM officers o LEFT JOIN departments d ON o.department_id=d.department_name WHERE o.id=%s", (officer_id,))
    officer = cur.fetchone()
    return render_template("officer_profile.html", officer=officer)

@app.route("/officer_profile_edit", methods=["GET", "POST"])
def officer_profile_edit():
    if "role" not in session or session["role"] != "officer":
        return redirect("/login")
    officer_id = session["officer_id"]
    db = get_db()
    cur = db.cursor(dictionary=True)
    if request.method == "GET":
        cur.execute("SELECT * FROM officers WHERE id=%s", (officer_id,))
        officer = cur.fetchone()
        cur.execute("SELECT id, department_name FROM departments")
        departments = cur.fetchall()
        return render_template("officer_profile_edit.html", officer=officer, departments=departments)
    # POST
    name = request.form.get("name")
    mobile = request.form.get("mobile")
    address = request.form.get("address")
    department = request.form.get("department")
    cur2 = db.cursor()
    cur2.execute("UPDATE officers SET name=%s, mobile=%s, address=%s, department_id=%s WHERE id=%s", (name, mobile, address, department, officer_id))
    db.commit()
    flash("Profile updated successfully!", "success")
    return redirect("/officer_profile")

# ----------------- ADMIN: USERS/OFFICERS/DEPARTMENTS/PROBLEMS -----------------
@app.route("/admin_users")
def admin_users():
    if "role" not in session or session["role"] != "admin":
        return redirect("/login")
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM users ORDER BY id DESC")
    users = cur.fetchall()
    return render_template("admin_users.html", users=users)

@app.route("/delete_user/<int:user_id>")
def delete_user(user_id):
    if "role" not in session or session["role"] != "admin":
        return redirect("/login")
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM problems WHERE user_id=%s", (user_id,))
    cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
    db.commit()
    flash("User deleted.", "info")
    return redirect("/admin_users")

@app.route("/edit_user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    if "role" not in session or session["role"] != "admin":
        return redirect("/login")
    db = get_db()
    cur = db.cursor(dictionary=True)
    if request.method == "POST":
        name = request.form.get("name")
        username = request.form.get("username")
        mobile = request.form.get("mobile")
        address = request.form.get("address")
        cur2 = db.cursor()
        cur2.execute("UPDATE users SET name=%s, username=%s, mobile=%s, address=%s WHERE id=%s", (name, username, mobile, address, user_id))
        db.commit()
        flash("User updated.", "success")
        return redirect("/admin_users")
    cur.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()
    return render_template("edit_user.html", user=user)

@app.route("/admin_officers")
def admin_officers():
    if "role" not in session or session["role"] != "admin":
        return redirect("/login")
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT o.*, d.department_name AS department_name FROM officers o LEFT JOIN departments d ON o.department_id=d.department_name ORDER BY o.id DESC")
    officers = cur.fetchall()
    return render_template("admin_officers.html", officers=officers)

@app.route("/delete_officer/<int:officer_id>")
def delete_officer(officer_id):
    if "role" not in session or session["role"] != "admin":
        return redirect("/login")
    db = get_db()
    cur = db.cursor()
    # Set assigned_officer_id to NULL for problems assigned to this officer
    cur.execute("UPDATE problems SET assigned_officer_id=NULL WHERE assigned_officer_id=%s", (officer_id,))
    cur.execute("DELETE FROM officers WHERE id=%s", (officer_id,))
    db.commit()
    flash("Officer deleted.", "info")
    return redirect("/admin_officers")

@app.route("/admin_departments")
def admin_departments():
    if "role" not in session or session["role"] != "admin":
        return redirect("/login")
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM departments ORDER BY id DESC")
    departments = cur.fetchall()
    return render_template("admin_departments.html", departments=departments)

@app.route("/add_department", methods=["POST"])
def add_department():
    if "role" not in session or session["role"] != "admin":
        return redirect("/login")
    name = request.form.get("dept_name")
    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT INTO departments (department_name) VALUES (%s)", (name,))
    db.commit()
    flash("Department added.", "success")
    return redirect("/admin_departments")

@app.route("/delete_department/<int:dept_id>")
def delete_department(dept_id):
    if "role" not in session or session["role"] != "admin":
        return redirect("/login")
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM departments WHERE id=%s", (dept_id,))
    db.commit()
    flash("Department deleted.", "info")
    return redirect("/admin_departments")

@app.route("/edit_department/<int:dept_id>", methods=["GET", "POST"])
def edit_department(dept_id):
    if "role" not in session or session["role"] != "admin":
        return redirect("/login")
    db = get_db()
    cur = db.cursor(dictionary=True)
    if request.method == "POST":
        name = request.form.get("dept_name")
        cur2 = db.cursor()
        cur2.execute("UPDATE departments SET department_name=%s WHERE id=%s", (name, dept_id))
        db.commit()
        flash("Department updated.", "success")
        return redirect("/admin_departments")
    cur.execute("SELECT * FROM departments WHERE id=%s", (dept_id,))
    dept = cur.fetchone()
    return render_template("edit_department.html", dept=dept)

@app.route("/admin_problems")
def admin_problems():
    if "role" not in session or session["role"] != "admin":
        return redirect("/login")
    status = request.args.get("status", "")
    department = request.args.get("department", "")
    search = request.args.get("search", "")
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM departments")
    departments = cur.fetchall()
    query = "SELECT p.id, p.department, p.description, p.status, u.username FROM problems p LEFT JOIN users u ON p.user_id=u.id WHERE 1=1"
    params = []
    if status:
        query += " AND p.status=%s"
        params.append(status)
    if department:
        query += " AND p.department=%s"
        params.append(department)
    if search:
        query += " AND p.description LIKE %s"
        params.append("%" + search + "%")
    query += " ORDER BY p.id DESC"
    cur.execute(query, params)
    problems = cur.fetchall()
    return render_template("admin_problems.html", problems=problems, departments=departments)

@app.route("/delete_problem/<int:pid>")
def delete_problem(pid):
    if "role" not in session or session["role"] != "admin":
        return redirect("/login")
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM problems WHERE id=%s", (pid,))
    db.commit()
    flash("Problem deleted.", "info")
    return redirect("/admin_problems")

@app.route("/view_problem/<int:problem_id>")
def view_problem(problem_id):

    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    cur = db.cursor(dictionary=True)

    # Load problem
    cur.execute("""
        SELECT *
        FROM problems
        WHERE id = %s AND user_id = %s
    """, (problem_id, session["user_id"]))
    problem = cur.fetchone()

    if not problem:
        flash("Problem not found!")
        return redirect("/my_problems")

    # Load review complaint (if any)
    cur.execute("""
        SELECT *
        FROM review_complaints
        WHERE problem_id=%s AND user_id=%s
        ORDER BY id DESC LIMIT 1
    """, (problem_id, session["user_id"]))
    review = cur.fetchone()

    return render_template("view_problem.html", problem=problem, review=review)

@app.route("/submit_review/<int:pid>", methods=["POST"])
def submit_review(pid):
    if "user_id" not in session:
        return redirect("/login")

    message = request.form["message"]

    db = get_db()
    cur = db.cursor()

    sql = """
        INSERT INTO review_complaints (problem_id, user_id, message)
        VALUES (%s, %s, %s)
    """

    cur.execute(sql, (pid, session["user_id"], message))
    db.commit()

    flash("Your complaint has been sent to the Admin.", "error")
    return redirect("/my_problems")
@app.route("/admin_reviews")
def admin_reviews():

    if "role" not in session or session["role"] != "admin":
        return redirect("/login")

    db = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute("""
        SELECT r.*, u.username 
        FROM review_complaints r
        LEFT JOIN users u ON r.user_id = u.id
        ORDER BY r.created_at DESC
    """)

    reviews = cur.fetchall()

    return render_template("admin_reviews.html", reviews=reviews)
@app.route("/admin_review/<int:rid>", methods=["GET", "POST"])
def admin_review(rid):

    if "role" not in session or session["role"] != "admin":
        return redirect("/login")

    db = get_db()
    cur = db.cursor(dictionary=True)

    if request.method == "POST":
        reply = request.form["reply"]
        status = request.form["status"]

        cur.execute("""
            UPDATE review_complaints
            SET reply_message=%s, status=%s, reply_at=NOW()
            WHERE id=%s
        """, (reply, status, rid))

        db.commit()
        flash("Reply sent successfully.", "success")
        return redirect("/admin_reviews")

    # GET → Show the review
    cur.execute("""
        SELECT r.*, u.username, u.id AS uid, p.description AS problem_desc 
        FROM review_complaints r
        LEFT JOIN users u ON r.user_id = u.id
        LEFT JOIN problems p ON r.problem_id = p.id
        WHERE r.id=%s
    """, (rid,))

    review = cur.fetchone()

    return render_template("admin_review_view.html", review=review)
@app.route("/view_problem_admin/<int:problem_id>")
def view_problem_admin(problem_id):



    db = get_db()
    cur = db.cursor(dictionary=True)

    # Load problem
    cur.execute("""
        SELECT *
        FROM problems
        WHERE id = %s  
    """, (problem_id,  ))
    problem = cur.fetchone()

    if not problem:
        flash("Problem not found!")
        return redirect("/my_problems")

    # Load review complaint (if any)
    cur.execute("""
        SELECT *
        FROM review_complaints
        WHERE problem_id=%s  
        ORDER BY id DESC LIMIT 1
    """, (problem_id, ))
    review = cur.fetchone()

    return render_template("admin_view_problem.html", problem=problem, review=review)
# -------------------
# Run app
# -------------------
if __name__ == "__main__":
    app.run(debug=True)
