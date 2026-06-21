import os
import math
import threading
from flask import Flask, request, jsonify, render_template
from openai import AzureOpenAI

from db import test_connection, get_connection

app = Flask(__name__)


# -------------------------
# Azure OpenAI Setup
# -------------------------
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
)

DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")


# -------------------------
# Module 9: Category-to-NAICS Lookup
# -------------------------
NAICS_LOOKUP = {
    "hardware store":         "4441",
    "hardware":               "4441",
    "home improvement":       "4441",
    "building materials":     "4441",
    "lumber store":           "4441",
    "home depot":             "4441",
    "lowes":                  "4441",
    "lowe's":                 "4441",
    "liquor store":           "445310",
    "wine store":             "445310",
    "beer store":             "445310",
    "alcohol store":          "445310",
    "auto parts":             "441310",
    "car parts":              "441310",
    "tire store":             "441310",
    "automotive parts":       "441310",
    "gas station":            "447110",
    "petrol station":         "447110",
    "fuel station":           "447110",
    "jewelry store":          "448310",
    "jewelry":                "448310",
    "luggage store":          "448310",
    "general store":          "452319",
    "warehouse store":        "452319",
    "department store":       "452319",
    "walmart":                "452319",
    "costco":                 "452319",
    "target":                 "452319",
    "bakery":                 "311811",
    "bread store":            "311811",
    "pastry shop":            "311811",
    "bank":                   "522110",
    "credit union":           "522110",
    "financial services":     "522310",
    "investment office":      "523930",
    "insurance office":       "524113",
    "insurance":              "524113",
    "real estate office":     "531210",
    "real estate agent":      "531210",
    "real estate":            "531210",
    "property rental":        "531120",
    "rental office":          "531120",
    "college":                "611310",
    "university":             "611310",
    "school":                 "611310",
    "dentist":                "621210",
    "dental office":          "621210",
    "dental":                 "621210",
    "clinic":                 "6214",
    "urgent care":            "6214",
    "outpatient clinic":      "6214",
    "medical lab":            "621511",
    "diagnostic lab":         "621511",
    "salon":                  "812910",
    "spa":                    "812910",
    "nail salon":             "812910",
    "barber":                 "812910",
    "personal services":      "812910",
    "phone store":            "517312",
    "telecom store":          "517312",
    "wireless store":         "517312",
    "mobile store":           "517312",
}

NAICS_NAMES = {
    "4441":   "Building Material and Supplies Dealers",
    "445310": "Beer, Wine, and Liquor Stores",
    "441310": "Automotive Parts, Accessories, and Tire Stores",
    "447110": "Gasoline Stations",
    "448310": "Jewelry, Luggage, and Leather Goods Stores",
    "452319": "General Merchandise Stores",
    "311811": "Bakeries",
    "3399":   "Other Miscellaneous Manufacturing",
    "512240": "Sound Recording Industries",
    "517312": "Wired and Wireless Telecommunications Carriers",
    "522110": "Depository Credit Intermediation",
    "522310": "Activities Related to Credit Intermediation",
    "523930": "Other Financial Investment Activities",
    "524113": "Insurance Carriers",
    "531120": "Lessors of Real Estate",
    "531210": "Offices of Real Estate Agents and Brokers",
    "611310": "Colleges, Universities, and Professional Schools",
    "621210": "Offices of Dentists",
    "6214":   "Outpatient Care Centers",
    "621511": "Medical and Diagnostic Laboratories",
    "812910": "Other Personal Services",
    "922110": "Justice, Public Order, and Safety Activities",
    "453991": "Other Miscellaneous Store Retailers",
}


# -------------------------
# Haversine distance helper
# -------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    R     = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a     = (math.sin(d_lat / 2) ** 2 +
             math.cos(math.radians(lat1)) *
             math.cos(math.radians(lat2)) *
             math.sin(d_lon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# -------------------------
# Routes
# -------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/dbcheck")
def dbcheck():
    try:
        ok = test_connection()
        return jsonify({"ok": ok})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# -------------------------
# Module 7 - Migration Routes (commented out after migration)
# -------------------------
# @app.route("/admin/migrate")
# def admin_migrate():
#     ...

# @app.route("/admin/migrate/status")
# def admin_migrate_status():
#     ...


@app.route("/db_structure")
def db_structure():
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.name   AS TABLE_NAME,
                   p.rows   AS row_count
            FROM   sys.tables     t
            INNER JOIN sys.indexes    i ON t.object_id = i.object_id
            INNER JOIN sys.partitions p ON i.object_id = p.object_id
                                       AND i.index_id  = p.index_id
            WHERE  t.is_ms_shipped = 0
              AND  i.index_id IN (0, 1)
            ORDER  BY t.name
        """)
        result = [
            {"TABLE_NAME": str(row[0]), "row_count": int(row[1])}
            for row in cursor.fetchall()
        ]
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# -------------------------
# Module 9: POI Data Endpoint
# -------------------------
@app.route("/api/pois")
def get_pois():
    naics    = request.args.get("naics",    "").strip()
    category = request.args.get("category", "").strip()

    try:
        conn   = get_connection()
        cursor = conn.cursor()

        if naics:
            cursor.execute("""
                SELECT TOP 200
                    p.location_name, p.latitude, p.longitude,
                    p.top_category,  cp.naics_code
                FROM pois p
                LEFT JOIN category_parameters cp ON p.top_category = cp.top_category
                WHERE cp.naics_code = ?
                  AND p.latitude  IS NOT NULL
                  AND p.longitude IS NOT NULL
            """, (naics,))
        elif category:
            cursor.execute("""
                SELECT TOP 200
                    p.location_name, p.latitude, p.longitude,
                    p.top_category,  cp.naics_code
                FROM pois p
                LEFT JOIN category_parameters cp ON p.top_category = cp.top_category
                WHERE p.top_category = ?
                  AND p.latitude  IS NOT NULL
                  AND p.longitude IS NOT NULL
            """, (category,))
        else:
            cursor.execute("""
                SELECT TOP 200
                    p.location_name, p.latitude, p.longitude,
                    p.top_category,  cp.naics_code
                FROM pois p
                LEFT JOIN category_parameters cp ON p.top_category = cp.top_category
                WHERE p.latitude  IS NOT NULL
                  AND p.longitude IS NOT NULL
                ORDER BY p.top_category
            """)

        cols     = [c[0] for c in cursor.description]
        pois_out = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()
        return jsonify({"ok": True, "pois": pois_out})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# -------------------------
# Module 9: Nearest Competitors Endpoint
# Returns the top N closest competitors to a candidate location.
# Fixes the "No competitor records returned" issue by returning
# actual competitor names, categories, and distances.
# -------------------------
@app.route("/api/nearest_competitors")
def get_nearest_competitors():
    naics = request.args.get("naics", "").strip()
    lat   = request.args.get("lat",   "").strip()
    lon   = request.args.get("lon",   "").strip()
    n     = request.args.get("n",     "5").strip()

    if not naics or not lat or not lon:
        return jsonify({"ok": False, "error": "Missing naics, lat, or lon"}), 400

    try:
        cand_lat = float(lat)
        cand_lon = float(lon)
        top_n    = max(1, min(int(n), 20))
    except Exception:
        return jsonify({"ok": False, "error": "Invalid lat, lon, or n"}), 400

    try:
        conn   = get_connection()
        cursor = conn.cursor()

        # Pull all POIs for this NAICS code
        cursor.execute("""
            SELECT TOP 200
                p.location_name,
                p.latitude,
                p.longitude,
                p.top_category,
                cp.naics_code
            FROM pois p
            LEFT JOIN category_parameters cp ON p.top_category = cp.top_category
            WHERE cp.naics_code = ?
              AND p.latitude  IS NOT NULL
              AND p.longitude IS NOT NULL
        """, (naics,))

        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()

        # Calculate distance for each POI and sort
        for row in rows:
            try:
                row["distance_km"] = round(
                    haversine_km(cand_lat, cand_lon,
                                 float(row["latitude"]),
                                 float(row["longitude"])), 2
                )
            except Exception:
                row["distance_km"] = None

        rows_with_dist = [r for r in rows if r["distance_km"] is not None]
        rows_with_dist.sort(key=lambda x: x["distance_km"])

        return jsonify({
            "ok":          True,
            "competitors": rows_with_dist[:top_n],
            "total_found": len(rows_with_dist)
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# -------------------------
# Module 9: Category-to-NAICS Resolution Endpoint
# -------------------------
@app.route("/api/resolve_category", methods=["POST"])
def resolve_category():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip().lower()

    if not name:
        return jsonify({"ok": False, "error": "No name provided"}), 400

    if name in NAICS_LOOKUP:
        code = NAICS_LOOKUP[name]
        return jsonify({
            "ok": True, "naics_code": code,
            "category_name": NAICS_NAMES.get(code, code), "matched": True
        })

    sorted_keys = sorted(NAICS_LOOKUP.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key in name or name in key:
            code = NAICS_LOOKUP[key]
            return jsonify({
                "ok": True, "naics_code": code,
                "category_name": NAICS_NAMES.get(code, code), "matched": True
            })

    return jsonify({
        "ok": False, "matched": False,
        "error": f"Could not map '{name}' to a NAICS code."
    })


# -------------------------
# Run Huff Model
# -------------------------
@app.route("/api/run_huff", methods=["POST"])
def api_run_huff():
    try:
        from huff_engine import run_huff_model

        data = request.get_json(silent=True) or {}

        candidate_lat     = get_first_present(data, ["candidate_lat", "lat", "latitude"])
        candidate_lon     = get_first_present(data, ["candidate_lon", "lon", "lng", "longitude"])
        business_category = get_first_present(data, ["business_category", "naics_code", "naics"])
        floor_area        = get_first_present(data, ["floor_area", "floor_area_sqm", "area", "area_sqm"])

        missing = []
        if candidate_lat is None:     missing.append("candidate_lat")
        if candidate_lon is None:     missing.append("candidate_lon")
        if business_category is None: missing.append("business_category or naics_code")
        if floor_area is None:        missing.append("floor_area or floor_area_sqm")

        if missing:
            return jsonify({"ok": False, "error": "Missing required inputs: " + ", ".join(missing)}), 400

        try:
            candidate_lat     = float(candidate_lat)
            candidate_lon     = float(candidate_lon)
            floor_area        = float(floor_area)
            business_category = str(business_category).strip()
        except Exception:
            return jsonify({"ok": False, "error": "Invalid input types."}), 400

        if not business_category:
            return jsonify({"ok": False, "error": "Business category cannot be empty."}), 400
        if candidate_lat < -90 or candidate_lat > 90:
            return jsonify({"ok": False, "error": "candidate_lat must be between -90 and 90."}), 400
        if candidate_lon < -180 or candidate_lon > 180:
            return jsonify({"ok": False, "error": "candidate_lon must be between -180 and 180."}), 400
        if floor_area <= 0:
            return jsonify({"ok": False, "error": "floor_area must be greater than zero."}), 400

        # ── NAICS Validation (professor requirement) ──────────────────
        # Case 3: NAICS code not in POIs data at all → refuse to run
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM pois p
                LEFT JOIN category_parameters cp ON p.top_category = cp.top_category
                WHERE cp.naics_code = ?
                  AND p.latitude  IS NOT NULL
                  AND p.longitude IS NOT NULL
            """, (business_category,))
            poi_count = cursor.fetchone()[0]
            conn.close()
        except Exception:
            poi_count = -1  # DB error — allow model to run, huff_engine handles it

        if poi_count == 0:
            return jsonify({
                "ok": False,
                "error": (
                    f"There are no historical records for NAICS code {business_category} "
                    "in our data, so the model cannot produce results for this business category. "
                    "Please try a different NAICS code or business type."
                )
            }), 400
        # ── End NAICS Validation ───────────────────────────────────────

        result      = run_huff_model(
            candidate_lat=candidate_lat,
            candidate_lon=candidate_lon,
            business_category=business_category,
            floor_area=floor_area,
            db_connection=None
        )
        explanation = generate_explanation(result, business_category, floor_area)

        return jsonify({
            "ok": True,
            "inputs": {
                "candidate_lat":     candidate_lat,
                "candidate_lon":     candidate_lon,
                "business_category": business_category,
                "floor_area":        floor_area
            },
            "result":      result,
            "explanation": explanation
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# -------------------------
# Ask Follow-up Questions
# -------------------------
@app.route("/api/ask", methods=["POST"])
def api_ask():
    try:
        data     = request.get_json(silent=True) or {}
        question = data.get("question")
        result   = data.get("result")

        if not question or not result:
            return jsonify({"ok": False, "error": "Missing question or result"}), 400

        answer = answer_question(question, result)
        return jsonify({"ok": True, "answer": answer})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# -------------------------
# Helper Functions
# -------------------------
def get_first_present(data, keys):
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)
    return None


def safe_competitor_sample(result, n=3):
    competitors = result.get("competitors", [])
    if not isinstance(competitors, list):
        return []
    return competitors[:n]


# -------------------------
# LLM Functions
# -------------------------
DSS_SYSTEM_IDENTITY = """You are a location decision support assistant for Worcester, MA.
You help business owners and analysts evaluate retail store locations using the Huff gravity model.

STRICT RULES:
1. Only answer questions related to: location analysis, NAICS codes, market share, competitors,
   the Huff model, map interpretation, and location decision-making.
2. If asked about unrelated topics, politely decline and redirect to location decision support.
3. NEVER invent, estimate, or guess model results. Only reference data actually returned by the model.
4. Use plain business language. Avoid academic jargon.
5. Keep default responses to 3-5 sentences.
6. Always mention at least one limitation: the model does not account for rent, zoning,
   parking availability, or customer demographics.
7. Do not claim any location is guaranteed to succeed."""


def generate_explanation(result, business_category="", floor_area=0):
    cat_name = NAICS_NAMES.get(str(business_category), f"NAICS {business_category}")

    prompt = f"""
The Huff gravity model was just run for a proposed {cat_name} store ({floor_area} sq meters).

Model results:
- Predicted visits: {result.get("predicted_visits")}
- Market share: {result.get("market_share")} ({round(float(result.get("market_share", 0)) * 100, 2)}%)
- Number of competitors in this category: {result.get("competitors")}
- Runtime: {result.get("runtime_ms")} ms

Write a clear explanation following this structure:
1. State the main result (predicted visits and market share) in plain terms.
2. Explain what these numbers mean for the location decision.
3. Name one specific factor that likely influenced the result.
4. End with one honest limitation (what the model does not include).

Do not use technical jargon. Write for a business owner. Keep it to 3-5 sentences.
"""
    response = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": DSS_SYSTEM_IDENTITY},
            {"role": "user",   "content": prompt}
        ],
        temperature=0.4
    )
    return response.choices[0].message.content


def answer_question(question, result):
    prompt = f"""
Model result data:
{result}

User question:
{question}

Instructions:
- If about model result or location decision-making: answer clearly using only the data above.
- If about an unrelated topic: respond with "I am designed to help with location decision support only."
- Never invent numbers not in the data above.
- Use plain language. Keep to 3-5 sentences.
- Always end with a limitation or next step.
"""
    response = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": DSS_SYSTEM_IDENTITY},
            {"role": "user",   "content": prompt}
        ],
        temperature=0.5
    )
    return response.choices[0].message.content


# -------------------------
# Run locally
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
