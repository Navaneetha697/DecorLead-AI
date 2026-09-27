from flask import Flask, jsonify, request, render_template
from flask_cors import CORS

import requests
import os
import html
import re

import resend
from dotenv import load_dotenv


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")

load_dotenv(ENV_FILE, override=True)

FOURSQUARE_API_KEY = os.getenv("FOURSQUARE_API_KEY", "").strip()
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)
CORS(app)


# ============================================================
# BUYER KEYWORDS
# ============================================================

BUYER_KEYWORDS = {

    "Furniture Store": [
        "furniture",
        "furniture store",
        "furnishings",
        "home furniture"
    ],

    "Home Decor Store": [
        "home decor",
        "home decoration",
        "decor",
        "home goods",
        "home furnishings",
        "interior"
    ],

    "Interior Designer": [
        "interior designer",
        "interior design",
        "design studio",
        "interiors"
    ],

    "Gift Shop": [
        "gift shop",
        "gifts",
        "gift store",
        "home gifts"
    ],

    "Home Furnishing Store": [
        "home furnishing",
        "home furnishings",
        "furniture",
        "furnishings",
        "home goods"
    ]
}


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def home():
    return render_template("index.html")


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/api/health", methods=["GET"])
def health():

    return jsonify({
        "status": "success",
        "message": "DecorLead AI API is running",
        "foursquare_configured": bool(FOURSQUARE_API_KEY),
        "resend_configured": bool(RESEND_API_KEY)
    })


# ============================================================
# FOURSQUARE PLACE DETAILS
# ============================================================

def get_place_details(place_id):

    if not FOURSQUARE_API_KEY:
        return {}

    url = f"https://places-api.foursquare.com/places/{place_id}"

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {FOURSQUARE_API_KEY}",
        "X-Places-Api-Version": "2025-06-17"
    }

    params = {
        "fields": (
            "fsq_place_id,"
            "name,"
            "categories,"
            "location,"
            "tel,"
            "website,"
            "email,"
            "rating"
        )
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=20
        )

        if response.status_code == 200:
            return response.json()

        print(
            "Foursquare place details error:",
            response.status_code,
            response.text
        )

        return {}

    except requests.RequestException as e:

        print("Foursquare details request error:", str(e))

        return {}


# ============================================================
# HELPER - CHECK BUYER RELEVANCE
# ============================================================

def is_relevant_buyer(name, categories, buyer_type):

    keywords = BUYER_KEYWORDS.get(
        buyer_type,
        []
    )

    text = (
        str(name) + " " +
        " ".join(categories)
    ).lower()

    for keyword in keywords:

        if keyword.lower() in text:
            return True

    return False


# ============================================================
# HELPER - EMAIL VALIDATION
# ============================================================

def is_valid_email(email):

    if not email:
        return False

    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

    return bool(
        re.match(pattern, email)
    )


# ============================================================
# SEARCH POTENTIAL BUYERS
# ============================================================

@app.route("/api/search-buyers", methods=["POST"])
def search_buyers():

    try:

        data = request.get_json() or {}

        product = data.get(
            "product",
            ""
        ).strip()

        buyer_type = data.get(
            "buyer_type",
            ""
        ).strip()

        location = data.get(
            "location",
            ""
        ).strip()

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if not product:

            return jsonify({
                "success": False,
                "error": "Product is required"
            }), 400

        if not buyer_type:

            return jsonify({
                "success": False,
                "error": "Buyer type is required"
            }), 400

        if not location:

            return jsonify({
                "success": False,
                "error": "US location is required"
            }), 400

        # ----------------------------------------------------
        # FOURSQUARE KEY CHECK
        # ----------------------------------------------------

        if not FOURSQUARE_API_KEY:

            return jsonify({
                "success": False,
                "error": "FOURSQUARE_API_KEY is not configured"
            }), 500

        # ----------------------------------------------------
        # FOURSQUARE SEARCH
        # ----------------------------------------------------

        url = "https://places-api.foursquare.com/places/search"

        headers = {
            "Accept": "application/json",
            "Authorization": (
                f"Bearer {FOURSQUARE_API_KEY}"
            ),
            "X-Places-Api-Version": "2025-06-17"
        }

        # Keep these parameters simple because this
        # configuration is already working in your project.
        params = {
            "query": buyer_type,
            "near": location,
            "limit": 20,
            "sort": "RELEVANCE"
        }

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code != 200:

            print(
                "Foursquare search error:",
                response.status_code,
                response.text
            )

            return jsonify({
                "success": False,
                "error": "Foursquare API request failed",
                "details": response.text
            }), 502

        result = response.json()

        places = result.get(
            "results",
            []
        )

        buyers = []

        # ----------------------------------------------------
        # PROCESS RESULTS
        # ----------------------------------------------------

        for place in places:

            name = place.get(
                "name",
                "Unknown Business"
            )

            categories_data = place.get(
                "categories",
                []
            )

            categories = []

            for category in categories_data:

                category_name = category.get(
                    "name",
                    ""
                )

                if category_name:
                    categories.append(
                        category_name
                    )

            # ------------------------------------------------
            # RELEVANCE FILTER
            # ------------------------------------------------

            if not is_relevant_buyer(
                name,
                categories,
                buyer_type
            ):
                continue

            # ------------------------------------------------
            # PLACE ID
            # ------------------------------------------------

            place_id = place.get(
                "fsq_place_id"
            )

            if not place_id:
                continue

            # ------------------------------------------------
            # LOCATION FROM SEARCH
            # ------------------------------------------------

            location_data = place.get(
                "location",
                {}
            ) or {}

            # ------------------------------------------------
            # GET DETAILED INFORMATION
            # ------------------------------------------------

            details = get_place_details(
                place_id
            )

            details_location = details.get(
                "location",
                {}
            ) or {}

            # ------------------------------------------------
            # CONTACT INFORMATION
            # ------------------------------------------------

            email = (
                details.get("email")
                or place.get("email")
                or ""
            )

            phone = (
                details.get("tel")
                or place.get("tel")
                or ""
            )

            website = (
                details.get("website")
                or place.get("website")
                or ""
            )

            rating = (
                details.get("rating")
                or place.get("rating")
            )

            # ------------------------------------------------
            # ADDRESS
            # ------------------------------------------------

            address = (
                details_location.get("formatted_address")
                or location_data.get("formatted_address")
                or location_data.get("address")
                or ""
            )

            city = (
                details_location.get("locality")
                or location_data.get("locality")
                or ""
            )

            state = (
                details_location.get("region")
                or location_data.get("region")
                or ""
            )

            postcode = (
                details_location.get("postcode")
                or location_data.get("postcode")
                or ""
            )

            # ------------------------------------------------
            # BUILD BUYER OBJECT
            # ------------------------------------------------

            buyer = {
                "id": place_id,
                "name": name,
                "category": ", ".join(categories),
                "rating": rating,
                "phone": phone,
                "email": email,
                "website": website,
                "address": address,
                "city": city,
                "state": state,
                "postcode": postcode,
                "latitude": place.get("latitude"),
                "longitude": place.get("longitude")
            }

            buyers.append(
                buyer
            )

        # ----------------------------------------------------
        # RESPONSE
        # ----------------------------------------------------

        return jsonify({
            "success": True,
            "product": product,
            "buyer_type": buyer_type,
            "location": location,
            "count": len(buyers),
            "buyers": buyers
        })

    except requests.RequestException as e:

        print(
            "Foursquare request exception:",
            str(e)
        )

        return jsonify({
            "success": False,
            "error": "Unable to connect to Foursquare API"
        }), 502

    except Exception as e:

        print(
            "Search buyers exception:",
            str(e)
        )

        return jsonify({
            "success": False,
            "error": "Unable to find buyers",
            "details": str(e)
        }), 500
        # ============================================================
# SEND OUTREACH EMAIL
# ============================================================

@app.route("/api/send-email", methods=["POST"])
def send_email():

    try:

        data = request.get_json() or {}

        # ----------------------------------------------------
        # GET EMAIL DATA
        # ----------------------------------------------------

        to_email = data.get(
            "to",
            ""
        ).strip()

        subject = data.get(
            "subject",
            ""
        ).strip()

        body = data.get(
            "body",
            ""
        ).strip()

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if not to_email:

            return jsonify({
                "success": False,
                "error": "Recipient email is required"
            }), 400

        if not is_valid_email(to_email):

            return jsonify({
                "success": False,
                "error": "Please enter a valid recipient email"
            }), 400

        if not subject:

            return jsonify({
                "success": False,
                "error": "Email subject is required"
            }), 400

        if not body:

            return jsonify({
                "success": False,
                "error": "Email message is required"
            }), 400

        # ----------------------------------------------------
        # CHECK RESEND API KEY
        # ----------------------------------------------------

        # The key was loaded from .env at application startup.
        if not RESEND_API_KEY:

            return jsonify({
                "success": False,
                "error": "RESEND_API_KEY is not configured"
            }), 500

        # ----------------------------------------------------
        # CONFIGURE RESEND
        # ----------------------------------------------------

        resend.api_key = RESEND_API_KEY

        # ----------------------------------------------------
        # CONVERT TEXT TO SAFE HTML
        # ----------------------------------------------------

        safe_body = html.escape(
            body
        )

        html_body = safe_body.replace(
            "\n",
            "<br>"
        )

        # ----------------------------------------------------
        # SEND EMAIL
        # ----------------------------------------------------

        email_response = resend.Emails.send({

            "from": "onboarding@resend.dev",

            "to": [
                to_email
            ],

            "subject": subject,

            "html": html_body
        })

        print(
            "Email sent successfully:",
            email_response
        )

        # ----------------------------------------------------
        # SUCCESS RESPONSE
        # ----------------------------------------------------

        return jsonify({
            "success": True,
            "message": "Outreach email sent successfully",
            "data": email_response
        }), 200

    except Exception as e:

        print(
            "RESEND ERROR:",
            str(e)
        )

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("DecorLead AI")
    print("=" * 60)

    print(
        "Foursquare configured:",
        bool(FOURSQUARE_API_KEY)
    )

    print(
        "Resend configured:",
        bool(RESEND_API_KEY)
    )

    print(
        "Environment file:",
        ENV_FILE
    )

    print("=" * 60)

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )