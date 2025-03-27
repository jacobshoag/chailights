from flask import Flask, redirect, request, session, url_for
import os
import requests
import json
from io import StringIO
from google_auth_oauthlib.flow import Flow
from convertdate import hebrew
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)
app.secret_key = "super-dev-secret-key-for-testing-only"
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile"
]

# Base holiday definitions
HOLIDAY_BASE = {
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
}

# Compute extended holiday dates with optional erev and outside-Israel
def compute_holiday_dates(include_erev=False, include_extra=False):
    holiday_map = {}
    for label, base_dates in HOLIDAY_BASE.items():
        dates = base_dates.copy()
        if include_extra and label in ["📜 Shavuot", "🛖 Sukkot", "🐸 Passover"]:
            last = base_dates[-1]
            dates.append((last[0], last[1] + 1))  # Add 8th day
        if include_erev:
            erev_dates = []
            for month, day in base_dates:
                if day > 1:
                    erev_dates.append((month, day - 1))
                else:
                    if month > 0:
                        erev_dates.append((month - 1, 30))
            dates += erev_dates
        unique_dates = list(set(dates))
        holiday_map[label] = unique_dates
    return holiday_map

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

    if query_day is not None and query_month is not None:
        target_day = query_day
        target_month = query_month
        date_label = f"{target_day} {hebrew.MONTHS_HEB[target_month]}"
        active_targets = [(target_month, target_day)]
    elif "holiday_dates" in session:
        active_targets = session.pop("holiday_dates")
        date_label = "Selected Holiday"
    else:
        today = datetime.now()
        h_year, target_month, target_day = hebrew.from_gregorian(today.year, today.month, today.day)
        date_label = f"{target_day} {hebrew.MONTHS_HEB[target_month]} (Today)"
        active_targets = [(target_month, target_day)]

    response = requests.get("https://photoslibrary.googleapis.com/v1/mediaItems?pageSize=100", headers=headers)
    if response.status_code != 200:
        return "<h2>Error fetching photos</h2><p>Try re-authenticating.</p>"

    photos = response.json().get("mediaItems", [])
    hebrew_date_to_photos = defaultdict(list)

    for photo in photos:
        date = photo.get("mediaMetadata", {}).get("creationTime", "")[:10]
        if not date:
            continue
        try:
            year, month, day = map(int, date.split("-"))
            h_year, h_month, h_day = hebrew.from_gregorian(year, month, day)
            key = (h_month, h_day)
            hebrew_date_to_photos[key].append({
                "url": photo["baseUrl"] + "=w400-h400",
                "date": date,
                "hebrew_date": f"{h_day} {hebrew.MONTHS_HEB[h_month]} {h_year}"
            })
        except:
            continue

    matching_photos = []
    for key in active_targets:
        matching_photos.extend(hebrew_date_to_photos.get(key, []))

    # Alt suggestions
    alt_suggestions = ""
    count = 0
    for (h_month, h_day), matches in sorted(hebrew_date_to_photos.items(), key=lambda x: -len(x[1])):
        if (h_month, h_day) in active_targets:
            continue
        alt_suggestions += f"<li><a href='/photos?day={h_day}&month={h_month}'>{h_day} {hebrew.MONTHS_HEB[h_month]}</a> ({len(matches)} photo(s))</li>"
        count += 1
        if count >= 5:
            break
    alt_html = f"<h4>📅 Other Hebrew Dates with Photos:</h4><ul>{alt_suggestions}</ul>" if alt_suggestions else ""

    # Month dropdown
    dropdown = ""
    for i, name in enumerate(hebrew.MONTHS_HEB):
        selected = "selected" if i == target_month else ""
        dropdown += f'<option value="{i}" {selected}>{name}</option>'

    form_html = f"""
        <form method="get">
            Day: <input type="number" name="day" min="1" max="30" value="{target_day if query_day else ''}" required>
            Month: <select name="month">{dropdown}</select>
            <button type="submit">🔍 Search</button>
        </form>
    """

    if not matching_photos:
        photo_html = "<p>No matches for that Hebrew date.</p>"
    else:
        photo_html = f"<p>Photos matching selected date(s) ({len(matching_photos)} total):</p>"
        for p in matching_photos:
            photo_html += f'<img src="{p["url"]}"><br><small>{p["date"]} / {p["hebrew_date"]}</small><br><br>'

    # Holiday links
    holiday_html = """
        <h4>🕎 Jewish Holidays</h4>
        <form id="holidayForm" method="post" action="/holiday">
        <input type="checkbox" name="erev" id="erev"> <label for="erev">Include Erev Chag</label><br>
        <input type="checkbox" name="outside" id="outside"> <label for="outside">Outside of Israel</label><br><br>
        <ul>
    """
    for label in HOLIDAY_BASE.keys():
        holiday_html += f"<li><button type='submit' name='holiday' value='{label}'>{label}</button></li>"
    holiday_html += "</ul></form>"

    return f"""
        <h2>👋 Welcome, {user_name}!</h2>
        <h3>📅 Hebrew Date: {date_label}</h3>
        {form_html}
        {holiday_html}
        {photo_html}
        {alt_html}
        <br><a href='/logout'>🚪 Logout</a>
    """

@app.route("/holiday", methods=["POST"])
def holiday_redirect():
    label = request.form.get("holiday")
    include_erev = bool(request.form.get("erev"))
    include_extra = bool(request.form.get("outside"))
    computed = compute_holiday_dates(include_erev, include_extra)
    session["holiday_dates"] = computed.get(label, [])
    return redirect(url_for("fetch_photos"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
