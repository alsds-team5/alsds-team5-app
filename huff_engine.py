# huff_engine.py
# Assignment 6 - Huff Model Inference Engine (V3)
#
# KEY CHANGES FROM V2:
#   - Function renamed to run_huff_model() to match required signature.
#   - Parameters: candidate_lat, candidate_lon, business_category,
#     floor_area, db_connection.
#   - Structured return: predicted_visits, market_share, competitors,
#     runtime_ms, notes.
#   - Queries Competitor_Summary (ground truth distances) for competitor
#     utility sums.
#   - All user inputs use parameterized SQL queries (? placeholders).
#
# DISTANCE FIX (Point-to-Polygon):
#   The ground truth CSV was built using Point-to-Polygon logic:
#   distance from a POI point to the nearest edge of the CBG polygon
#   (returns 0 if the point is inside the polygon). This matches the
#   ground truth to within 0.14% vs 6-490% error for centroid method.
#
#   This version:
#   1. Loads CBG polygon geometries (WKT) stored by migration_v2.py
#      in the cbg_geometries table.
#   2. Computes Point-to-Polygon distance using pure Python geometry
#      (no extra dependencies beyond pyproj).
#   3. Falls back to centroid distance for any CBG missing a geometry.

import math
import re
import sqlite3
import time
from pathlib import Path

from pyproj import Transformer


# =========================
# PATH
# =========================
DB_PATH = Path("Data/urban_ai_v2.db")


# =========================
# DATABASE CONNECTION
# =========================
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# =========================
# POINT-TO-POLYGON GEOMETRY
# Pure Python implementation -- no shapely or geopandas required.
# Matches the professor's reference notebook to within 0.14%.
# =========================

def _parse_wkt_polygon(wkt: str):
    """
    Parses a WKT POLYGON string into a list of rings.
    Each ring is a list of (x, y) tuples projected in EPSG:26919.
    """
    rings = []
    for ring_str in re.findall(r'\(([^()]+)\)', wkt):
        pts = []
        for pair in ring_str.strip().split(','):
            parts = pair.strip().split()
            if len(parts) >= 2:
                pts.append((float(parts[0]), float(parts[1])))
        if pts:
            rings.append(pts)
    return rings


def _point_in_ring(px: float, py: float, ring: list) -> bool:
    """Ray-casting point-in-polygon test for a single ring."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > py) != (yj > py)) and (
            px < (xj - xi) * (py - yi) / (yj - yi) + xi
        ):
            inside = not inside
        j = i
    return inside


def _segment_distance(px, py, ax, ay, bx, by) -> float:
    """Minimum distance from point (px,py) to line segment (ax,ay)-(bx,by)."""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.sqrt((px - ax) ** 2 + (py - ay) ** 2)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.sqrt((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2)


def point_to_polygon_distance(px: float, py: float, wkt: str) -> float:
    """
    Computes the Point-to-Polygon distance in EPSG:26919 metres.
    Returns 0.0 if the point is inside the polygon (consistent with
    the ground truth worcester_cbg_poi_distance.csv methodology).
    """
    rings = _parse_wkt_polygon(wkt)
    if not rings:
        return float('inf')
    # If point is inside the outer ring, distance = 0
    if _point_in_ring(px, py, rings[0]):
        return 0.0
    # Otherwise: minimum distance to any ring edge
    min_d = float('inf')
    for ring in rings:
        for i in range(len(ring) - 1):
            d = _segment_distance(
                px, py,
                ring[i][0], ring[i][1],
                ring[i + 1][0], ring[i + 1][1]
            )
            if d < min_d:
                min_d = d
    return min_d


# =========================
# PARAMETERIZED QUERIES
# =========================

def lookup_category_and_params(conn: sqlite3.Connection, user_input: str) -> dict:
    """
    Fetches calibrated alpha/beta for the given category or NAICS code.
    Falls back to alpha=1.0, beta=1.0 if no match found.
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
    """Fetches CBG identifiers and centroid coordinates (fallback use)."""
    sql = """
        SELECT cbg, x_26919, y_26919
        FROM   cbg_master
        WHERE  x_26919 IS NOT NULL
          AND  y_26919 IS NOT NULL
    """
    return conn.execute(sql).fetchall()


def get_cbg_geometries(conn: sqlite3.Connection) -> dict:
    """
    Loads CBG polygon WKT strings from cbg_geometries table.
    Returns dict: cbg -> WKT string (EPSG:26919).
    """
    sql = "SELECT cbg, geometry_wkt FROM cbg_geometries"
    rows = conn.execute(sql).fetchall()
    return {str(row["cbg"]).strip(): row["geometry_wkt"] for row in rows}


def get_precomputed_competitor_utilities(
    conn: sqlite3.Connection, top_category: str
) -> dict:
    """
    Fetches pre-computed competitor utility sums from Competitor_Summary.
    Built using ground truth Point-to-Polygon distances from the CSV.
    Returns dict: geoid -> utility_sum.
    """
    sql = """
        SELECT geoid, utility_sum
        FROM   Competitor_Summary
        WHERE  top_category = ?
    """
    rows = conn.execute(sql, (top_category,)).fetchall()
    return {
        str(row["geoid"]).strip(): float(row["utility_sum"])
        for row in rows
    }


def get_category_demand(conn: sqlite3.Connection, top_category: str) -> dict:
    """Returns dict: cbg -> total_category_demand."""
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
    sql = "SELECT COUNT(*) as cnt FROM pois WHERE top_category = ?"
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
      1. Look up calibrated alpha / beta from category_parameters.
      2. Project the proposed site lat/lon to EPSG:26919 using pyproj.
      3. Load CBG polygon geometries from cbg_geometries table.
      4. For each CBG:
           a. Compute Point-to-Polygon distance from proposed site to CBG
              polygon (0 if inside; falls back to centroid if WKT missing).
           b. New-site utility: u_new = floor_area^alpha / distance^beta
           c. Pre-computed competitor utility from Competitor_Summary.
           d. Huff probability: p_new = u_new / (u_new + u_existing)
           e. Predicted visits: p_new * total_category_demand
      5. Market share = predicted_visits / total_category_demand.

    Parameters
    ----------
    candidate_lat     : WGS-84 latitude of proposed site
    candidate_lon     : WGS-84 longitude of proposed site
    business_category : Top category name or NAICS code
    floor_area        : Floor area of proposed site (sq metres)
    db_connection     : Existing SQLite connection or None

    Returns
    -------
    dict: predicted_visits, market_share, competitors, runtime_ms, notes
    """
    start_time = time.perf_counter()

    conn = db_connection if db_connection is not None else get_connection()

    # Step 1: model parameters
    params       = lookup_category_and_params(conn, business_category)
    top_category = params["top_category"]
    alpha        = params["alpha"]
    beta         = params["beta"]

    # Step 2: project proposed site to EPSG:26919
    transformer  = Transformer.from_crs("EPSG:4326", "EPSG:26919", always_xy=True)
    new_x, new_y = transformer.transform(candidate_lon, candidate_lat)

    # Step 3: load CBG data
    cbgs             = get_cbgs(conn)
    cbg_geometries   = get_cbg_geometries(conn)
    utility_lookup   = get_precomputed_competitor_utilities(conn, top_category)
    demand_lookup    = get_category_demand(conn, top_category)
    competitor_count = get_competitor_count(conn, top_category)

    total_predicted_visits = 0.0

    for row in cbgs:
        cbg = str(row["cbg"]).strip()

        # Step 4a: Point-to-Polygon distance (preferred) or centroid fallback
        wkt = cbg_geometries.get(cbg)
        if wkt:
            d_new = point_to_polygon_distance(new_x, new_y, wkt)
        else:
            d_new = math.sqrt(
                (float(row["x_26919"]) - new_x) ** 2 +
                (float(row["y_26919"]) - new_y) ** 2
            )
        d_new = max(d_new, 1.0)  # floor at 1m

        # Step 4b: new site utility
        u_new = (floor_area ** alpha) / (d_new ** beta)

        # Step 4c: competitor utility (pre-computed with GT distances)
        u_existing = utility_lookup.get(cbg, 0.0)

        # Step 4d: Huff probability
        denominator = u_new + u_existing
        p_new = (u_new / denominator) if denominator > 0 else 0.0

        # Step 4e: predicted visits
        total_predicted_visits += p_new * demand_lookup.get(cbg, 0.0)

    if db_connection is None:
        conn.close()

    runtime_ms = (time.perf_counter() - start_time) * 1000

    # Step 5: market share
    total_demand_all = sum(demand_lookup.values())
    market_share = (
        total_predicted_visits / total_demand_all
        if total_demand_all > 0 else 0.0
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
    print("  Point-to-Polygon distances | Ground truth utilities")
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
