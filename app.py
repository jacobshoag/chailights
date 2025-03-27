# app/main.py
from flask import Flask, redirect, request, session, url_for
import os
import requests
import json
from io import StringIO
from google_auth_oauthlib.flow import Flow
from convertdate import hebrew
from datetime import datetime, timedelta
from collections import defaultdict
import logging

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-insecure-fallback")
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app.config['SESSION_COOKIE_SECURE'] = False  # Should be True in production
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

logging.basicConfig(level=logging.INFO)

SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile"
]

HOLIDAY_LINKS = {
    "🎭 Purim": [(11, 14), (12, 14)],
    "🇮🇱 Yom Ha'atzmaut": [(1, 5)],
    "🎖️ Yom HaZikaron": [(1, 4)],
    "🕍 Yom Yerushalayim": [(2, 28)],
    "📜 Shavuot": [(2, 6)],
    "🌳 Tu BiShvat": [(10, 15)],
    "📯 Rosh Hashanah": [(6, 1), (6, 2)],
    "🤍 Yom Kippur": [(6, 10)],
    "🛖 Sukkot": [(6, d) for d in range(15, 22)],
    "🐸 Passover": [(0, d) for d in range(15, 22)],
    "🕎 Hanukkah": [(8, 25), (8, 26), (8, 27), (8, 28), (8, 29), (8, 30), (9, 1), (9, 2)],
}

# Adjust holiday ranges for outside Israel (adds 1 extra day to specific holidays)
def get_extended_holidays(outside_israel):
    holidays = HOLIDAY_LINKS.copy()
    if outside_israel:
        for holiday in ["📜 Shavuot", "🛖 Sukkot", "🐸 Passover"]:
            dates = holidays.get(holiday, [])
            if dates:
                last = dates[-1]
                try:
                    g_year = 5784  # Placeholder year
                    g = hebrew.to_gregorian(g_year, last[0], last[1])
                    next_day = datetime(*g) + timedelta(days=1)
                    h_next = hebrew.from_gregorian(next_day.year, next_day.month, next_day.day)
                    holidays[holiday].append((h_next[1], h_next[2]))
                except Exception as e:
                    logging.warning(f"Could not extend holiday {holiday}: {e}")
    return holidays

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
        <html><head><style>
        body {{ font-family: sans-serif; margin: 20px; max-width: 600px; }}
        img {{ max-width: 100%; height: auto; }}
        </style></head><body>
        <h2>📸 ChaiLights – Hebrew Date Memories</h2>
        <p>See your old Google Photos taken on this Hebrew date.</p>
        <a href="{auth_url}"><button>🔗 Sign in with Google</button></a>
        </body></html>
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

def refresh_access_token(creds):
    data = {
        'client_id': creds['client_id'],
        'client_secret': creds['client_secret'],
        'refresh_token': creds['refresh_token'],
        'grant_type': 'refresh_token'
    }
    response = requests.post(creds['token_uri'], data=data)
    if response.ok:
        new_token = response.json()['access_token']
        creds['token'] = new_token
        session['credentials'] = creds
    else:
        logging.warning("Failed to refresh token")

def get_matching_hebrew_dates(h_month, h_day, include_erev):
    dates = [(h_month, h_day)]
    if include_erev:
        try:
            g = hebrew.to_gregorian(5784, h_month, h_day)
            dt = datetime(*g) - timedelta(days=1)
            h_prev = hebrew.from_gregorian(dt.year, dt.month, dt.day)
            dates.append((h_prev[1], h_prev[2]))
        except Exception as e:
            logging.warning(f"Could not compute erev date: {e}")
    return set(dates)

def get_all_photos(headers):
    photos = []
    page_token = None
    while True:
        params = {"pageSize": 100}
        if page_token:
            params["pageToken"] = page_token
        r = requests.get("https://photoslibrary.googleapis.com/v1/mediaItems", headers=headers, params=params)
        if r.status_code != 200:
            logging.warning("Failed to fetch photos: %s", r.text)
            break
        data = r.json()
        items = data.get("mediaItems", [])
        photos.extend(items)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return photos

@app.route("/photos")
def get_holiday_for_date(h_month, h_day, outside_israel):
    extended = get_extended_holidays(outside_israel)
    for label, dates in extended.items():
        if (h_month, h_day) in dates:
            return label
    return None

def fetch_photos():
    if "credentials" not in session:
        return redirect(url_for("index"))

    creds = session["credentials"]
    refresh_access_token(creds)
    headers = {"Authorization": f"Bearer {creds['token']}"}
    user_info = requests.get("https://www.googleapis.com/oauth2/v3/userinfo", headers=headers).json()
    user_name = user_info.get("name", "User")

    query_day = request.args.get("day", type=int)
    query_month = request.args.get("month", type=int)
    include_erev = request.args.get("erev") == "1"
    outside_israel = request.args.get("outside") == "1"

    today = datetime.now()
    h_year_today, month_today, day_today = hebrew.from_gregorian(today.year, today.month, today.day)

    target_day = query_day if query_day is not None else day_today
    target_month = query_month if query_month is not None else month_today

    if not (0 <= target_month < len(hebrew.MONTHS_HEB)):
        return "<p>Invalid Hebrew month</p>"

    valid_dates = get_matching_hebrew_dates(target_month, target_day, include_erev)
    date_label = f"{target_day} {hebrew.MONTHS_HEB[target_month]}"
    holiday_announcement = ""
    if query_day is None:
        date_label += " (Today)"
        today_holiday = get_holiday_for_date(target_month, target_day, outside_israel)
        if today_holiday:
            holiday_announcement = f"<h3>📅 Today is {today_holiday.split(' ', 1)[-1]}!</h3>"
    
    if query_day is None:
        date_label += " (Today)"

    photos = get_all_photos(headers)
    matches = []

    for photo in photos:
        date = photo.get("mediaMetadata", {}).get("creationTime", "")[:10]
        try:
            y, m, d = map(int, date.split("-"))
            h_year, h_month, h_day = hebrew.from_gregorian(y, m, d)
            if (h_month, h_day) in valid_dates:
                matches.append((photo["baseUrl"] + "=w600-h600", date, f"{h_day} {hebrew.MONTHS_HEB[h_month]} {h_year}"))
        except Exception as e:
            logging.warning(f"Error parsing photo date: {e}")
            continue

    photo_html = "<h4>📷 Matching Photos</h4>" if matches else "<p>No matches for that Hebrew date.</p>"
    for url, d, h in matches:
        photo_html += f'<img src="{url}"><br><small>{d} / {h}</small><br><br>'

    month_dropdown = ""
    for i, name in enumerate(hebrew.MONTHS_HEB):
        selected = "selected" if i == target_month else ""
        month_dropdown += f'<option value="{i}" {selected}>{name}</option>'

    form_html = f"""
        <form method="get">
            Day: <input type="number" name="day" min="1" max="30" value="{target_day}">
            Month: <select name="month">{month_dropdown}</select><br>
            <label><input type="checkbox" name="erev" value="1" {'checked' if include_erev else ''}> Include Erev</label><br>
            <label><input type="checkbox" name="outside" value="1" {'checked' if outside_israel else ''}> Outside of Israel</label><br>
            <button type="submit">🔍 Search</button>
        </form>
    """

    return f"""
        <html><head><style>
        body {{ font-family: sans-serif; max-width: 600px; margin: auto; }}
        img {{ width: 100%; height: auto; }}
        </style></head><body>
        <h2>👋 Welcome, {user_name}!</h2>
        {holiday_announcement}
        <h3>📅 Hebrew Date: {date_label}</h3>
        {form_html}
        {photo_html}
        <br><a href='/logout'>🚪 Logout</a>
        </body></html>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
