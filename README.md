# DSGNR

Private art-sharing platform inspired by Instagram for the campus art club. Authenticated members can upload their artwork, browse a modern three-column feed, and admins retain control over moderation. The project is split into a Flask backend (Render deployment ready) and a static marketing frontend (Vercel deployment ready).

## Tech Stack
- **Frontend:** HTML, Bootstrap 5, custom CSS/JS (deploy on Vercel)
- **Backend:** Python Flask, SQLite, Bootstrap-driven templates (deploy on Render)
- **Storage:** Local `uploads/` directory for artwork images

## Features
- Secure registration and login using `werkzeug.security` password hashing
- Authenticated-only upload form for images (JPG/PNG/GIF/WEBP) with captions
- Responsive Instagram-style feed with hover effects and pastel theming
- Flash messaging for all major user actions
- Admin-only delete route for moderation
- Default admin account created on first run (`admin` / `adminpass`) — update immediately after deployment

## Repository Structure
```
backend/
  app.py             # Flask application (WSGI entry point is `application`)
  Procfile           # Render process definition (gunicorn)
  requirements.txt   # Backend dependencies
  static/style.css   # Additional Bootstrap overrides
  templates/         # Jinja templates (base, feed, auth, upload)
  uploads/           # Stored images (keep private on the server)
frontend/
  index.html         # Marketing/landing page for Vercel
  style.css          # Pastel themed overrides
  script.js          # Minor interactivity helpers
README.md            # Project setup & deployment guide
```

## Prerequisites
- Python 3.10+
- Node.js (optional, only if using Vercel CLI)
- Git

## Backend: Local Development
1. Navigate into the backend folder:
   ```powershell
   cd backend
   ```
2. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Set a secure secret key (replace value before deploying):
   ```powershell
   $env:SECRET_KEY = "change-this-secret"
   ```
5. Start Flask (debug server for local testing):
   ```powershell
   python app.py
   ```
6. Visit `http://localhost:5000` and log in with the default admin (`admin` / `adminpass`). Use the UI to create member accounts.

### Notes
- Uploaded images are saved to `backend/uploads/`. Ensure this folder exists wherever you deploy.
- SQLite database file `dsgnr.db` is created the first time the app runs.
- To reset the database locally, delete `dsgnr.db` and the contents of `uploads/` (not the folder itself).

## Frontend: Local Preview
1. Open another terminal and move into the frontend folder:
   ```powershell
   cd frontend
   ```
2. Serve the static files with any local server (for example, using Node.js `npx serve` or Python `python -m http.server`). The HTML is static, so opening `index.html` directly in the browser also works.
3. Update the call-to-action links in `index.html` to point to your hosted backend login/register URLs before deploying.

## Deploying the Backend to Render (Free Tier)
1. Create a new **Web Service** on Render and connect the repository.
2. Use the following settings:
   - **Root Directory:** `backend`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:application`
   - **Instance Type:** Free (first tier)
3. Add environment variables:
   - `SECRET_KEY` — a strong random string
4. Ensure the `uploads/` directory persists between deploys:
   - Render automatically persists the project directory. For best practices, consider mounting a persistent disk if long-term retention is required.
5. After deployment, test the endpoints:
   - `https://<your-service>.onrender.com/login`
   - `https://<your-service>.onrender.com/feed`
6. Change the default admin password immediately via the UI (`admin` uploads a new password-protected account and demotes/deletes the original if desired).

## Deploying the Frontend to Vercel (Free Tier)
1. Install the Vercel CLI (optional but convenient):
   ```powershell
   npm install -g vercel
   ```
2. From the `frontend` directory run:
   ```powershell
   vercel deploy
   ```
   - Provide a project name (e.g., `dsgnr-landing`).
   - When asked for the build command and output directory, accept the defaults (static site).
3. Alternatively, connect the Git repository on Vercel and set the project root to `frontend`.
4. After deployment, update any links/buttons so they target the Render backend URLs.

## Post-Deployment Checklist
- ✅ Update `SECRET_KEY` and admin credentials.
- ✅ Confirm uploads succeed and images display in the feed.
- ✅ Test login/logout flow on both desktop and mobile.
- ✅ Point the Vercel landing page buttons to the Render backend routes.

## Next Steps / Enhancements
- Add image resizing to reduce bandwidth usage.
- Introduce comments or reactions under posts.
- Connect to a persistent object storage service (e.g., AWS S3) before going beyond hobby usage.
- Implement email-based password resets for members.
