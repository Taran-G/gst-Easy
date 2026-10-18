from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from falkordb import FalkorDB
from app.core.config import settings

_db_instance: Optional[FalkorDB] = None

def get_db() -> FalkorDB:
    global _db_instance
    if _db_instance is None:
        _db_instance = FalkorDB(
            host=settings.FALKORDB_HOST,
            port=settings.FALKORDB_PORT,
            password=settings.FALKORDB_PASSWORD or None
        )
    return _db_instance

def tenant_graph(tenant_id: str):
    """Select isolated graph for tenant. Never query across tenant graphs."""
    db = get_db()
    clean_id = str(tenant_id).replace("-", "_")
    return db.select_graph(f"t_{clean_id}")

def firm_graph(firm_id: str):
    """Select firm graph for firm-level metadata, users, tenant routing."""
    db = get_db()
    clean_id = str(firm_id).replace("-", "_")
    return db.select_graph(f"firm_{clean_id}")

_query_cache: Dict[str, str] = {}
QUERIES_DIR = Path(__file__).resolve().parent / "queries"

def load_cypher_template(template_name: str) -> str:
    if not template_name.endswith(".cypher"):
        template_name = f"{template_name}.cypher"
    
    if template_name in _query_cache:
        return _query_cache[template_name]
    
    file_path = QUERIES_DIR / template_name
    if not file_path.exists():
        raise FileNotFoundError(f"Cypher template not found: {template_name} at {file_path}")
    
    with open(file_path, "r", encoding="utf-8") as f:
        cypher = f.read().strip()
        _query_cache[template_name] = cypher
        return cypher

def query(graph, template_name: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Executes a parameterised Cypher template from api/app/graph/queries/*.cypher.
    Returns:
      {
        "rows": List[List[Any]],
        "header": List[str],
        "cypher": str,
        "params": Dict[str, Any]
      }
    """
    cypher_text = load_cypher_template(template_name)
    params = params or {}
    
    res = graph.query(cypher_text, params)
    
    rows = getattr(res, "result_set", []) or []
    header = getattr(res, "header", []) or []
    if header and hasattr(header, "__iter__"):
        header = [str(h) for h in header]
        
    return {
        "rows": rows,
        "header": header,
        "cypher": cypher_text,
        "params": params
    }
