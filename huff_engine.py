# huff_engine.py
# Module 7 - Huff Model Inference Engine (Azure SQL)
#
# KEY CHANGES FROM MODULE 6:
#   - Removed sqlite3 and local DB_PATH entirely.
#   - Imports get_connection from db.py (Azure SQL via SQL_CONNECTION_STRING).
#   - Added _query() helper: wraps pyodbc cursor, returns rows as dicts.
#   - Changed LIMIT 1 to SELECT TOP 1 for T-SQL compatibility.
#   - Replaced pyproj with pure Python UTM projection (_wgs84_to_utm19n).
#   - Point-to-polygon distance logic unchanged (pure Python, 0.14% error).
#   - Function signature unchanged: run_huff_model() same five parameters.

import math
import re
import time

from db import get_connection


# =========================
# AZURE SQL QUERY HELPER
# Returns rows as list of dicts so column name access works the same
# as the previous sqlite3.Row style.
# =========================
def _query(conn, sql: str, params: tuple = None) -> list:
    cursor = conn.cursor()
    if params:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql)
    if cursor.description is None:
        return []
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# =========================
# PURE PYTHON UTM PROJECTION
# WGS84 -> EPSG:26919 (UTM Zone 19N)
# No pyproj needed at runtime on Azure.
# =========================
def _wgs84_to_utm19n(lon_deg: float, lat_deg: float):
    a  = 6378137.0; f = 1/298.257223563; b = a*(1-f)
    e2 = 1-(b/a)**2; k0 = 0.9996
    lon0 = math.radians(-69)
    lat  = math.radians(lat_deg); lon = math.radians(lon_deg)
    N    = a/math.sqrt(1-e2*math.sin(lat)**2)
    T    = math.tan(lat)**2
    C    = e2/(1-e2)*math.cos(lat)**2
    A    = math.cos(lat)*(lon-lon0)
    e4   = e2**2; e6 = e2**3
    M    = a*((1-e2/4-3*e4/64-5*e6/256)*lat
              -(3*e2/8+3*e4/32+45*e6/1024)*math.sin(2*lat)
              +(15*e4/256+45*e6/1024)*math.sin(4*lat)
              -(35*e6/3072)*math.sin(6*lat))
    x = k0*N*(A+(1-T+C)*A**3/6+(5-18*T+T**2+72*C-58*(e2/(1-e2)))*A**5/120)+500000
    y = k0*(M+N*math.tan(lat)*(A**2/2+(5-T+9*C+4*C**2)*A**4/24+
            (61-58*T+T**2+600*C-330*(e2/(1-e2)))*A**6/720))
    return x, y


# =========================
# POINT-TO-POLYGON GEOMETRY
# Pure Python -- matches ground truth CSV to within 0.14%.
# =========================
def _parse_wkt_polygon(wkt: str):
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

def _point_in_ring(px, py, ring):
    inside = False; n = len(ring); j = n-1
    for i in range(n):
        xi,yi = ring[i]; xj,yj = ring[j]
        if ((yi>py)!=(yj>py)) and (px<(xj-xi)*(py-yi)/(yj-yi)+xi):
            inside = not inside
        j = i
    return inside

def _segment_distance(px, py, ax, ay, bx, by):
    dx,dy = bx-ax, by-ay
    if dx==0 and dy==0:
        return math.sqrt((px-ax)**2+(py-ay)**2)
    t = max(0.0, min(1.0, ((px-ax)*dx+(py-ay)*dy)/(dx*dx+dy*dy)))
    return math.sqrt((px-(ax+t*dx))**2+(py-(ay+t*dy))**2)

def point_to_polygon_distance(px: float, py: float, wkt: str) -> float:
    rings = _parse_wkt_polygon(wkt)
    if not rings:
        return float('inf')
    if _point_in_ring(px, py, rings[0]):
        return 0.0
    min_d = float('inf')
    for ring in rings:
        for i in range(len(ring)-1):
            d = _segment_distance(px, py,
                ring[i][0], ring[i][1],
                ring[i+1][0], ring[i+1][1])
            if d < min_d:
                min_d = d
    return min_d


# =========================
# DATABASE QUERIES (T-SQL)
# All use ? placeholders (pyodbc compatible).
# =========================
def lookup_category_and_params(conn, user_input: str) -> dict:
    rows = _query(conn, """
        SELECT TOP 1 top_category, naics_code, alpha, beta, correlation
        FROM   category_parameters
        WHERE  top_category = ? OR naics_code = ?
    """, (user_input, user_input))
    if not rows:
        return {"top_category": user_input, "naics_code": None,
                "alpha": 1.0, "beta": 1.0, "correlation": None,
                "used_fallback": True}
    row = rows[0]
    return {"top_category": row["top_category"], "naics_code": row["naics_code"],
            "alpha": float(row["alpha"]), "beta": float(row["beta"]),
            "correlation": row["correlation"], "used_fallback": False}

def get_cbgs(conn) -> list:
    return _query(conn, """
        SELECT cbg, x_26919, y_26919 FROM cbg_master
        WHERE x_26919 IS NOT NULL AND y_26919 IS NOT NULL
    """)

def get_cbg_geometries(conn) -> dict:
    rows = _query(conn, "SELECT cbg, geometry_wkt FROM cbg_geometries")
    return {str(r["cbg"]).strip(): r["geometry_wkt"] for r in rows}

def get_precomputed_competitor_utilities(conn, top_category: str) -> dict:
    rows = _query(conn, """
        SELECT geoid, utility_sum FROM Competitor_Summary
        WHERE top_category = ?
    """, (top_category,))
    return {str(r["geoid"]).strip(): float(r["utility_sum"]) for r in rows}

def get_category_demand(conn, top_category: str) -> dict:
    rows = _query(conn, """
        SELECT cbg, total_category_demand FROM cbg_category_demand
        WHERE top_category = ?
    """, (top_category,))
    return {str(r["cbg"]).strip(): float(r["total_category_demand"]) for r in rows}

def get_competitor_count(conn, top_category: str) -> int:
    rows = _query(conn, "SELECT COUNT(*) AS cnt FROM pois WHERE top_category = ?",
                  (top_category,))
    return int(rows[0]["cnt"]) if rows else 0


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
    Queries Azure SQL via db.get_connection().
    Returns: predicted_visits, market_share, competitors, runtime_ms, notes.
    """
    start_time = time.perf_counter()

    conn       = db_connection if db_connection is not None else get_connection()
    opened_new = db_connection is None

    params       = lookup_category_and_params(conn, business_category)
    top_category = params["top_category"]
    alpha        = params["alpha"]
    beta         = params["beta"]

    new_x, new_y     = _wgs84_to_utm19n(candidate_lon, candidate_lat)
    cbgs             = get_cbgs(conn)
    cbg_geometries   = get_cbg_geometries(conn)
    utility_lookup   = get_precomputed_competitor_utilities(conn, top_category)
    demand_lookup    = get_category_demand(conn, top_category)
    competitor_count = get_competitor_count(conn, top_category)

    total_predicted_visits = 0.0

    for row in cbgs:
        cbg = str(row["cbg"]).strip()
        wkt = cbg_geometries.get(cbg)
        if wkt:
            d_new = point_to_polygon_distance(new_x, new_y, wkt)
        else:
            d_new = math.sqrt(
                (float(row["x_26919"]) - new_x) ** 2 +
                (float(row["y_26919"]) - new_y) ** 2
            )
        d_new      = max(d_new, 1.0)
        u_new      = (floor_area ** alpha) / (d_new ** beta)
        u_existing = utility_lookup.get(cbg, 0.0)
        denom      = u_new + u_existing
        p_new      = (u_new / denom) if denom > 0 else 0.0
        total_predicted_visits += p_new * demand_lookup.get(cbg, 0.0)

    if opened_new:
        conn.close()

    runtime_ms       = (time.perf_counter() - start_time) * 1000
    total_demand_all = sum(demand_lookup.values())
    market_share     = (total_predicted_visits / total_demand_all
                        if total_demand_all > 0 else 0.0)

    return {
        "predicted_visits": round(total_predicted_visits, 2),
        "market_share":     round(market_share, 4),
        "competitors":      competitor_count,
        "runtime_ms":       round(runtime_ms, 3),
        "notes":            "fallback parameters used" if params["used_fallback"] else "",
    }
