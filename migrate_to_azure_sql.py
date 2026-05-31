# migrate_to_azure_sql.py
# Module 7 - Asynchronous Background Migration Worker
#
# ARCHITECTURE:
#   This script runs inside a background thread (not the main web request)
#   to avoid Azure's 30-second Gunicorn worker timeout and the 230-second
#   proxy gateway timeout. The /admin/migrate endpoint spawns this as a
#   daemon thread and immediately returns 202 to the browser.
#
# TABLES MIGRATED:
#   cbg_master, cbg_geometries, pois, visits, distance_matrix,
#   category_parameters, cbg_category_demand,
#   cbg_category_competitor_utility, Competitor_Summary
#
# SAFETY FEATURES:
#   - DROP TABLE IF EXISTS before each CREATE (safe to run multiple times)
#   - fast_executemany = True for high-speed bulk inserts
#   - Explicit Python primitive casting to avoid pyodbc C-buffer alignment bugs
#   - VARCHAR(50) on key index columns to avoid T-SQL Error 1919

import os
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pyodbc

# =========================
# GLOBAL STATUS TRACKER
# Shared memory readable by /admin/migrate/status endpoint.
# =========================
migration_status = {
    "status":           "idle",
    "migrated_tables":  {},
    "indexing":         "Pending",
    "error":            None
}

# =========================
# CONFIGURATION
# =========================
BASE_DIR   = Path(__file__).resolve().parent
DB_PATH    = BASE_DIR / "Data" / "urban_ai_v2.db"
BATCH_SIZE = 25000

# Tables to migrate in order (parent tables first)
TABLES_TO_MIGRATE = [
    "cbg_master",
    "cbg_geometries",
    "pois",
    "visits",
    "distance_matrix",
    "category_parameters",
    "cbg_category_demand",
    "cbg_category_competitor_utility",
    "Competitor_Summary",
]

# T-SQL schema definitions (TEXT -> VARCHAR, REAL -> FLOAT, INTEGER -> BIGINT)
# Key lookup columns explicitly bounded to VARCHAR(50) to allow B-Tree indexes
# and avoid T-SQL Error 1919 (cannot index VARCHAR(MAX) columns).
TABLE_SCHEMAS = {
    "cbg_master": """
        CREATE TABLE [cbg_master] (
            [cbg]                     VARCHAR(50) PRIMARY KEY,
            [total_population]        BIGINT,
            [median_household_income] FLOAT,
            [median_age]              FLOAT,
            [white_population]        FLOAT,
            [black_population]        FLOAT,
            [asian_population]        FLOAT,
            [hispanic_population]     FLOAT,
            [uni_degree]              FLOAT,
            [income_q]                VARCHAR(50),
            [education_q]             VARCHAR(50),
            [intptlat10]              FLOAT,
            [intptlon10]              FLOAT,
            [x_26919]                 FLOAT,
            [y_26919]                 FLOAT
        )""",
    "cbg_geometries": """
        CREATE TABLE [cbg_geometries] (
            [cbg]          VARCHAR(50) PRIMARY KEY,
            [geometry_wkt] VARCHAR(MAX) NOT NULL
        )""",
    "pois": """
        CREATE TABLE [pois] (
            [placekey]           VARCHAR(50)  PRIMARY KEY,
            [location_name]      VARCHAR(255),
            [top_category]       VARCHAR(255),
            [latitude]           FLOAT,
            [longitude]          FLOAT,
            [poi_cbg]            VARCHAR(50),
            [wkt_area_sq_meters] FLOAT,
            [x_26919]            FLOAT,
            [y_26919]            FLOAT
        )""",
    "visits": """
        CREATE TABLE [visits] (
            [visitor_home_cbg] VARCHAR(50),
            [placekey]         VARCHAR(50),
            [visit_count]      FLOAT
        )""",
    "distance_matrix": """
        CREATE TABLE [distance_matrix] (
            [placekey]   VARCHAR(50),
            [geoid10]    VARCHAR(50),
            [distance_m] FLOAT
        )""",
    "category_parameters": """
        CREATE TABLE [category_parameters] (
            [top_category] VARCHAR(255),
            [naics_code]   VARCHAR(50),
            [alpha]        FLOAT,
            [beta]         FLOAT,
            [correlation]  FLOAT
        )""",
    "cbg_category_demand": """
        CREATE TABLE [cbg_category_demand] (
            [cbg]                   VARCHAR(50),
            [top_category]          VARCHAR(255),
            [total_category_demand] FLOAT
        )""",
    "cbg_category_competitor_utility": """
        CREATE TABLE [cbg_category_competitor_utility] (
            [cbg]                    VARCHAR(50),
            [top_category]           VARCHAR(255),
            [competitor_utility_sum] FLOAT
        )""",
    "Competitor_Summary": """
        CREATE TABLE [Competitor_Summary] (
            [geoid]        VARCHAR(50)  NOT NULL,
            [top_category] VARCHAR(255) NOT NULL,
            [utility_sum]  FLOAT        NOT NULL,
            PRIMARY KEY ([geoid], [top_category])
        )""",
}

INDEXES = [
    "CREATE INDEX idx_pois_cat   ON [pois]([top_category])",
    "CREATE INDEX idx_params     ON [category_parameters]([top_category])",
    "CREATE INDEX idx_naics      ON [category_parameters]([naics_code])",
    "CREATE INDEX idx_demand     ON [cbg_category_demand]([cbg], [top_category])",
    "CREATE INDEX idx_cs_geoid   ON [Competitor_Summary]([geoid])",
    "CREATE INDEX idx_cs_cat     ON [Competitor_Summary]([top_category])",
    "CREATE INDEX idx_dist       ON [distance_matrix]([geoid10], [placekey])",
    "CREATE INDEX idx_visits     ON [visits]([visitor_home_cbg], [placekey])",
]


# =========================
# BACKGROUND WORKER
# Called in a daemon thread from /admin/migrate.
# Never called directly from a web request.
# =========================
def execute_migration_task():
    """
    Module 7 Background Worker.
    Migrates all tables from SQLite to Azure SQL using fast_executemany
    and explicit Python primitive casting for memory-safe bulk inserts.
    Updates migration_status dict so /admin/migrate/status can be polled.
    """
    global migration_status
    migration_status["status"]          = "running"
    migration_status["error"]           = None
    migration_status["migrated_tables"] = {}
    migration_status["indexing"]        = "Pending"

    # Verify SQLite source exists
    if not DB_PATH.exists():
        migration_status["status"] = "failed"
        migration_status["error"]  = f"SQLite database not found: {DB_PATH}"
        return

    # Verify Azure SQL connection string
    azure_conn_str = os.getenv("SQL_CONNECTION_STRING")
    if not azure_conn_str:
        migration_status["status"] = "failed"
        migration_status["error"]  = "SQL_CONNECTION_STRING environment variable is not set."
        return

    sqlite_conn = sqlite3.connect(str(DB_PATH))

    try:
        azure_conn   = pyodbc.connect(azure_conn_str, timeout=60)
        azure_cursor = azure_conn.cursor()
    except Exception as e:
        sqlite_conn.close()
        migration_status["status"] = "failed"
        migration_status["error"]  = f"Azure SQL connection failed: {str(e)}"
        return

    try:
        for table in TABLES_TO_MIGRATE:
            migration_status["migrated_tables"][table] = "Processing..."

            # Read from SQLite
            df = pd.read_sql_query(f'SELECT * FROM "{table}"', sqlite_conn)

            if df.empty:
                migration_status["migrated_tables"][table] = "Skipped (0 rows)"
                continue

            # Replace NaN with None for SQL NULL compatibility
            df = df.replace({np.nan: None})

            # Drop and recreate table in Azure SQL
            azure_cursor.execute(f"IF OBJECT_ID('{table}', 'U') IS NOT NULL DROP TABLE [{table}]")
            azure_conn.commit()
            azure_cursor.execute(TABLE_SCHEMAS[table])
            azure_conn.commit()

            # Build INSERT statement
            columns      = [f"[{c}]" for c in df.columns]
            placeholders = ", ".join(["?"] * len(df.columns))
            insert_sql   = f"INSERT INTO [{table}] ({', '.join(columns)}) VALUES ({placeholders})"

            # CRITICAL: Explicit Python primitive casting.
            # Prevents pyodbc C-buffer alignment faults with mixed types and NaN.
            records = []
            for row in df.values.tolist():
                cleaned = []
                for x in row:
                    if x is None or (isinstance(x, float) and np.isnan(x)):
                        cleaned.append(None)
                    elif isinstance(x, (int, float)):
                        cleaned.append(x)
                    else:
                        cleaned.append(str(x))
                records.append(tuple(cleaned))

            total_rows = len(records)

            # fast_executemany = True switches pyodbc from row-by-row inserts
            # to high-speed C-accelerated array buffers.
            azure_cursor.fast_executemany = True

            for i in range(0, total_rows, BATCH_SIZE):
                azure_cursor.executemany(insert_sql, records[i:i + BATCH_SIZE])
                azure_conn.commit()

            migration_status["migrated_tables"][table] = f"Success ({total_rows:,} rows)"

        # Create performance indexes after all data is loaded
        migration_status["indexing"] = "Compiling indexes..."
        for idx_sql in INDEXES:
            try:
                azure_cursor.execute(idx_sql)
                azure_conn.commit()
            except Exception:
                pass  # Index may already exist

        migration_status["indexing"] = "Indexes applied"
        migration_status["status"]   = "completed"

    except Exception as e:
        migration_status["status"] = "failed"
        migration_status["error"]  = str(e)

    finally:
        sqlite_conn.close()
        try:
            azure_conn.close()
        except Exception:
            pass
