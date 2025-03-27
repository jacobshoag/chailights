from flask import Flask, redirect, request, session, url_for
import os
import requests
import json
from io import StringIO
from google_auth_oauthlib.flow import Flow
from convertdate import hebrew
from datetime import datetime, timedelta
import logging

app = Flask(__name__)
app.secret_key = "super-dev-secret-key-for-testing-only"
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def get_all_photos(headers, max_photos=500):
    """
    Fetch photos with pagination and limit
    
    Args:
        headers (dict): Authorization headers
        max_photos (int): Maximum number of photos to fetch
    
    Returns:
        list: List of photo items
    """
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
            photos.extend(items)
            
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        
        except requests.RequestException as e:
            logger.error(f"Error fetching photos: {e}")
            break
    
    return photos

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

def get_extended_holidays(outside_israel):
    """
    Extend holidays for diaspora communities
    
    Args:
        outside_israel (bool): Whether user is outside Israel
    
    Returns:
        dict: Updated holiday dates
    """
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
                    logger.warning(f"Could not extend holiday {holiday}: {e}")
    return holidays

def generate_suggested_dates(h_year, h_month, h_day, include_erev, outside_israel):
    """
    Generate suggested alternative dates when no photos are found
    
    Args:
        h_year (int): Hebrew year
        h_month (int): Hebrew month
        h_day (int): Hebrew day
        include_erev (bool): Include eve of holidays
        outside_israel (bool): User is outside Israel
    
    Returns:
        list: Suggested alternative dates
    """
    suggestions = []
    
    # Erev handling
    if include_erev:
        # Previous day could be Erev of a holiday
        erev_day = h_day - 1 if h_day > 1 else 30
        erev_month = h_month if h_day > 1 else (h_month - 1 if h_month > 0 else 12)
        suggestions.append((erev_month, erev_day, "Erev"))
    
    # Holiday extensions for diaspora
    extended_holidays = get_extended_holidays(outside_israel)
    for holiday, dates in extended_holidays.items():
        for hol_month, hol_day in dates:
            if hol_month == h_month and abs(hol_day - h_day) <= 1:
                suggestions.append((hol_month, hol_day, holiday))
    
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

@app.route("/photos")
def fetch_photos():
    if "credentials" not in session:
        return redirect(url_for("index"))

    creds = session["credentials"]
    headers = {"Authorization": f"Bearer {creds['token']}"}
    user_info = requests.get("https://www.googleapis.com/oauth2/v3/userinfo", headers=headers).json()
    user_name = user_info.get("name", "User")

    # Get query parameters
    query_day = request.args.get("day", type=int)
    query_month = request.args.get("month", type=int)
    include_erev = request.args.get("erev") == "1"
    outside_israel = request.args.get("outside") == "1"

    # Get current Hebrew date
    today = datetime.now()
    h_year_today, month_today, day_today = hebrew.from_gregorian(today.year, today.month, today.day)

    # Set target date
    target_day = query_day if query_day is not None else day_today
    target_month = query_month if query_month is not None else month_today

    # Create date label
    date_label = f"{target_day} {hebrew.MONTHS_HEB[target_month]}"
    if query_day is None:
        date_label += " (Today)"

    # Fetch photos
    photos = get_all_photos(headers)
    matches = []
    hebrew_date_to_photos = {}

    # Process photos
    for photo in photos:
        date = photo.get("mediaMetadata", {}).get("creationTime", "")[:10]
        try:
            y, m, d = map(int, date.split("-"))
            h_year, h_month, h_day = hebrew.from_gregorian(y, m, d)
            
            # Track photos by Hebrew date
            key = f"{h_month},{h_day}"
            if not hebrew_date_to_photos.get(key):
                hebrew_date_to_photos[key] = []
            hebrew_date_to_photos[key].append(photo)

            # Check for matching date
            if h_month == target_month and h_day == target_day:
                matches.append((photo["baseUrl"] + "=w600-h600", date, f"{h_day} {hebrew.MONTHS_HEB[h_month]} {h_year}"))
        except:
            continue

    # Holiday links
    holidays = get_extended_holidays(outside_israel)
    holiday_links_html = "<h4>🕎 Jewish Holidays</h4><ul>"
    holiday_html = ""

    # Process holiday links and announcements
    for label, dates in holidays.items():
        holiday_match = False
        for m, d in dates:
            holiday_key = f"{m},{d}"
            if holiday_key == f"{target_month},{target_day}":
                holiday_match = True
                holiday_html += f"<h4>🎉 Today is {label}!</h4>"
            
            count = len(hebrew_date_to_photos.get(holiday_key, []))
            holiday_links_html += f"<li><a href='/photos?month={m}&day={d}'>{label}</a> ({count} photo(s))</li>"

    holiday_links_html += "</ul>"

    # Photo display
    if not matches:
        # Generate suggestions if no photos found
        suggestions = generate_suggested_dates(h_year_today, target_month, target_day, include_erev, outside_israel)
        suggestion_html = "<h4>🔍 No Photos Found. Try these dates:</h4><ul>"
        for s_month, s_day, s_type in suggestions:
            suggestion_html += f'<li><a href="/photos?month={s_month}&day={s_day}">{s_type}: {s_day} {hebrew.MONTHS_HEB[s_month]}</a></li>'
        suggestion_html += "</ul>"
    else:
        suggestion_html = ""

    photo_html = "<h4>📷 Matching Photos</h4>" if matches else "<p>No matches for that Hebrew date.</p>"
    for url, d, h in matches:
        photo_html += f'<img src="{url}"><br><small>{d} / {h}</small><br><br>'

    # Month dropdown
    month_dropdown = ""
    for i, name in enumerate(hebrew.MONTHS_HEB):
        selected = "selected" if i == target_month else ""
        month_dropdown += f'<option value="{i}" {selected}>{name}</option>'

    # Search form
    form_html = f"""
        <form method="get">
            Day: <input type="number" name="day" min="1" max="30" value="{target_day}">
            Month: <select name="month">{month_dropdown}</select><br>
            <label><input type="checkbox" name="erev" value="1" {'checked' if include_erev else ''}> Include Erev</label><br>
            <label><input type="checkbox" name="outside" value="1" {'checked' if outside_israel else ''}> Outside of Israel</label><br>
            <button type="submit">🔍 Search</button>
        </form>
        {holiday_links_html}
    """

    return f"""
        <html><head><style>
        body {{ font-family: sans-serif; max-width: 600px; margin: auto; }}
        img {{ width: 100%; height: auto; }}
        a {{ color: blue; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        </style></head><body>
        <h2>👋 Welcome, {user_name}!</h2>
        <h3>📅 Hebrew Date: {date_label}</h3>
        {form_html}
        {holiday_html}
        {photo_html}
        {suggestion_html}
        <br><a href='/logout'>🚪 Logout</a>
        </body></html>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
