"""Replace the Part 3 Step-1 cell: use a Unity Catalog SQL UDF (which can read a
table) instead of a Python UDF (which runs sandboxed with no Spark/creds).
Delete after running."""
import json, pathlib
p = pathlib.Path("modules/07_sandboxes_and_databricks.ipynb")
nb = json.loads(p.read_text())

def src(c): return "".join(c["source"])
def setsrc(c, t): c["source"] = t.splitlines(keepends=True)

# Locate the Step-1 cell by a stable unique marker.
target = None
for c in nb["cells"]:
    if c["cell_type"] == "code" and "Step 1: make sure there's a store_inventory" in src(c):
        target = c
        break
if target is None:
    raise SystemExit("Step-1 cell not found")

setsrc(target, r'''# --- Step 1: seed a store_inventory Delta table, then register a Unity Catalog
# SQL FUNCTION that reads it. Governance (grants, audit, lineage) applies to the
# UC function, and any agent/dashboard can reuse it. Guarded so the notebook
# runs offline.
#
# IMPORTANT: this is a SQL UDF, not a Python UDF. A UC *Python* UDF runs in a
# sandbox with no Spark session and no ambient credentials, so it CANNOT query
# another table (you'd hit "cannot configure default credentials"). A SQL UDF
# executes as SQL on the warehouse and can read the table directly.
from agents.research_agent import STORE_CATALOG

DBX_INV_TABLE = os.environ.get("DATABRICKS_INVENTORY_TABLE", "store_inventory")
DBX_INV_FQN = _fqn(DBX_CATALOG, DBX_SCHEMA, DBX_INV_TABLE)
DBX_INV_FUNC = os.environ.get("DATABRICKS_INVENTORY_FUNCTION", "inventory_lookup")
UC_FUNC_FQN = _fqn(DBX_CATALOG, DBX_SCHEMA, DBX_INV_FUNC)

uc_client = None
uc_ready = False
if databricks_configured:
    try:
        rows = [(k, v["aisle"], bool(v["in_stock"]), float(v["price"]))
                for k, v in STORE_CATALOG.items()]
        with databricks_connection() as conn, conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {DBX_CATALOG}.{DBX_SCHEMA}")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {DBX_INV_FQN} (
                    item STRING, aisle STRING, in_stock BOOLEAN, price DOUBLE
                )
            """)
            cur.execute(f"DELETE FROM {DBX_INV_FQN}")
            cur.executemany(
                f"INSERT INTO {DBX_INV_FQN} (item, aisle, in_stock, price) VALUES (?, ?, ?, ?)",
                rows,
            )
            print(f"Seeded {len(rows)} rows into {DBX_INV_FQN}")

            # SQL UDF. The parameter is named `lookup_item` (distinct from the
            # table column `item`) so the WHERE clause is unambiguous. Returns a
            # single formatted line, or a "not found" message via COALESCE.
            cur.execute(f"""
                CREATE OR REPLACE FUNCTION {UC_FUNC_FQN}(lookup_item STRING)
                RETURNS STRING
                COMMENT 'Look up a grocery item aisle, live stock status, and price.'
                RETURN COALESCE(
                    (SELECT concat(
                        t.item, ': aisle ', t.aisle, ', ',
                        CASE WHEN t.in_stock THEN 'in stock' ELSE 'OUT OF STOCK' END,
                        ', $', format_number(t.price, 2))
                     FROM {DBX_INV_FQN} AS t
                     WHERE lower(t.item) = lower(lookup_item)
                     LIMIT 1),
                    concat(lookup_item, ' not found in store inventory.')
                )
            """)
            print("Registered UC SQL function:", UC_FUNC_FQN)

        # The toolkit will load this already-registered UC function by name.
        from unitycatalog.ai.core.databricks import DatabricksFunctionClient
        uc_client = DatabricksFunctionClient()
        uc_ready = True
    except Exception as e:
        print(f"Could not register the UC function ({type(e).__name__}: {e}).")
        print("Falling back to the local tool below.")
else:
    print("Databricks not configured — Part 3 will use a local fallback tool.")''')

p.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n")
print("Step-1 cell rewritten as a SQL UDF")
