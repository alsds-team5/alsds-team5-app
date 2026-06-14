import os
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
# Maps plain business names to NAICS codes in our database.
# Only includes codes that exist in category_parameters table.
# -------------------------
NAICS_LOOKUP = {
    # Building Material / Hardware
    "hardware store":         "4441",
    "hardware":               "4441",
    "home improvement":       "4441",
    "building materials":     "4441",
    "lumber store":           "4441",
    "home depot":             "4441",
    "lowes":                  "4441",
    "lowe's":                 "4441",

    # Beer / Wine / Liquor
    "liquor store":           "445310",
    "wine store":             "445310",
    "beer store":             "445310",
    "beer wine liquor":       "445310",
    "alcohol store":          "445310",

    # Auto Parts
    "auto parts":             "441310",
    "car parts":              "441310",
    "tire store":             "441310",
    "automotive parts":       "441310",

    # Gas Station
    "gas station":            "447110",
    "petrol station":         "447110",
    "fuel station":           "447110",
    "gas":                    "447110",

    # Jewelry
    "jewelry store":          "448310",
    "jewelry":                "448310",
    "luggage store":          "448310",

    # General Merchandise
    "general store":          "452319",
    "warehouse store":        "452319",
    "department store":       "452319",
    "superstore":             "452319",
    "walmart":                "452319",
    "costco":                 "452319",
    "target":                 "452319",

    # Bakery
    "bakery":                 "311811",
    "bread store":            "311811",
    "pastry shop":            "311811",

    # Bank / Financial
    "bank":                   "522110",
    "credit union":           "522110",
    "financial services":     "522310",
    "investment office":      "523930",
    "insurance office":       "524113",
    "insurance":              "524113",

    # Real Estate
    "real estate office":     "531210",
    "real estate agent":      "531210",
    "property rental":        "531120",
    "rental office":          "531120",

    # Education
    "college":                "611310",
    "university":             "611310",
    "school":                 "611310",

    # Healthcare
    "dentist":                "621210",
    "dental office":          "621210",
    "clinic":                 "6214",
    "urgent care":            "6214",
    "outpatient clinic":      "6214",
    "medical lab":            "621511",
    "diagnostic lab":         "621511",

    # Personal Services
    "salon":                  "812910",
    "spa":                    "812910",
    "personal services":      "812910",
    "nail salon":             "812910",
    "barber":                 "812910",

    # Telecom
    "phone store":            "517312",
    "telecom store":          "517312",
    "wireless store":         "517312",
    "mobile store":           "517312",
}

# Human-readable names for confirmed NAICS codes
NAICS_NAMES = {
    "4441":   "Building Material and Supplies Dealers",
    "445310": "Beer, Wine, and Liquor Stores",
    "441310": "Automotive Parts, Accessories, and Tire Stores",
    "447110": "Gasoline Stations",
    "448310": "Jewelry, Luggage, and Leather Goods Stores",
    "452319": "General Merchandise Stores",
    "311811": "Bakeries and Tortilla Manufacturing",
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
# Serves POI locations from Azure SQL so the map does not
# rely on static GeoJSON files stored in GitHub.
# -------------------------
@app.route("/api/pois")
def get_pois():
    """
    Returns POI data from Azure SQL for map display.
    Optional query params:
      ?naics=4441       filter by NAICS code
      ?category=...     filter by top_category name
    Returns up to 200 rows with name, lat, lon, category.
    """
    naics    = request.args.get("naics", "").strip()
    category = request.args.get("category", "").strip()

    try:
        conn   = get_connection()
        cursor = conn.cursor()

        if naics:
            cursor.execute("""
                SELECT TOP 200
                    p.location_name,
                    p.latitude,
                    p.longitude,
                    p.top_category,
                    cp.naics_code
                FROM pois p
                LEFT JOIN category_parameters cp
                       ON p.top_category = cp.top_category
                WHERE cp.naics_code = ?
                  AND p.latitude  IS NOT NULL
                  AND p.longitude IS NOT NULL
            """, (naics,))
        elif category:
            cursor.execute("""
                SELECT TOP 200
                    p.location_name,
                    p.latitude,
                    p.longitude,
                    p.top_category,
                    cp.naics_code
                FROM pois p
                LEFT JOIN category_parameters cp
                       ON p.top_category = cp.top_category
                WHERE p.top_category = ?
                  AND p.latitude  IS NOT NULL
                  AND p.longitude IS NOT NULL
            """, (category,))
        else:
            cursor.execute("""
                SELECT TOP 200
                    p.location_name,
                    p.latitude,
                    p.longitude,
                    p.top_category,
                    cp.naics_code
                FROM pois p
                LEFT JOIN category_parameters cp
                       ON p.top_category = cp.top_category
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
# Module 9: Category-to-NAICS Resolution Endpoint
# Accepts a plain business name and returns the matching NAICS code.
# -------------------------
@app.route("/api/resolve_category", methods=["POST"])
def resolve_category():
    """
    Maps a plain business name to a NAICS code.
    Body: { "name": "hardware store" }
    Returns: { "ok": true, "naics_code": "4441", "category_name": "..." }
    """
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip().lower()

    if not name:
        return jsonify({"ok": False, "error": "No name provided"}), 400

    # Exact match
    if name in NAICS_LOOKUP:
        code = NAICS_LOOKUP[name]
        return jsonify({
            "ok":            True,
            "naics_code":    code,
            "category_name": NAICS_NAMES.get(code, code),
            "matched":       True
        })

    # Partial match (longest key wins)
    sorted_keys = sorted(NAICS_LOOKUP.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key in name or name in key:
            code = NAICS_LOOKUP[key]
            return jsonify({
                "ok":            True,
                "naics_code":    code,
                "category_name": NAICS_NAMES.get(code, code),
                "matched":       True
            })

    return jsonify({
        "ok":      False,
        "matched": False,
        "error":   f"Could not map '{name}' to a NAICS code. Please provide a numeric NAICS code."
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
        if candidate_lat is None:
            missing.append("candidate_lat")
        if candidate_lon is None:
            missing.append("candidate_lon")
        if business_category is None:
            missing.append("business_category or naics_code")
        if floor_area is None:
            missing.append("floor_area or floor_area_sqm")

        if missing:
            return jsonify({
                "ok":    False,
                "error": "Missing required inputs: " + ", ".join(missing)
            }), 400

        try:
            candidate_lat     = float(candidate_lat)
            candidate_lon     = float(candidate_lon)
            floor_area        = float(floor_area)
            business_category = str(business_category).strip()
        except Exception:
            return jsonify({
                "ok":    False,
                "error": "Invalid input type. Latitude, longitude, and floor area must be numeric."
            }), 400

        if not business_category:
            return jsonify({"ok": False, "error": "Business category / NAICS code cannot be empty."}), 400

        if candidate_lat < -90 or candidate_lat > 90:
            return jsonify({"ok": False, "error": "candidate_lat must be between -90 and 90."}), 400

        if candidate_lon < -180 or candidate_lon > 180:
            return jsonify({"ok": False, "error": "candidate_lon must be between -180 and 180."}), 400

        if floor_area <= 0:
            return jsonify({"ok": False, "error": "floor_area must be greater than zero."}), 400

        result = run_huff_model(
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
# Module 9: Updated system prompts for plain language and topic control
# -------------------------

# Shared system identity for all prompts
DSS_SYSTEM_IDENTITY = """You are a location decision support assistant for Worcester, MA.
You help business owners and analysts evaluate retail store locations using the Huff gravity model.

STRICT RULES:
1. Only answer questions related to: location analysis, NAICS codes, market share, competitors, 
   the Huff model, map interpretation, and location decision-making.
2. If asked about unrelated topics (essays, personal advice, general coding, history, etc.), 
   politely decline and redirect to location decision support.
3. NEVER invent, estimate, or guess model results. Only reference data actually returned by the model.
4. Use plain business language. Avoid academic jargon like "spatial interaction dynamics" or 
   "distance-decay functions". Speak as if explaining to a business owner, not a researcher.
5. Keep default responses to 3-5 sentences.
6. Always mention at least one limitation: the model does not account for rent, zoning, 
   parking availability, or customer demographics.
7. Do not claim any location is guaranteed to succeed.
8. When comparing locations, state clearly which performs better and why, using specific numbers."""


def generate_explanation(result, business_category="", floor_area=0):
    """
    Generates a plain-language explanation of Huff model results.
    Updated for Module 9: clearer structure, no jargon, honest limitations.
    """
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

Do not use technical jargon. Write for a business owner making a location decision.
Keep it to 3-5 sentences.
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
    """
    Answers follow-up questions about model results.
    Updated for Module 9: topic control, no hallucination, plain language.
    """
    prompt = f"""
Model result data provided to you:
{result}

User question:
{question}

Instructions:
- If this question is about the model result, location comparison, NAICS codes, 
  or location decision-making: answer it clearly using only the data provided above.
- If this question is about an unrelated topic (essays, coding, personal advice, etc.):
  respond with: "I am designed to help with location decision support only. 
  I can help you run or compare store location scenarios. Would you like to try a new location?"
- Never invent numbers or results not present in the data above.
- If comparing multiple scenarios, reference specific metrics from each.
- Use plain language. Keep response to 3-5 sentences.
- Always end with a limitation or next step when discussing model results.
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
