from flask import Flask, redirect, request, session, url_for
import os
import requests
import json
from io import StringIO
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from convertdate import hebrew
from datetime import datetime, timedelta
import logging

# Flask setup
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Secure session settings
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OAuth Scopes
SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile"
]

# Hebrew Months List (0-indexed)
HEBREW_MONTHS = [
    "ניסן", "אייר", "סיון", "תמוז", "אב", "אלול",
    "תשרי", "חשון", "כסלו", "טבת", "שבט", "אדר", "אדר ב"
]

# Holiday Definitions
HOLIDAY_LINKS = {
    "🎭 פורים": [(11, 14), (12, 14)],
    "🇮🇱 יום העצמאות": [(8, 5)],
    "🎖️ יום הזיכרון": [(8, 4)],
    "🕍 יום ירושלים": [(9, 28)],
    "📜 שבועות": [(9, 6)],
    "🌳 ט״ו בשבט": [(10, 15)],
    "📯 ראש השנה": [(6, 1), (6, 2)],
    "🤍 יום כיפור": [(6, 10)],
    "🛖 סוכות": [(6, d) for d in range(15, 22)],
    "🐸 פסח": [(0, d) for d in range(15, 22)],
    "🕎 חנוכה": [(8, 25), (8, 26), (8, 27), (8, 28), (8, 29), (8, 30), (9, 1), (9, 2)]
}

def get_all_photos(headers, max_photos=2500):
    photos = []
    page_token = None
    while len(photos) < max_photos:
        params = {"pageSize": min(100, max_photos - len(photos))}
        if page_token:
            params["pageToken"] = page_token
        try:
            r = requests.get(
                "https://photoslibrary.googleapis.com/v1/mediaItems",
                headers=headers,
                params=params,
                timeout=10
            )
            r.raise_for_status()
            data = r.json()
            items = data.get("mediaItems", [])
            for item in items:
                date = item.get("mediaMetadata", {}).get("creationTime", "")[:10]
                try:
                    y, m, d = map(int, date.split("-"))
                    h_year, h_month, h_day = hebrew.from_gregorian(y, m, d)
                    item['_hebrew_month'] = h_month - 1
                    item['_hebrew_day'] = h_day
                    item['_hebrew_year'] = h_year
                    item['_original_date'] = date
                    photos.append(item)
                except Exception as e:
                    logger.warning(f"Could not convert date for item: {e}")
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        except requests.RequestException as e:
            logger.error(f"Error fetching photos: {e}")
            break
    return photos

def get_extended_holidays(outside_israel, h_year=None):
    holidays = HOLIDAY_LINKS.copy()
    if not h_year:
        today = datetime.now()
        h_year, _, _ = hebrew.from_gregorian(today.year, today.month, today.day)
    if outside_israel:
        for holiday in ["📜 שבועות", "🛖 סוכות", "🐸 פסח"]:
            dates = holidays.get(holiday, [])
            if dates:
                last = dates[-1]
                try:
                    g = hebrew.to_gregorian(h_year, last[0] + 1, last[1])
                    next_day = datetime(*g) + timedelta(days=1)
                    h_next = hebrew.from_gregorian(next_day.year, next_day.month, next_day.day)
                    holidays[holiday].append((h_next[1] - 1, h_next[2]))
                except Exception as e:
                    logger.warning(f"Could not extend holiday {holiday}: {e}")
    return holidays

def count_holiday_photos(photos, outside_israel=False):
    h_year = photos[0]['_hebrew_year'] if photos else None
    holidays = get_extended_holidays(outside_israel, h_year=h_year)
    results = []
    for holiday, dates in holidays.items():
        matches = set()
        for m, d in dates:
            matches.update(
                p['_original_date'] for p in photos if p['_hebrew_month'] == m and p['_hebrew_day'] == d
            )
        results.append(f"{holiday} ({len(matches)} photo(s))")
    return results

def create_flow():
    secret = os.environ.get("GOOGLE_CLIENT_SECRET_JSON")
    if not secret:
        raise Exception("Missing GOOGLE_CLIENT_SECRET_JSON")
    config = json.load(StringIO(secret))
    return Flow.from_client_config(
        config,
        scopes=SCOPES,
        redirect_uri="https://chailights.onrender.com/oauth/callback"
    )

def generate_suggested_dates(h_year, h_month, h_day, include_erev, outside_israel):
    suggestions = []
    if include_erev:
        prev_day = h_day - 1 if h_day > 1 else 30
        prev_month = h_month if h_day > 1 else (h_month - 1 if h_month > 0 else 12)
        suggestions.append((prev_month, prev_day, "ערב"))
    holidays = get_extended_holidays(outside_israel, h_year=h_year)
    for label, dates in holidays.items():
        for m, d in dates:
            if m == h_month and abs(d - h_day) <= 1:
                suggestions.append((m, d, label))
    return suggestions

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
        <html><body style='font-family:sans-serif'>
        <h2>📸 ChaiLights – Hebrew Date Memories</h2>
        <p>See your Google Photos from specific Hebrew dates.</p>
        <a href='{auth_url}'><button>🔗 Sign in with Google</button></a>
        </body></html>
    """

@app.route("/oauth/callback")
def oauth_callback():
    if session.get("oauth_state") != request.args.get("state"):
        return "<h2>Invalid state</h2><p>Please try again.</p>"
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

    creds = Credentials(**session["credentials"])
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleRequest())
            session["credentials"] = {
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri': creds.token_uri,
                'client_id': creds.client_id,
                'client_secret': creds.client_secret,
                'scopes': creds.scopes
            }
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return "<h3>Session expired or token refresh failed. Please <a href='/'>log in again</a>.</h3>"

    headers = {"Authorization": f"Bearer {creds.token}"}
    user_info = requests.get("https://www.googleapis.com/oauth2/v3/userinfo", headers=headers).json()
    user_name = user_info.get("name", "User")

    query_day = request.args.get("day", type=int)
    query_month = request.args.get("month", type=int)
    include_erev = request.args.get("erev") == "1"
    outside_israel = request.args.get("outside") == "1"

    today = datetime.now()
    h_year, h_month, h_day = hebrew.from_gregorian(today.year, today.month, today.day)

    target_day = query_day if query_day is not None else h_day
    target_month = query_month if query_month is not None else h_month - 1
    date_label = f"{target_day} {HEBREW_MONTHS[target_month]}"
    if query_day is None:
        date_label += " (היום)"

    photos = get_all_photos(headers)
    matches = [
        (p["baseUrl"] + "=w600-h600", p['_original_date'], f"{p['_hebrew_day']} {HEBREW_MONTHS[p['_hebrew_month']]} {p['_hebrew_year']}")
        for p in photos if p['_hebrew_month'] == target_month and p['_hebrew_day'] == target_day
    ]

    holidays = get_extended_holidays(outside_israel, h_year)
    holiday_html = ""
    holiday_links_html = "<ul>"
    for label, dates in holidays.items():
        for m, d in dates:
            if m == target_month and d == target_day:
                holiday_html += f"<h4>🎉 היום הוא {label}!</h4>"
            holiday_links_html += f"<li><a href='/photos?month={m}&day={d}'>{label} – {d} {HEBREW_MONTHS[m]}</a></li>"
    holiday_links_html += "</ul>"

    suggestion_html = ""
    if not matches:
        suggestions = generate_suggested_dates(h_year, target_month, target_day, include_erev, outside_israel)
        suggestion_html += "<h4>🔍 לא נמצאו תמונות. נסו תאריכים אלה:</h4><ul>"
        for sm, sd, label in suggestions:
            suggestion_html += f"<li><a href='/photos?month={sm}&day={sd}'>{label}: {sd} {HEBREW_MONTHS[sm]}</a></li>"
        suggestion_html += "</ul>"

    photo_html = "<h4>📷 תמונות תואמות</h4>" if matches else "<p>אין תמונות עבור תאריך זה.</p>"
    for url, date, heb_date in matches:
        photo_html += f'<img src="{url}"><br><small>{date} / {heb_date}</small><br><br>'

    month_dropdown = "".join(
        f'<option value="{i}" {"selected" if i == target_month else ""}>{name}</option>'
        for i, name in enumerate(HEBREW_MONTHS)
    )

    form_html = f"""
        <form method='get'>
            יום: <input type='number' name='day' min='1' max='30' value='{target_day}'>
            חודש: <select name='month'>{month_dropdown}</select><br>
            <label><input type='checkbox' name='erev' value='1' {'checked' if include_erev else ''}> כולל ערב</label><br>
            <label><input type='checkbox' name='outside' value='1' {'checked' if outside_israel else ''}> מחוץ לישראל</label><br>
            <button type='submit'>🔍 חפש</button>
        </form>
        <h4>🕎 חגים יהודיים</h4>{holiday_links_html}
    """

    return f"""
        <html><body style='font-family:sans-serif; max-width:600px; margin:auto; direction:rtl;'>
        <h2>👋 ברוכים הבאים, {user_name}!</h2>
        <h3>📅 תאריך עברי: {date_label}</h3>
        {form_html}
        {holiday_html}
        {photo_html}
        {suggestion_html}
        <br><a href='/logout'>🚪 התנתק</a>
        </body></html>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
