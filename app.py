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

# Translations dictionary
TRANSLATIONS = {
    "he": {
        "app_name": "📸 ChaiLights – זכרונות תאריך עברי",
        "app_description": "צפה בתמונות Google Photos מתאריכים עבריים מסוימים.",
        "sign_in": "🔗 התחבר עם Google",
        "welcome": "👋 ברוכים הבאים,",
        "hebrew_date": "📅 תאריך עברי:",
        "today": "(היום)",
        "day": "יום:",
        "month": "חודש:",
        "include_eve": "כולל ערב",
        "outside_israel": "מחוץ לישראל",
        "search": "🔍 חפש",
        "jewish_holidays": "🕎 חגים יהודיים",
        "today_is": "🎉 היום הוא",
        "no_photos": "אין תמונות עבור תאריך זה.",
        "matching_photos": "📷 תמונות תואמות",
        "no_photos_suggestions": "🔍 לא נמצאו תמונות. נסו תאריכים אלה:",
        "logout": "🚪 התנתק",
        "language": "שפה:",
        "switch_to_english": "🇺🇸 Switch to English",
        "switch_to_hebrew": "🇮🇱 עבור לעברית"
    },
    "en": {
        "app_name": "📸 ChaiLights – Hebrew Date Memories",
        "app_description": "See your Google Photos from specific Hebrew dates.",
        "sign_in": "🔗 Sign in with Google",
        "welcome": "👋 Welcome,",
        "hebrew_date": "📅 Hebrew Date:",
        "today": "(today)",
        "day": "Day:",
        "month": "Month:",
        "include_eve": "Include Eve",
        "outside_israel": "Outside Israel",
        "search": "🔍 Search",
        "jewish_holidays": "🕎 Jewish Holidays",
        "today_is": "🎉 Today is",
        "no_photos": "No photos for this date.",
        "matching_photos": "📷 Matching Photos",
        "no_photos_suggestions": "🔍 No photos found. Try these dates:",
        "logout": "🚪 Logout",
        "language": "Language:",
        "switch_to_english": "🇺🇸 Switch to English",
        "switch_to_hebrew": "🇮🇱 עבור לעברית"
    }
}

# Hebrew Months List (0-indexed)
HEBREW_MONTHS = {
    "he": [
        "ניסן", "אייר", "סיון", "תמוז", "אב", "אלול",
        "תשרי", "חשון", "כסלו", "טבת", "שבט", "אדר", "אדר ב"
    ],
    "en": [
        "Nisan", "Iyar", "Sivan", "Tammuz", "Av", "Elul",
        "Tishrei", "Cheshvan", "Kislev", "Tevet", "Shevat", "Adar", "Adar II"
    ]
}

# Holiday Definitions with bilingual names
HOLIDAY_LINKS = {
    "he": {
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
    },
    "en": {
        "🎭 Purim": [(11, 14), (12, 14)],
        "🇮🇱 Independence Day": [(8, 5)],
        "🎖️ Memorial Day": [(8, 4)],
        "🕍 Jerusalem Day": [(9, 28)],
        "📜 Shavuot": [(9, 6)],
        "🌳 Tu B'Shvat": [(10, 15)],
        "📯 Rosh Hashanah": [(6, 1), (6, 2)],
        "🤍 Yom Kippur": [(6, 10)],
        "🛖 Sukkot": [(6, d) for d in range(15, 22)],
        "🐸 Pesach": [(0, d) for d in range(15, 22)],
        "🕎 Chanukah": [(8, 25), (8, 26), (8, 27), (8, 28), (8, 29), (8, 30), (9, 1), (9, 2)]
    }
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

def get_extended_holidays(outside_israel, h_year=None, lang="he"):
    holidays = HOLIDAY_LINKS[lang].copy()
    if not h_year:
        today = datetime.now()
        h_year, _, _ = hebrew.from_gregorian(today.year, today.month, today.day)
    if outside_israel:
        for holiday_key in ["📜 שבועות", "🛖 סוכות", "🐸 פסח"] if lang == "he" else ["📜 Shavuot", "🛖 Sukkot", "🐸 Pesach"]:
            dates = holidays.get(holiday_key, [])
            if dates:
                last = dates[-1]
                try:
                    g = hebrew.to_gregorian(h_year, last[0] + 1, last[1])
                    next_day = datetime(*g) + timedelta(days=1)
                    h_next = hebrew.from_gregorian(next_day.year, next_day.month, next_day.day)
                    holidays[holiday_key].append((h_next[1] - 1, h_next[2]))
                except Exception as e:
                    logger.warning(f"Could not extend holiday {holiday_key}: {e}")
    return holidays

def count_holiday_photos(photos, outside_israel=False, lang="he"):
    h_year = photos[0]['_hebrew_year'] if photos else None
    holidays = get_extended_holidays(outside_israel, h_year=h_year, lang=lang)
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

def generate_suggested_dates(h_year, h_month, h_day, include_erev, outside_israel, lang="he"):
    suggestions = []
    if include_erev:
        prev_day = h_day - 1 if h_day > 1 else 30
        prev_month = h_month if h_day > 1 else (h_month - 1 if h_month > 0 else 12)
        suggestions.append((prev_month, prev_day, "ערב" if lang == "he" else "Eve"))
    holidays = get_extended_holidays(outside_israel, h_year=h_year, lang=lang)
    for label, dates in holidays.items():
        for m, d in dates:
            if m == h_month and abs(d - h_day) <= 1:
                suggestions.append((m, d, label))
    return suggestions

@app.route("/")
def index():
    lang = request.args.get("lang", "he")
    if lang not in ["he", "en"]:
        lang = "he"
    session["lang"] = lang
    
    flow = create_flow()
    state = os.urandom(16).hex()
    session['oauth_state'] = state
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state
    )
    
    direction = "rtl" if lang == "he" else "ltr"
    lang_switch = f"<a href='/?lang={'en' if lang == 'he' else 'he'}'>{TRANSLATIONS[lang]['switch_to_english'] if lang == 'he' else TRANSLATIONS[lang]['switch_to_hebrew']}</a>"
    
    return f"""
        <html><body style='font-family:sans-serif; direction:{direction};'>
        <h2>{TRANSLATIONS[lang]["app_name"]}</h2>
        <p>{TRANSLATIONS[lang]["app_description"]}</p>
        <a href='{auth_url}'><button>{TRANSLATIONS[lang]["sign_in"]}</button></a>
        <p>{lang_switch}</p>
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
        
    # Get language preference from query parameter or session, defaulting to Hebrew
    lang = request.args.get("lang", session.get("lang", "he"))
    if lang not in ["he", "en"]:
        lang = "he"
    session["lang"] = lang
    
    direction = "rtl" if lang == "he" else "ltr"
    lang_switch = f"<a href='{request.path}?{get_query_string_with_lang('en' if lang == 'he' else 'he')}'>{TRANSLATIONS[lang]['switch_to_english'] if lang == 'he' else TRANSLATIONS[lang]['switch_to_hebrew']}</a>"

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
    date_label = f"{target_day} {HEBREW_MONTHS[lang][target_month]}"
    if query_day is None:
        date_label += f" {TRANSLATIONS[lang]['today']}"

    photos = get_all_photos(headers)
    matches = [
        (p["baseUrl"] + "=w600-h600", p['_original_date'], 
         f"{p['_hebrew_day']} {HEBREW_MONTHS[lang][p['_hebrew_month']]} {p['_hebrew_year']}")
        for p in photos if p['_hebrew_month'] == target_month and p['_hebrew_day'] == target_day
    ]

    holidays = get_extended_holidays(outside_israel, h_year, lang)
    holiday_html = ""
    holiday_links_html = "<ul>"
    for label, dates in holidays.items():
        for m, d in dates:
            if m == target_month and d == target_day:
                holiday_html += f"<h4>{TRANSLATIONS[lang]['today_is']} {label}!</h4>"
            holiday_links_html += f"<li><a href='/photos?month={m}&day={d}&lang={lang}'>{label} – {d} {HEBREW_MONTHS[lang][m]}</a></li>"
    holiday_links_html += "</ul>"

    suggestion_html = ""
    if not matches:
        suggestions = generate_suggested_dates(h_year, target_month, target_day, include_erev, outside_israel, lang)
        suggestion_html += f"<h4>{TRANSLATIONS[lang]['no_photos_suggestions']}</h4><ul>"
        for sm, sd, label in suggestions:
            suggestion_html += f"<li><a href='/photos?month={sm}&day={sd}&lang={lang}'>{label}: {sd} {HEBREW_MONTHS[lang][sm]}</a></li>"
        suggestion_html += "</ul>"

    photo_html = f"<h4>{TRANSLATIONS[lang]['matching_photos']}</h4>" if matches else f"<p>{TRANSLATIONS[lang]['no_photos']}</p>"
    for url, date, heb_date in matches:
        photo_html += f'<img src="{url}"><br><small>{date} / {heb_date}</small><br><br>'

    month_dropdown = "".join(
        f'<option value="{i}" {"selected" if i == target_month else ""}>{name}</option>'
        for i, name in enumerate(HEBREW_MONTHS[lang])
    )

    form_html = f"""
        <form method='get'>
            <input type='hidden' name='lang' value='{lang}'>
            {TRANSLATIONS[lang]['day']} <input type='number' name='day' min='1' max='30' value='{target_day}'>
            {TRANSLATIONS[lang]['month']} <select name='month'>{month_dropdown}</select><br>
            <label><input type='checkbox' name='erev' value='1' {'checked' if include_erev else ''}> {TRANSLATIONS[lang]['include_eve']}</label><br>
            <label><input type='checkbox' name='outside' value='1' {'checked' if outside_israel else ''}> {TRANSLATIONS[lang]['outside_israel']}</label><br>
            <button type='submit'>{TRANSLATIONS[lang]['search']}</button>
        </form>
        <h4>{TRANSLATIONS[lang]['jewish_holidays']}</h4>{holiday_links_html}
    """

    return f"""
        <html><body style='font-family:sans-serif; max-width:600px; margin:auto; direction:{direction};'>
        <div style='text-align: {'right' if lang == 'he' else 'left'};'>
            {lang_switch}
        </div>
        <h2>{TRANSLATIONS[lang]['welcome']} {user_name}!</h2>
        <h3>{TRANSLATIONS[lang]['hebrew_date']} {date_label}</h3>
        {form_html}
        {holiday_html}
        {photo_html}
        {suggestion_html}
        <br><a href='/logout'>{TRANSLATIONS[lang]['logout']}</a>
        </body></html>
    """

def get_query_string_with_lang(new_lang):
    """Helper function to maintain all query parameters but change the language"""
    params = request.args.copy()
    params["lang"] = new_lang
    return "&".join(f"{k}={v}" for k, v in params.items())

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
