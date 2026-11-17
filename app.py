import os
import sqlite3
from functools import wraps
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "enta.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
ALLOWED_EXTENSIONS = {"pdf"}

app = Flask(__name__)
app.secret_key = os.environ.get("ENTA_SECRET_KEY", "change-this-secret-key-before-deployment")
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            subject TEXT NOT NULL DEFAULT 'Autres',
            program TEXT DEFAULT '',
            semester TEXT DEFAULT '',
            description TEXT DEFAULT '',
            filename TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            program TEXT DEFAULT '',
            semester TEXT DEFAULT '',
            filename TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)
        # Migrate older databases created before the subject field existed.
        resource_columns = {row[1] for row in con.execute("PRAGMA table_info(resources)").fetchall()}
        if "subject" not in resource_columns:
            con.execute("ALTER TABLE resources ADD COLUMN subject TEXT NOT NULL DEFAULT 'Autres'")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('wifi_info',?)",
                    ("Les informations Wi-Fi seront publiées par l'administration.",))
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('welcome_text',?)",
                    ("Toutes les ressources étudiantes de l'ENTA Dakhla réunies au même endroit.",))
        # Publish the timetable image supplied for the initial APCI S1 example.
        existing_schedule = con.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]
        if not existing_schedule:
            con.execute("""INSERT INTO schedules(title,program,semester,filename)
                           VALUES(?,?,?,?)""",
                        ("Emploi du temps APCI - 2026/2027", "APCI", "Semestre 1",
                         "emploi-apci-s1-2026-2027.jpg"))

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_upload(file):
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        raise ValueError("Format non autorisé. Ajoutez uniquement des fichiers PDF.")
    original = secure_filename(file.filename)
    # Avoid collisions while retaining a readable filename.
    import uuid
    name = f"{uuid.uuid4().hex[:10]}_{original}"
    file.save(UPLOAD_DIR / name)
    return name

@app.context_processor
def inject_globals():
    return {"admin_logged_in": "admin_id" in session}

SUBJECTS = [
    "Introduction aux sciences de l’ingénieur et aux technologies avancées",
    "Mathématiques pour l’ingénieur",
    "Physique pour les technologies avancées",
    "Algorithmique et programmation Python",
    "Outils numériques, programmation collaborative et culture digitale",
    "Communication scientifique (Français) et culture académique",
    "Développement personnel, méthodologie universitaire et soft skills",
]
SUBJECT_SLUGS = {
    "introduction-aux-sciences-de-lingenieur-et-aux-technologies-avancees": SUBJECTS[0],
    "mathematiques-pour-lingenieur": SUBJECTS[1],
    "physique-pour-les-technologies-avancees": SUBJECTS[2],
    "algorithmique-et-programmation-python": SUBJECTS[3],
    "outils-numeriques-programmation-collaborative-et-culture-digitale": SUBJECTS[4],
    "communication-scientifique-francais-et-culture-academique": SUBJECTS[5],
    "developpement-personnel-methodologie-universitaire-et-soft-skills": SUBJECTS[6],
}
CATEGORIES = ["Cours", "TD", "Corrigés"]

@app.route("/")
def index():
    with db() as con:
        resources = con.execute("SELECT * FROM resources ORDER BY created_at DESC").fetchall()
        schedules = con.execute("SELECT * FROM schedules ORDER BY created_at DESC").fetchall()
        announcements = con.execute("SELECT * FROM announcements ORDER BY created_at DESC LIMIT 5").fetchall()
        settings = {r["key"]: r["value"] for r in con.execute("SELECT * FROM settings").fetchall()}
    subject_urls = {value: key for key, value in SUBJECT_SLUGS.items()}
    return render_template("index.html", resources=resources, subjects=SUBJECTS,
                           subject_urls=subject_urls, schedules=schedules,
                           announcements=announcements, settings=settings)

@app.route("/matiere/<slug>")
def subject_page(slug):
    subject = SUBJECT_SLUGS.get(slug.lower())
    if not subject:
        abort(404)
    with db() as con:
        resources = con.execute(
            "SELECT * FROM resources WHERE lower(subject)=lower(?) ORDER BY created_at DESC", (subject,)
        ).fetchall()
    # Compatibility with resources uploaded using the old singular category label.
    resources = [dict(r) for r in resources]
    for item in resources:
        if item["category"] == "Correction":
            item["category"] = "Corrigés"
    return render_template("subject.html", subject=subject, resources=resources, categories=CATEGORIES)

@app.route("/setup", methods=["GET", "POST"])
def setup():
    with db() as con:
        count = con.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
    if count:
        flash("Le compte administrateur existe déjà. Connectez-vous.", "info")
        return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if len(username) < 3 or len(password) < 10:
            flash("Choisissez un identifiant (3 caractères min.) et un mot de passe (10 caractères min.).", "error")
        elif password != confirm:
            flash("Les mots de passe ne correspondent pas.", "error")
        else:
            try:
                with db() as con:
                    con.execute("INSERT INTO admins(username,password_hash) VALUES(?,?)",
                                (username, generate_password_hash(password)))
                flash("Compte administrateur créé. Vous pouvez vous connecter.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("Cet identifiant est déjà utilisé.", "error")
    return render_template("setup.html")

@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with db() as con:
            admin = con.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            return redirect(url_for("dashboard"))
        flash("Identifiant ou mot de passe incorrect.", "error")
    return render_template("login.html")

@app.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/admin")
@admin_required
def dashboard():
    with db() as con:
        resources = con.execute("SELECT * FROM resources ORDER BY created_at DESC").fetchall()
        schedules = con.execute("SELECT * FROM schedules ORDER BY created_at DESC").fetchall()
        announcements = con.execute("SELECT * FROM announcements ORDER BY created_at DESC").fetchall()
        settings = {r["key"]: r["value"] for r in con.execute("SELECT * FROM settings").fetchall()}
    return render_template("admin.html", resources=resources, schedules=schedules,
                           announcements=announcements, settings=settings, subjects=SUBJECTS)

@app.route("/admin/resource", methods=["POST"])
@admin_required
def add_resource():
    subject = request.form.get("subject", "").strip()
    category = request.form.get("category", "").strip()
    files = request.files.getlist("files")
    files = [f for f in files if f and f.filename]
    if subject not in SUBJECTS or category not in CATEGORIES or not files:
        flash("Choisissez une matière, une rubrique et au moins un fichier PDF.", "error")
        return redirect(url_for("dashboard"))
    saved = []
    try:
        for file in files:
            if not allowed_file(file.filename):
                raise ValueError(f"{file.filename}: seuls les fichiers PDF sont acceptés.")
            filename = save_upload(file)
            saved.append(filename)
        with db() as con:
            for filename, file in zip(saved, files):
                title = Path(file.filename).stem.replace("_", " ").replace("-", " ").strip() or "Document PDF"
                con.execute("""INSERT INTO resources(title,category,subject,program,semester,description,filename)
                               VALUES(?,?,?,?,?,?,?)""",
                            (title, category, subject, "", "", "", filename))
        flash(f"{len(saved)} fichier(s) PDF publié(s) avec succès.", "success")
    except (ValueError, OSError) as e:
        for filename in saved:
            (UPLOAD_DIR / filename).unlink(missing_ok=True)
        flash(str(e), "error")
    return redirect(url_for("dashboard"))

@app.route("/admin/schedule", methods=["POST"])
@admin_required
def add_schedule():
    title = request.form.get("title", "").strip()
    file = request.files.get("file")
    if not title or not file or not file.filename:
        flash("Ajoutez un titre et un fichier du planning.", "error")
        return redirect(url_for("dashboard"))
    try:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in {"pdf", "png", "jpg", "jpeg", "webp"}:
            raise ValueError("Le planning doit être un PDF ou une image.")
        import uuid
        filename = f"{uuid.uuid4().hex[:10]}_{secure_filename(file.filename)}"
        file.save(UPLOAD_DIR / filename)
        with db() as con:
            con.execute("INSERT INTO schedules(title,program,semester,filename) VALUES(?,?,?,?)",
                        (title, request.form.get("program","").strip(),
                         request.form.get("semester","").strip(), filename))
        flash("Emploi du temps ajouté.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("dashboard"))

@app.route("/admin/announcement", methods=["POST"])
@admin_required
def add_announcement():
    title = request.form.get("title", "").strip()
    body = request.form.get("body", "").strip()
    if title and body:
        with db() as con:
            con.execute("INSERT INTO announcements(title,body) VALUES(?,?)", (title, body))
        flash("Annonce publiée.", "success")
    else:
        flash("Ajoutez un titre et un contenu.", "error")
    return redirect(url_for("dashboard"))

@app.route("/admin/settings", methods=["POST"])
@admin_required
def update_settings():
    with db() as con:
        con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('wifi_info',?)",
                    (request.form.get("wifi_info","").strip(),))
        con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('welcome_text',?)",
                    (request.form.get("welcome_text","").strip(),))
    flash("Informations mises à jour.", "success")
    return redirect(url_for("dashboard"))

@app.route("/admin/delete/<kind>/<int:item_id>", methods=["POST"])
@admin_required
def delete_item(kind, item_id):
    table = {"resource": "resources", "schedule": "schedules", "announcement": "announcements"}.get(kind)
    if not table:
        abort(404)
    with db() as con:
        row = con.execute(f"SELECT * FROM {table} WHERE id=?", (item_id,)).fetchone()
        if row:
            if kind in {"resource", "schedule"}:
                try:
                    (UPLOAD_DIR / row["filename"]).unlink(missing_ok=True)
                except OSError:
                    pass
            con.execute(f"DELETE FROM {table} WHERE id=?", (item_id,))
    flash("Élément supprimé.", "success")
    return redirect(url_for("dashboard"))

@app.errorhandler(413)
def too_large(_):
    flash("Fichier trop volumineux (maximum 25 Mo).", "error")
    return redirect(request.referrer or url_for("dashboard"))

init_db()

if __name__ == "__main__":
    app.run(debug=True)
