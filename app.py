from flask import Flask, redirect, request, session, url_for
import os
import requests
import json
from io import StringIO
from google_auth_oauthlib.flow import Flow
from convertdate import hebrew
from datetime import datetime

app = Flask(__name__)
app.secret_key = "super-dev-secret-key-for-testing-only"
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # For dev use only

app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile"
]

def create_flow():
    client_secret_content = os.environ.get("GOOGLE_CLIENT_SECRET_JSON")
    if not client_secret_content:
        raise Exception("Missing GOOGLE_CLIENT_SECRET_JSON in environment")

    client_config = json.load(StringIO(client_secret_content))
    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri="https://chailights.onrender.com/oauth/callback"
    )

@app.route("/")
def index():
    flow = create_flow()
    state = os.urandom(16).hex()
    session['oauth_state'] = state
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state
    )
    return f"""
        <h2>📸 ChaiLights – Hebrew Date Memories</h2>
        <p>See your old Google Photos taken on this Hebrew date.</p>
        <a href="{auth_url}"><button>🔗 Sign in with Google</button></a>
    """

@app.route("/oauth/callback")
def oauth_callback():
    if session.get('oauth_state') != request.args.get("state"):
        return "<h2>Invalid state</h2><p>Please try again from the homepage.</p>"

    flow = create_flow()
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials

    session["credentials"] = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }
    return redirect(url_for("fetch_photos"))

@app.route("/photos")
def fetch_photos():
    if "credentials" not in session:
        return redirect(url_for("index"))

    creds = session["credentials"]
    headers = {"Authorization": f"Bearer {creds['token']}"}

    user_info = requests.get("https://www.googleapis.com/oauth2/v3/userinfo", headers=headers).json()
    user_name = user_info.get("name", "User")

    query_day = request.args.get("day", type=int)
    query_month = request.args.get("month", type=int)

    if query_day and query_month:
        target_day = query_day
        target_month = query_month
        date_label = f"{target_day} {hebrew.MONTHS_HEB[target_month]}"
    else:
        today = datetime.now()
        h_year, target_month, target_day = hebrew.from_gregorian(today.year, today.month, today.day)
        date_label = f"{target_day} {hebrew.MONTHS_HEB[target_month]} (Today)"

    response = requests.get("https://photoslibrary.googleapis.com/v1/mediaItems?pageSize=100", headers=headers)
    if response.status_code != 200:
        return "<h2>Error fetching photos</h2><p>Try re-authenticating.</p>"

    photos = response.json().get("mediaItems", [])
    matching_photos = []

    for photo in photos:
        date = photo.get("mediaMetadata", {}).get("creationTime", "")[:10]
        if not date:
            continue
        try:
            year, month, day = map(int, date.split("-"))
            photo_hebrew = hebrew.from_gregorian(year, month, day)
            if photo_hebrew[1] == target_month and photo_hebrew[2] == target_day:
                matching_photos.append({
                    "url": photo["baseUrl"] + "=w400-h400",
                    "date": date,
                    "hebrew_date": f"{photo_hebrew[2]} {hebrew.MONTHS_HEB[photo_hebrew[1]]} {photo_hebrew[0]}"
                })
        except:
            continue

    month_dropdown = ""
    for i, name in enumerate(hebrew.MONTHS_HEB):
        if i == 0:
            continue
        selected = "selected" if i == target_month else ""
        month_dropdown += f'<option value="{i}" {selected}>{name}</option>'

    form_html = f"""
        <form method="get">
            Day: <input type="number" name="day" min="1" max="30" value="{target_day}" required>
            Month: <select name="month">{month_dropdown}</select>
            <button type="submit">🔍 Search</button>
        </form>
    """

    if not matching_photos:
        photo_html = "<p>No matches for that Hebrew date.</p>"
    else:
        photo_html = "<p>Photos taken on that Hebrew date:</p>"
        for p in matching_photos:
            photo_html += f'<img src="{p["url"]}"><br><small>{p["date"]} / {p["hebrew_date"]}</small><br><br>'

    return f"""
        <h2>👋 Welcome, {user_name}!</h2>
        <h3>📅 Hebrew Date: {date_label}</h3>
        {form_html}
        {photo_html}
        <br><a href='/logout'>🚪 Logout</a>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
