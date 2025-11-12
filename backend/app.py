import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Iterable, Set
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from functools import wraps
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_from_directory,
    g,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


try:
    IST = ZoneInfo("Asia/Kolkata")
except ZoneInfoNotFoundError:
    IST = timezone(timedelta(hours=5, minutes=30))


def create_app() -> Flask:
    """Application factory that sets up Flask, database, and routes."""
    app = Flask(__name__)

    # Core configuration values for security, file uploads, and local database location.
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "uploads")
    app.config["DATABASE"] = os.path.join(app.root_path, "dsgnr.db")
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # Limit uploads to 10 MB.
    app.config["ALLOWED_EXTENSIONS"] = {"png", "jpg", "jpeg", "gif", "webp"}

    ensure_upload_folder(app)

    with app.app_context():
        with sqlite3.connect(app.config["DATABASE"]) as db:
            create_tables(db)
            ensure_admin_exists(db)

    @app.before_request
    def attach_db_connection() -> None:
        """Creates a database connection for the request lifecycle."""
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row  # Enable dict-style column access.

    @app.teardown_appcontext
    def close_db_connection(exception: Exception | None) -> None:
        """Closes the database connection at the end of the request."""
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def login_required(view):
        """Decorator that restricts routes to authenticated users."""

        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped_view

    def admin_required(view):
        """Decorator that restricts routes to administrator-level users."""

        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if not session.get("is_admin"):
                flash("You do not have permission to perform this action.", "danger")
                return redirect(url_for("feed"))
            return view(*args, **kwargs)

        return wrapped_view

    @app.route("/")
    @app.route("/feed")
    @login_required
    def feed():
        """Displays the Instagram-style grid of all posts ordered by recency."""
        raw_posts = fetch_posts(g.db, sort="recent")
        liked_ids = get_user_liked_post_ids(g.db, session["user_id"])
        posts = format_posts_for_view(raw_posts, liked_ids)
        return render_template("feed.html", posts=posts)

    @app.route("/leaderboard")
    @login_required
    def leaderboard():
        """Lists posts ranked by like counts."""
        raw_posts = fetch_posts(g.db, sort="likes")
        liked_ids = get_user_liked_post_ids(g.db, session["user_id"])
        posts = format_posts_for_view(raw_posts, liked_ids)
        return render_template("leaderboard.html", posts=posts)

    @app.route("/about")
    def about():
        """Shares club details and platform guidelines."""
        return render_template("about.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        """Handles account creation with hashed passwords and validation."""
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if not username or not password:
                flash("Username and password are required.", "danger")
                return redirect(url_for("register"))

            if user_exists(g.db, username):
                flash("That username is already taken.", "warning")
                return redirect(url_for("register"))

            password_hash = generate_password_hash(password)
            create_user(g.db, username, password_hash)
            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for("login"))

        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        """Authenticates existing users and stores session data."""
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            user = fetch_user_by_username(g.db, username)
            if user is None or not check_password_hash(user["password_hash"], password):
                flash("Invalid username or password.", "danger")
                return redirect(url_for("login"))

            # Refresh the session to mitigate fixation attacks before storing identifiers.
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = bool(user["is_admin"])
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for("feed"))

        return render_template("login.html", hide_nav=True)

    @app.route("/logout")
    def logout():
        """Clears session data to log the user out."""
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("login"))

    @app.route("/upload", methods=["GET", "POST"])
    @login_required
    def upload():
        """Allows authenticated users to upload new artwork posts."""
        if request.method == "POST":
            caption = request.form.get("caption", "").strip()
            image = request.files.get("image")

            if not image or image.filename == "":
                flash("Please choose an image to upload.", "warning")
                return redirect(url_for("upload"))

            if not allowed_file(image.filename, app):
                flash("Unsupported file type. Please upload an image.", "danger")
                return redirect(url_for("upload"))

            # Prefix the original filename with a high-resolution timestamp to avoid collisions.
            filename = secure_filename(image.filename)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
            stored_filename = f"{timestamp}_{filename}"
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], stored_filename)
            image.save(image_path)

            # Persist the post metadata referencing the stored file.
            create_post(
                g.db,
                user_id=session["user_id"],
                image_filename=stored_filename,
                caption=caption,
            )
            flash("Your art has been shared!", "success")
            return redirect(url_for("feed"))

        return render_template("upload.html")

    @app.route("/delete/<int:post_id>", methods=["POST"])
    @login_required
    @admin_required
    def delete_post(post_id: int):
        """Allows administrators to remove a post and its associated image file."""
        post = fetch_post_by_id(g.db, post_id)
        if post is None:
            flash("Post not found.", "warning")
            return redirect(url_for("feed"))

        # Deleting the post removes both the database record and image asset.
        remove_post(g.db, post)
        flash("Post deleted.", "info")
        return redirect(url_for("feed"))

    @app.route("/like/<int:post_id>", methods=["POST"])
    @login_required
    def toggle_like(post_id: int):
        """Toggles the like status for the current user on a post."""
        post = fetch_post_by_id(g.db, post_id)
        if post is None:
            flash("Post not found.", "warning")
            return redirect(url_for("feed"))

        user_id = session["user_id"]
        if user_has_liked(g.db, user_id, post_id):
            remove_like(g.db, user_id, post_id)
        else:
            add_like(g.db, user_id, post_id)

        return redirect(request.referrer or url_for("feed"))

    @app.route("/uploads/<path:filename>")
    @login_required
    def uploaded_file(filename: str):
        """Serves uploaded files securely to authenticated users."""
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    return app


def ensure_upload_folder(app: Flask) -> None:
    """Creates the upload directory if it does not already exist."""
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def create_tables(db: sqlite3.Connection) -> None:
    """Creates the required database tables when they are missing."""
    cursor = db.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            image_path TEXT NOT NULL,
            caption TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (user_id, post_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (post_id) REFERENCES posts(id)
        )
        """
    )
    db.commit()


def ensure_admin_exists(db: sqlite3.Connection) -> None:
    """Creates a default admin account when none is present."""
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
            (
                "admin",
                generate_password_hash("adminpass"),
            ),
        )
        db.commit()


def allowed_file(filename: str, app: Flask) -> bool:
    """Validates file extensions against the allowed list."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]


def user_exists(db: sqlite3.Connection, username: str) -> bool:
    """Checks whether a username is already registered."""
    cursor = db.cursor()
    cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
    return cursor.fetchone() is not None


def create_user(db: sqlite3.Connection, username: str, password_hash: str) -> None:
    """Persists a new user record to the database."""
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash),
    )
    db.commit()


def fetch_user_by_username(db: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    """Retrieves a user row matching the provided username."""
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    return cursor.fetchone()


def create_post(db: sqlite3.Connection, user_id: int, image_filename: str, caption: str) -> None:
    """Adds a new art post to the feed."""
    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO posts (user_id, image_path, caption, created_at)
        VALUES (?, ?, ?, ?)
        """,
    (user_id, image_filename, caption, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()


def fetch_posts(db: sqlite3.Connection, sort: str = "recent") -> list[sqlite3.Row]:
    """Fetches all posts with author information and like counts."""
    cursor = db.cursor()
    order_map = {
        "recent": "posts.created_at DESC",
        "likes": "like_count DESC, posts.created_at DESC",
    }
    order_clause = order_map.get(sort, order_map["recent"])
    cursor.execute(
        """
        SELECT
            posts.id,
            posts.image_path,
            posts.caption,
            posts.created_at,
            users.username,
            COALESCE(COUNT(likes.id), 0) AS like_count
        FROM posts
        JOIN users ON posts.user_id = users.id
        LEFT JOIN likes ON likes.post_id = posts.id
        GROUP BY posts.id
        ORDER BY %s
        """
        % order_clause
    )
    return cursor.fetchall()


def format_posts_for_view(posts: list[sqlite3.Row], liked_ids: Iterable[int] | None = None) -> list[dict]:
    """Transforms raw database rows into template-friendly dictionaries."""
    formatted: list[dict] = []
    liked_set: Set[int] = set(liked_ids or [])
    for row in posts:
        created_at = datetime.fromisoformat(row["created_at"]).astimezone(IST)
        formatted.append(
            {
                "id": row["id"],
                "image_path": row["image_path"],
                "caption": row["caption"],
                "username": row["username"],
                "created_at": created_at,
                "display_time": created_at.strftime("%b %d, %Y · %I:%M %p"),
                "like_count": row["like_count"],
                "liked": row["id"] in liked_set,
            }
        )
    return formatted


def fetch_post_by_id(db: sqlite3.Connection, post_id: int) -> sqlite3.Row | None:
    """Finds a single post record and author details."""
    cursor = db.cursor()
    cursor.execute(
        """
        SELECT
            posts.*, 
            users.username,
            COALESCE(COUNT(likes.id), 0) AS like_count
        FROM posts
        JOIN users ON posts.user_id = users.id
        LEFT JOIN likes ON likes.post_id = posts.id
        WHERE posts.id = ?
        GROUP BY posts.id
        """,
        (post_id,),
    )
    return cursor.fetchone()


def remove_post(db: sqlite3.Connection, post: sqlite3.Row) -> None:
    """Deletes the post record and removes its stored image."""
    cursor = db.cursor()
    cursor.execute("DELETE FROM likes WHERE post_id = ?", (post["id"],))
    cursor.execute("DELETE FROM posts WHERE id = ?", (post["id"],))
    db.commit()

    uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
    image_path = os.path.join(uploads_dir, post["image_path"])
    if os.path.exists(image_path):
        os.remove(image_path)


def get_user_liked_post_ids(db: sqlite3.Connection, user_id: int) -> Set[int]:
    """Returns a set of post IDs liked by the specified user."""
    cursor = db.cursor()
    cursor.execute("SELECT post_id FROM likes WHERE user_id = ?", (user_id,))
    return {row[0] for row in cursor.fetchall()}


def user_has_liked(db: sqlite3.Connection, user_id: int, post_id: int) -> bool:
    """Checks whether the user already liked the post."""
    cursor = db.cursor()
    cursor.execute(
        "SELECT 1 FROM likes WHERE user_id = ? AND post_id = ?",
        (user_id, post_id),
    )
    return cursor.fetchone() is not None


def add_like(db: sqlite3.Connection, user_id: int, post_id: int) -> None:
    """Adds a like entry for the given user and post."""
    cursor = db.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO likes (user_id, post_id, created_at) VALUES (?, ?, ?)",
        (user_id, post_id, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()


def remove_like(db: sqlite3.Connection, user_id: int, post_id: int) -> None:
    """Removes a like entry for the given user and post."""
    cursor = db.cursor()
    cursor.execute(
        "DELETE FROM likes WHERE user_id = ? AND post_id = ?",
        (user_id, post_id),
    )
    db.commit()


if __name__ == "__main__":
    # Running in development mode with Flask's built-in server.
    application = create_app()
    application.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
