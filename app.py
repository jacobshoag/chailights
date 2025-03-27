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
    user_name = session.get("user_name", "User")
    date_label = session.get("date_label", "")
    form_html = session.get("form_html", "")
    # Generate holiday links with photo counts
    hebrew_date_to_photos = session.get("hebrew_date_to_photos", {})
    holiday_links_html = "<h4>🕎 Jewish Holidays</h4><ul>"
    for label, dates in HOLIDAY_LINKS.items():
        count = sum(len(hebrew_date_to_photos.get(f"{m},{d}", [])) for m, d in dates)
        if dates:
            m, d = dates[0]
            holiday_links_html += f"<li><a href='/photos?month={m}&day={d}'>{label}</a> ({count} photo(s))</li>"
    holiday_links_html += "</ul>"
    form_html += holiday_links_html
    holiday_announcement = session.get("holiday_announcement", "")
    holiday_html = session.get("holiday_html", "")
    photo_html = session.get("photo_html", "")
    alt_html = session.get("alt_html", "")
    return f"""
        <html><head><style>
        body {{ font-family: sans-serif; max-width: 600px; margin: auto; }}
        img {{ width: 100%; height: auto; }}
        </style></head><body>
        <h2>👋 Welcome, {user_name}!</h2>
        {holiday_announcement}
        <h3>📅 Hebrew Date: {date_label}</h3>
        {form_html}
        {holiday_html}
        {photo_html}
        {alt_html}
        <br><a href='/logout'>🚪 Logout</a>
        </body></html>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
