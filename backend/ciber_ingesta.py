"""
Ingesta SIEM en vivo (Elemento de Ciberseguridad) — 100% local/soberano.

Dos modos reales por empresa (el operador controla el endpoint, no la nube):
  - Webhook (push): el nodo SIEM/IAM del cliente hace POST de eventos → se
    almacenan en un buffer local por dominio (JSON-lines en disco).
  - Poll (pull): el backend hace un GET saliente al endpoint del cliente
    (Nivel 1) con urllib (stdlib) y agrega los eventos al mismo buffer.

El buffer alimenta a las herramientas (Modo 1 / Modo 2) con fuente="ingesta_live".
"""

import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, List, Optional

BASE = Path(__file__).resolve().parent
BUFFER_DIR = BASE / "flujo" / "ciber_ingesta"


def _buf_path(domain_id: str) -> Path:
    BUFFER_DIR.mkdir(parents=True, exist_ok=True)
    return BUFFER_DIR / f"{domain_id}.jsonl"


def agregar_eventos(domain_id: str, eventos: Any, fuente: str = "webhook") -> int:
    if isinstance(eventos, dict):
        eventos = [eventos]
    if not isinstance(eventos, list):
        return 0
    recibido = datetime.now(timezone.utc).isoformat()
    p = _buf_path(domain_id)
    n = 0
    with open(p, "a", encoding="utf-8") as f:
        for ev in eventos:
            f.write(json.dumps({"_recibido": recibido, "_fuente": fuente, "evento": ev},
                               ensure_ascii=False) + "\n")
            n += 1
    return n


def leer_buffer(domain_id: str, limit: Optional[int] = None) -> List[dict]:
    p = _buf_path(domain_id)
    if not p.exists():
        return []
    lineas = [l for l in p.read_text(encoding="utf-8").split("\n") if l.strip()]
    out = []
    for l in lineas:
        try:
            out.append(json.loads(l)["evento"])
        except Exception:
            continue
    return out[-limit:] if limit else out


def estado_buffer(domain_id: str) -> dict:
    p = _buf_path(domain_id)
    if not p.exists():
        return {"domain_id": domain_id, "total": 0, "ultimo": None}
    lineas = [l for l in p.read_text(encoding="utf-8").split("\n") if l.strip()]
    ultimo = None
    if lineas:
        try:
            ultimo = json.loads(lineas[-1]).get("_recibido")
        except Exception:
            pass
    return {"domain_id": domain_id, "total": len(lineas), "ultimo": ultimo}


def vaciar_buffer(domain_id: str) -> dict:
    p = _buf_path(domain_id)
    if p.exists():
        p.unlink()
    return {"domain_id": domain_id, "vaciado": True}


def poll_endpoint(domain_id: str, url: str, api_key: str = "", timeout: int = 15) -> dict:
    """Nivel 1 — GET saliente al endpoint del cliente. Best-effort, local."""
    if not url:
        return {"ok": False, "msg": "Se requiere url del endpoint del cliente."}
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "msg": f"No se pudo consultar el endpoint: {e}"}
    eventos = data if isinstance(data, list) else data.get("events", data.get("results", [data]))
    n = agregar_eventos(domain_id, eventos, fuente="poll")
    return {"ok": True, "eventos_agregados": n, "total_buffer": estado_buffer(domain_id)["total"]}
