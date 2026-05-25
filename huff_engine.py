# huff_engine_v3.py
# Assignment 6 - Huff Model Inference Engine (V3)
#
# KEY CHANGES FROM V2 (huff_engine_v2.py):
#   - Function renamed to run_huff_model() to match required signature.
#   - Parameters renamed: candidate_lat, candidate_lon, business_category,
#     floor_area, db_connection.
#   - db_connection parameter added: accepts an existing SQLite connection
#     or opens a new one if none is provided.
#   - Structured return: now returns predicted_visits, market_share,
#     competitors, runtime_ms, and notes.
#   - Queries the cbg_category_competitor_utility table for pre-computed
#     competitor utility sums.
#   - All user inputs use parameterized SQL queries (? placeholders).
#   - Updated to use a relative database path for GitHub compatibility.
#     Database must be located at: Data/urban_ai_v2.db
#
# BUG FIXES (V3 corrected):
#   - Fixed table name: was querying non-existent "Competitor_Summary";
#     now correctly queries "cbg_category_competitor_utility" with column
#     "competitor_utility_sum". The wrong table caused u_existing = 0 for
#     every CBG, making p_new = 1.0 always and massively inflating results.
#   - Fixed market_share calculation: was averaging p_new across all CBGs
#     (including zero-demand ones), which is not meaningful. Now calculated
#     as predicted_visits / total_category_demand, which is the correct
#     definition of market share.
#
# NOTE:
#   Predicted visit counts may differ slightly from the V1 CSV-based engine
#   because competitor utilities are pre-computed using projected EPSG:26919
#   coordinates rather than the provided distance matrix CSV.

import math
import sqlite3
import time
from pathlib import Path

from pyproj import Transformer


# =========================
# PATH
# Relative path for GitHub compatibility.
# The database file must be placed in the /Data/ folder of the repository.
# Do NOT use absolute paths (e.g. /content/drive/... or C:/Users/...).
# =========================
DB_PATH = Path("Data/urban_ai_v2.db")


# =========================
# DATABASE CONNECTION
# =========================
def get_connection() -> sqlite3.Connection:
    """
    Opens a connection to the SQLite database using a relative path.
    Row factory is set so columns can be accessed by name.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# =========================
# PARAMETERIZED QUERIES
# All SQL below uses ? placeholders — never f-strings or % formatting.
# This satisfies the security requirement for all user inputs.
# =========================

def lookup_category_and_params(conn: sqlite3.Connection, user_input: str) -> dict:
    """
    Fetches calibrated alpha/beta parameters for the given category or
    NAICS code. Uses parameterized query for both lookup fields.
    Falls back to alpha=1.0, beta=1.0 if no match is found.
    """
    sql = """
        SELECT top_category, naics_code, alpha, beta, correlation
        FROM   category_parameters
        WHERE  top_category = ?
           OR  naics_code   = ?
        LIMIT 1
    """
    row = conn.execute(sql, (user_input, user_input)).fetchone()

    if row is None:
        return {
            "top_category":  user_input,
            "naics_code":    None,
            "alpha":         1.0,
            "beta":          1.0,
            "correlation":   None,
            "used_fallback": True,
        }

    return {
        "top_category":  row["top_category"],
        "naics_code":    row["naics_code"],
        "alpha":         float(row["alpha"]),
        "beta":          float(row["beta"]),
        "correlation":   row["correlation"],
        "used_fallback": False,
    }


def get_cbgs(conn: sqlite3.Connection):
    """
    Fetches all CBG identifiers and their EPSG:26919 projected coordinates
    from the enriched cbg_master table. No user input -> no parameters needed.
    """
    sql = """
        SELECT cbg, x_26919, y_26919
        FROM   cbg_master
        WHERE  x_26919 IS NOT NULL
          AND  y_26919 IS NOT NULL
    """
    return conn.execute(sql).fetchall()


def get_precomputed_competitor_utilities(
    conn: sqlite3.Connection, top_category: str
) -> dict:
    """
    Fetches the pre-computed competitor utility sums from the
    cbg_category_competitor_utility table (built by migration_script.py).
    Returns a dict mapping cbg (str) -> competitor_utility_sum (float).
    Uses a parameterized query: top_category is a ? placeholder.

    NOTE: The previous version queried a table called "Competitor_Summary"
    which does not exist in the database. This caused every CBG to fall back
    to u_existing = 0.0, making p_new = 1.0 for all CBGs and producing
    wildly inflated predicted visit counts.
    """
    sql = """
        SELECT cbg, competitor_utility_sum
        FROM   cbg_category_competitor_utility
        WHERE  top_category = ?
    """
    rows = conn.execute(sql, (top_category,)).fetchall()
    return {
        str(row["cbg"]).strip(): float(row["competitor_utility_sum"])
        for row in rows
    }


def get_category_demand(conn: sqlite3.Connection, top_category: str) -> dict:
    """
    Fetches total observed visit demand per CBG for the given category.
    Uses a parameterized query: top_category is a ? placeholder.
    Returns a dict mapping cbg (str) -> total_category_demand (float).
    """
    sql = """
        SELECT cbg, total_category_demand
        FROM   cbg_category_demand
        WHERE  top_category = ?
    """
    rows = conn.execute(sql, (top_category,)).fetchall()
    return {
        str(row["cbg"]).strip(): float(row["total_category_demand"])
        for row in rows
    }


def get_competitor_count(conn: sqlite3.Connection, top_category: str) -> int:
    """
    Returns the number of existing competitor POIs for the given category.
    Used to populate the 'competitors' field in the structured result.
    """
    sql = """
        SELECT COUNT(*) as cnt
        FROM   pois
        WHERE  top_category = ?
    """
    row = conn.execute(sql, (top_category,)).fetchone()
    return int(row["cnt"]) if row else 0


# =========================
# HUFF MODEL PREDICTION
# =========================
def run_huff_model(
    candidate_lat:     float,
    candidate_lon:     float,
    business_category: str,
    floor_area:        float,
    db_connection=None
) -> dict:
    """
    Runs the Huff gravity model for a proposed new business location.

    Steps:
      1. Look up calibrated alpha / beta from the database.
      2. Project the user-supplied lat/lon to EPSG:26919.
      3. For each CBG:
           a. Compute new-site utility  u_new = floor_area^alpha / distance^beta
           b. Fetch pre-computed competitor utility sum from
              cbg_category_competitor_utility
           c. Huff probability  p_new = u_new / (u_new + u_existing)
           d. Predicted visits  = p_new x total_category_demand
      4. Sum predicted visits across all CBGs.
      5. Market share = predicted_visits / total_category_demand (correct
         definition: what fraction of all category demand goes to new site).

    Parameters
    ----------
    candidate_lat     : float    -- WGS-84 latitude of the proposed site
    candidate_lon     : float    -- WGS-84 longitude of the proposed site
    business_category : str      -- Top category name or NAICS code
    floor_area        : float    -- Floor area of the proposed site (sq metres)
    db_connection     : optional -- Pass an existing SQLite connection, or
                        leave as None to open a new one automatically.

    Returns
    -------
    dict with keys:
        predicted_visits : float -- Total predicted visits from all CBGs
        market_share     : float -- predicted_visits / total_category_demand
        competitors      : int   -- Number of existing competitor POIs
        runtime_ms       : float -- Total execution time in milliseconds
        notes            : str   -- Any warnings (e.g. fallback parameters used)
    """

    start_time = time.perf_counter()

    # Use provided connection or open a new one
    if db_connection is not None:
        conn = db_connection
    else:
        conn = get_connection()

    # --- Step 1: Fetch model parameters ---
    params       = lookup_category_and_params(conn, business_category)
    top_category = params["top_category"]
    alpha        = params["alpha"]
    beta         = params["beta"]

    # --- Step 2: Project proposed site to EPSG:26919 ---
    transformer  = Transformer.from_crs("EPSG:4326", "EPSG:26919", always_xy=True)
    new_x, new_y = transformer.transform(candidate_lon, candidate_lat)

    # --- Step 3: Load CBG data ---
    cbgs           = get_cbgs(conn)
    utility_lookup = get_precomputed_competitor_utilities(conn, top_category)
    demand_lookup  = get_category_demand(conn, top_category)
    competitor_count = get_competitor_count(conn, top_category)

    total_predicted_visits = 0.0

    for row in cbgs:
        cbg = str(row["cbg"]).strip()
        x   = float(row["x_26919"])
        y   = float(row["y_26919"])

        # Distance from CBG centroid to proposed site (metres)
        d_new = math.sqrt((x - new_x) ** 2 + (y - new_y) ** 2)
        d_new = max(d_new, 1.0)  # floor at 1 m to avoid division by zero

        # Utility of the proposed new site
        u_new = (floor_area ** alpha) / (d_new ** beta)

        # Pre-computed sum of all existing competitor utilities for this CBG
        u_existing = utility_lookup.get(cbg, 0.0)

        # Huff probability
        denominator = u_new + u_existing
        p_new = (u_new / denominator) if denominator > 0 else 0.0

        total_demand           = demand_lookup.get(cbg, 0.0)
        total_predicted_visits += p_new * total_demand

    # Only close the connection if we opened it ourselves
    if db_connection is None:
        conn.close()

    runtime_ms = (time.perf_counter() - start_time) * 1000

    # --- Market share: predicted visits as a fraction of total category demand ---
    # FIX: previously this averaged p_new across all CBGs, which is not a
    # meaningful measure. The correct definition is what share of total
    # observed category demand is captured by the new site.
    total_demand_all = sum(demand_lookup.values())
    market_share = (
        total_predicted_visits / total_demand_all
        if total_demand_all > 0
        else 0.0
    )

notes = "fallback parameters used" if params["used_fallback"] else ""

    return {
        "predicted_visits": round(total_predicted_visits, 2),
        "market_share":     round(market_share, 4),
        "competitors":      competitor_count,
        "runtime_ms":       round(runtime_ms, 3),
        "notes":            notes,
    }


# =========================
# MAIN  --  CLI entry point
# =========================
def main():
    print("\n" + "=" * 55)
    print("  Huff Model V3 Inference Engine")
    print("  Database-only | Pre-computed utilities | Secure SQL")
    print("=" * 55 + "\n")

    candidate_lat     = float(input("Enter latitude  (e.g., 42.27):  ").strip())
    candidate_lon     = float(input("Enter longitude (e.g., -71.80): ").strip())
    business_category = input("Enter Top Category or NAICS code:  ").strip()
    floor_area        = float(input("Enter store size (sq metres):    ").strip())

    result = run_huff_model(candidate_lat, candidate_lon, business_category, floor_area)

    print("\n" + "=" * 55)
    print("  RESULTS")
    print("=" * 55)
    print(f"  Predicted Visits  : {result['predicted_visits']:,.2f}")
    print(f"  Market Share      : {result['market_share']:.4f}  ({result['market_share']*100:.2f}%)")
    print(f"  Competitors       : {result['competitors']}")
    print(f"  Runtime           : {result['runtime_ms']:.3f} ms")
    print(f"  Notes             : {result['notes'] if result['notes'] else 'None'}")
    print("=" * 55 + "\n")

    return result


if __name__ == "__main__":
    main()
