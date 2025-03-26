from flask import Flask, redirect, request, session, url_for
import os
import requests
from google_auth_oauthlib.flow import Flow
from convertdate import hebrew
from datetime import datetime

app = Flask(__name__)
app.secret_key = "super-dev-secret-key-for-testing-only"
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

CLIENT_SECRET_FILE = "client_secret_302588911248-331ltqb4hodno7no7kegoaqe32h7ijfb.apps.googleusercontent.com.json"
REDIRECT_URI = "http://localhost:5000/oauth/callback"
SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile"
]

def create_flow():
    return Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
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

    today = datetime.now()
    h_year, today_month, today_day = hebrew.from_gregorian(today.year, today.month, today.day)
    target_day = query_day or today_day
    target_month = query_month or today_month
    date_label = f"{target_day} {hebrew.MONTHS_HEB[target_month]}"
    if not query_day or not query_month:
        date_label += " (Today)"

    # Fetch photos
    response = requests.get("https://photoslibrary.googleapis.com/v1/mediaItems?pageSize=100", headers=headers)
    if response.status_code != 200:
        return "<h2>Error fetching photos</h2><p>Try re-authenticating.</p>"

    photos = response.json().get("mediaItems", [])
    matching_photos = []
    hebrew_date_counts = {}

    for photo in photos:
        date = photo.get("mediaMetadata", {}).get("creationTime", "")[:10]
        if not date:
            continue
        try:
            year, month, day = map(int, date.split("-"))
            h_year, h_month, h_day = hebrew.from_gregorian(year, month, day)
            heb_key = (h_day, h_month)
            hebrew_date_counts[heb_key] = hebrew_date_counts.get(heb_key, 0) + 1

            if h_day == target_day and h_month == target_month:
                matching_photos.append({
                    "url": photo["baseUrl"] + "=w400-h400",
                    "date": date,
                    "hebrew_date": f"{h_day} {hebrew.MONTHS_HEB[h_month]} {h_year}"
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

    # Add list of alternative Hebrew dates with photo counts
    alt_html = "<h4>🗓️ Hebrew Dates with Your Photos:</h4><ul>"
    for (d, m), count in sorted(hebrew_date_counts.items(), key=lambda x: -x[1])[:5]:
        month_name = hebrew.MONTHS_HEB[m]
        alt_html += f'<li><a href="/photos?day={d}&month={m}">{d} {month_name}</a> ({count} photo{"s" if count != 1 else ""})</li>'
    alt_html += "</ul>"

    return f"""
        <h2>👋 Welcome, {user_name}!</h2>
        <h3>📅 Hebrew Date: {date_label}</h3>
        {form_html}
        {photo_html}
        {alt_html}
        <br><a href='/logout'>🚪 Logout</a>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="localhost", port=5000, debug=True)
