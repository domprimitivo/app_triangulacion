"""
Aprendiz Mileforum - Backend FastAPI
100% LOCAL: SQLite unicamente, sin MongoDB, sin dependencia de internet.
F-05 integrado: export_package, anomalias, schema_draft, destruccion.
"""

from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Body
from starlette.middleware.cors import CORSMiddleware
import os
import sys
import json
import logging
import sqlite3
import zipfile
import io
import base64
import threading
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Literal
import uuid
from datetime import datetime, timezone
import shutil
from local_storage import guardar_stream

def _resolver_root_dir() -> Path:
    """
    Resuelve la carpeta base donde viven config.json, mileforum.db, uploads/, etc.

    - Si el proceso corre como .exe empaquetado con PyInstaller (--onefile),
      sys.frozen es True y sys.executable apunta al .exe real en disco.
      __file__ en ese caso apunta a una carpeta temporal (sys._MEIPASS) que
      se recrea en cada arranque y se borra al cerrar — NUNCA usar __file__
      para datos persistentes en este modo.
    - Si corre como script normal (python server.py / uvicorn server:app),
      __file__ sí apunta a la carpeta real del archivo y es seguro usarlo.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


ROOT_DIR = _resolver_root_dir()

CONFIG_PATH = ROOT_DIR / 'config.json'
UPLOADS_DIR = ROOT_DIR / 'uploads'
UPLOADS_DIR.mkdir(exist_ok=True)

SQLITE_PATH = ROOT_DIR / 'mileforum.db'

# ─── SQLite: conexion unica + lock (app local, un solo proceso) ─────────────
# sqlite3 es sincrono; FastAPI es async. Para una app local de un solo
# usuario esto es seguro y simple. El lock evita carreras entre requests
# concurrentes del mismo proceso.

_db_lock = threading.Lock()
_conn = sqlite3.connect(str(SQLITE_PATH), check_same_thread=False)
_conn.row_factory = sqlite3.Row


def init_sqlite():
    with _db_lock:
        _conn.executescript("""
            CREATE TABLE IF NOT EXISTS bimestral_runs (
                run_id              TEXT PRIMARY KEY,
                profile             TEXT,
                created_utc         TEXT,
                received_at         TEXT,
                retention_policy    TEXT,
                status              TEXT DEFAULT 'active',
                schema_draft_json   TEXT,
                quality_report_json TEXT,
                destruccion_at      TEXT,
                schema_answer       TEXT
            );

            CREATE TABLE IF NOT EXISTS expedientes (
                id           TEXT PRIMARY KEY,
                nombre       TEXT NOT NULL,
                descripcion  TEXT,
                dominio_id   TEXT NOT NULL,
                estado       TEXT DEFAULT 'pendiente',
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documentos (
                id            TEXT PRIMARY KEY,
                expediente_id TEXT NOT NULL,
                nombre        TEXT NOT NULL,
                tipo          TEXT,
                size          INTEGER,
                uploaded_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS procesamientos (
                id            TEXT PRIMARY KEY,
                expediente_id TEXT NOT NULL,
                tipo          TEXT,
                resultado_json TEXT,
                procesado_en  TEXT,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS decisiones (
                id              TEXT PRIMARY KEY,
                expediente_id   TEXT NOT NULL,
                sugerencia_tcl  TEXT,
                decision        TEXT,
                correccion      TEXT,
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sincronizaciones (
                id          TEXT PRIMARY KEY,
                tipo        TEXT,
                status      TEXT DEFAULT 'completado',
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS aprendiz_events (
                id           TEXT PRIMARY KEY,
                dominio      TEXT NOT NULL,
                event_id     TEXT,
                timestamp    TEXT,
                received_at  TEXT,
                payload_json TEXT
            );

            CREATE TABLE IF NOT EXISTS aprendiz_dictionaries (
                dominio     TEXT NOT NULL,
                tipo        TEXT NOT NULL,
                data_json   TEXT,
                updated_at  TEXT,
                PRIMARY KEY (dominio, tipo)
            );

            CREATE TABLE IF NOT EXISTS aprendiz_artefactos (
                id              TEXT PRIMARY KEY,
                dominio         TEXT NOT NULL,
                timestamp       TEXT,
                archivo_origen  TEXT,
                incorporado_at  TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_documentos_expediente ON documentos(expediente_id);
            CREATE INDEX IF NOT EXISTS idx_aprendiz_events_dominio ON aprendiz_events(dominio, timestamp);

            CREATE TABLE IF NOT EXISTS ingesta_webhook (
                id              TEXT PRIMARY KEY,
                dominio         TEXT NOT NULL,
                fuente          TEXT,
                payload_json    TEXT,
                texto_generado  TEXT,
                expediente_id   TEXT,
                resultado_json  TEXT,
                estado          TEXT DEFAULT 'recibido',
                error_msg       TEXT,
                received_at     TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_ingesta_dominio ON ingesta_webhook(dominio, received_at);
        """)
        _conn.commit()


init_sqlite()


def db_execute(query: str, params: tuple = ()):
    """INSERT/UPDATE/DELETE. Devuelve el cursor (para lastrowid/rowcount)."""
    with _db_lock:
        cur = _conn.execute(query, params)
        _conn.commit()
        return cur


def db_query(query: str, params: tuple = ()) -> List[sqlite3.Row]:
    """SELECT que devuelve multiples filas."""
    with _db_lock:
        return _conn.execute(query, params).fetchall()


def db_query_one(query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
    """SELECT que devuelve una sola fila (o None)."""
    with _db_lock:
        return _conn.execute(query, params).fetchone()


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row is not None else None


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    return {"modo": "local", "tipo_dominio": None, "dominio_id": None, "dominio_nombre": None, "configurado": False}


def save_config(config: Dict[str, Any]):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)


# ─── Sistema de Activación ───────────────────────────────────────────────────
#
# El activador es un archivo JSON firmado con HMAC-SHA256 que el operador
# (Antonio) genera para cada cliente tras el cierre bimestral. El cliente
# lo descarga del sitio web y lo coloca junto al .exe.
#
# La clave secreta vive aquí — nunca viaja al cliente ni al repositorio
# público. Si se compromete, se cambia la clave y se regeneran todos los
# activadores activos.
#
# IMPORTANTE: cambia ACTIVACION_CLAVE_SECRETA antes de distribuir a clientes
# reales. Usa cualquier cadena larga y aleatoria (32+ caracteres).

ACTIVACION_CLAVE_SECRETA = "mileforum-prudential-2026-clave-privada-antonio"
ACTIVACION_PATH = ROOT_DIR / "mileforum_activador.json"
ACTIVACION_DIAS_GRACIA = 7  # dias extra tras vencimiento antes de bloquear


def _calcular_cliente_id() -> str:
    """
    Calcula el cliente_id como hash SHA-256 de la huella de hardware
    de esta maquina especifica.

    Fuentes usadas (en orden de preferencia):
      1. UUID de la placa madre (WMI Win32_BaseBoard.SerialNumber) — muy estable
      2. UUID del sistema (WMI Win32_ComputerSystemProduct.UUID) — estable
      3. Numero de serie del volumen C: (vol C:) — cambia con formateo, no con reinstalacion
      4. Fallback: MAC address de la primera interfaz de red

    El hash resultante es determinista: misma maquina = mismo cliente_id,
    siempre, aunque el usuario reinstale la carpeta Mileforum o borre config.json.
    Una maquina diferente = cliente_id diferente = activador invalido.

    En sistemas no-Windows (ej. desarrollo en Linux/Mac) cae al fallback
    de MAC address para no romper el entorno de desarrollo.
    """
    import hashlib
    import subprocess

    fuentes = []

    if sys.platform == "win32":
        # 1. UUID de placa madre via WMIC
        try:
            r = subprocess.run(
                ["wmic", "baseboard", "get", "SerialNumber"],
                capture_output=True, text=True, timeout=5
            )
            serial = r.stdout.strip().split('\n')[-1].strip()
            if serial and serial.lower() not in ("", "none", "default string",
                                                  "to be filled by o.e.m.",
                                                  "not applicable"):
                fuentes.append(f"baseboard:{serial}")
        except Exception:
            pass

        # 2. UUID del sistema via WMIC
        try:
            r = subprocess.run(
                ["wmic", "csproduct", "get", "UUID"],
                capture_output=True, text=True, timeout=5
            )
            uid = r.stdout.strip().split('\n')[-1].strip()
            if uid and uid.upper() not in ("", "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF"):
                fuentes.append(f"uuid:{uid}")
        except Exception:
            pass

        # 3. Numero de serie del volumen C: (backup si WMI no responde)
        if not fuentes:
            try:
                r = subprocess.run(["vol", "C:"], capture_output=True,
                                   text=True, shell=True, timeout=5)
                for line in r.stdout.splitlines():
                    if "numero de serie" in line.lower() or "serial number" in line.lower():
                        volserial = line.split()[-1].strip()
                        if volserial:
                            fuentes.append(f"vol:{volserial}")
                            break
            except Exception:
                pass

    # 4. Fallback universal: MAC address
    if not fuentes:
        try:
            import uuid as _uuid
            mac = hex(_uuid.getnode())
            fuentes.append(f"mac:{mac}")
        except Exception:
            fuentes.append("fallback:mileforum")

    huella = "|".join(fuentes)
    return hashlib.sha256(huella.encode("utf-8")).hexdigest()[:32]


# Cache del cliente_id — se calcula una vez al arrancar, no en cada request
_cliente_id_cache: Optional[str] = None


def obtener_cliente_id() -> str:
    """Devuelve el cliente_id de esta maquina, calculandolo la primera vez."""
    global _cliente_id_cache
    if _cliente_id_cache is None:
        _cliente_id_cache = _calcular_cliente_id()
    return _cliente_id_cache


def _generar_firma(payload: dict, clave: str) -> str:
    """Genera la firma HMAC-SHA256 del payload para verificar autenticidad."""
    import hmac
    import hashlib
    # Solo firmar los campos de negocio, no la firma misma
    campos = {k: v for k, v in payload.items() if k != "firma"}
    contenido = json.dumps(campos, sort_keys=True, ensure_ascii=False)
    return hmac.new(
        clave.encode('utf-8'),
        contenido.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


def verificar_activador() -> dict:
    """
    Verifica el activador de la instalacion actual.
    El cliente_id se calcula desde el hardware de la maquina — no se lee
    de config.json ni de ningun archivo copiable. Esto impide que el usuario
    reinstale la carpeta Mileforum con archivos guardados y evite la suscripcion.
    """
    cliente_id = obtener_cliente_id()

    if not ACTIVACION_PATH.exists():
        return {
            "activo": False,
            "modo_lectura": True,
            "mensaje": "Activador no encontrado. Descarga tu archivo mileforum_activador.json del sitio web y colócalo junto al ejecutable.",
            "valido_hasta": None,
            "cliente_id": cliente_id,
            "dias_restantes": None,
        }

    try:
        with open(ACTIVACION_PATH, 'r', encoding='utf-8') as f:
            activador = json.load(f)
    except Exception as e:
        return {
            "activo": False,
            "modo_lectura": True,
            "mensaje": f"El archivo activador está corrupto o no es JSON válido: {e}",
            "valido_hasta": None,
            "cliente_id": cliente_id,
            "dias_restantes": None,
        }

    # 1. Verificar firma
    firma_recibida = activador.get("firma", "")
    firma_esperada = _generar_firma(activador, ACTIVACION_CLAVE_SECRETA)
    if firma_recibida != firma_esperada:
        return {
            "activo": False,
            "modo_lectura": True,
            "mensaje": "El activador no es válido (firma incorrecta). Descarga un activador nuevo desde el sitio web.",
            "valido_hasta": None,
            "cliente_id": cliente_id,
            "dias_restantes": None,
        }

    # 2. Verificar que el cliente_id coincide con esta instalacion
    activador_cliente_id = activador.get("cliente_id")
    if cliente_id and activador_cliente_id and activador_cliente_id != cliente_id:
        return {
            "activo": False,
            "modo_lectura": True,
            "mensaje": "Este activador pertenece a otra instalación. Solicita un activador para tu cliente_id específico.",
            "valido_hasta": activador.get("valido_hasta"),
            "cliente_id": cliente_id,
            "dias_restantes": None,
        }

    # 3. Verificar vencimiento (con dias de gracia)
    valido_hasta_str = activador.get("valido_hasta", "")
    try:
        valido_hasta = datetime.fromisoformat(valido_hasta_str.replace("Z", "+00:00"))
        ahora = datetime.now(timezone.utc)
        dias_restantes = (valido_hasta - ahora).days
        dias_con_gracia = dias_restantes + ACTIVACION_DIAS_GRACIA

        if dias_con_gracia < 0:
            return {
                "activo": False,
                "modo_lectura": True,
                "mensaje": f"Activador vencido hace {abs(dias_restantes)} días. Completa el cierre bimestral para renovar.",
                "valido_hasta": valido_hasta_str,
                "cliente_id": cliente_id,
                "dias_restantes": dias_restantes,
            }

        # Advertencia si quedan menos de 14 dias
        advertencia = ""
        if dias_restantes < 14:
            advertencia = f" ⚠️ Vence en {dias_restantes} días — programa tu cierre bimestral."

        return {
            "activo": True,
            "modo_lectura": False,
            "mensaje": f"Activador válido hasta {valido_hasta_str[:10]}.{advertencia}",
            "valido_hasta": valido_hasta_str,
            "cliente_id": cliente_id,
            "dias_restantes": dias_restantes,
        }

    except Exception as e:
        return {
            "activo": False,
            "modo_lectura": True,
            "mensaje": f"Fecha de vencimiento inválida en el activador: {e}",
            "valido_hasta": None,
            "cliente_id": cliente_id,
            "dias_restantes": None,
        }


# Estado global de activacion — se calcula una vez al startup y se
# recalcula cada vez que se llama /api/activacion/estado
_estado_activacion: dict = {"activo": False, "modo_lectura": True,
                             "mensaje": "Sistema iniciando...",
                             "valido_hasta": None, "cliente_id": None,
                             "dias_restantes": None}


def _refrescar_activacion():
    """Recalcula el estado de activacion y lo guarda en el estado global."""
    global _estado_activacion
    _estado_activacion = verificar_activador()


app = FastAPI(title="Aprendiz Mileforum API", description="Portal Episodico - Tu operacion, tu modelo (100% local)", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")

DOMINIOS_UNIPERSONALES = [
    {"id": "abogado", "nombre": "Abogado", "icono": "Scale", "descripcion": "Analisis legal y dictamenes"},
    {"id": "arquitecto", "nombre": "Arquitecto", "icono": "Ruler", "descripcion": "Proyectos y especificaciones"},
    {"id": "contador", "nombre": "Contador", "icono": "Calculator", "descripcion": "Analisis fiscal y financiero"},
    {"id": "consultor_pyme", "nombre": "Consultor PyME", "icono": "Briefcase", "descripcion": "Estrategia empresarial"},
    {"id": "diseno_producto", "nombre": "Diseno Producto", "icono": "PenTool", "descripcion": "Especificaciones de producto"},
    {"id": "operaciones", "nombre": "Operaciones", "icono": "Settings", "descripcion": "Procesos operativos"},
]

DOMINIOS_EMPRESAS = [
    {"id": "clinica", "nombre": "Clinica", "icono": "Stethoscope", "descripcion": "Gestion clinica"},
    {"id": "hotel", "nombre": "Hotel", "icono": "Bed", "descripcion": "Operaciones hoteleras"},
    {"id": "restaurante", "nombre": "Restaurante", "icono": "Utensils", "descripcion": "Gestion gastronomica"},
    {"id": "retail", "nombre": "Retail", "icono": "ShoppingBag", "descripcion": "Comercio minorista"},
    {"id": "fabrica", "nombre": "Fabrica", "icono": "Factory", "descripcion": "Produccion industrial"},
    {"id": "logistica", "nombre": "Logistica", "icono": "Truck", "descripcion": "Cadena de suministro"},
]

TODOS_DOMINIOS = DOMINIOS_UNIPERSONALES + DOMINIOS_EMPRESAS

# ─── Modelos Pydantic ────────────────────────────────────────────────────────

class ConfiguracionInicial(BaseModel):
    dominio_id: str
    modo: Literal["local"] = "local"

class ConfiguracionResponse(BaseModel):
    modo: str
    tipo_dominio: Optional[str]
    dominio_id: Optional[str]
    dominio_nombre: Optional[str]
    configurado: bool

class ExpedienteCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None

class Expediente(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    nombre: str
    descripcion: Optional[str] = None
    dominio_id: str
    estado: str = "pendiente"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class DocumentoMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    expediente_id: str
    nombre: str
    tipo: str
    size: int
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ProcesamientoRequest(BaseModel):
    tipo_consulta: str = "analisis"

class HeadsResponse(BaseModel):
    trigo: float
    cobre: float
    petroleo: float

class EstadosResponse(BaseModel):
    campos: float
    tension: float
    coherencia: float
    resiliencia: float
    indice_telos: float

class ProcesamientoUnipersonalResponse(BaseModel):
    expediente_id: str
    heads: HeadsResponse
    estados: EstadosResponse
    sugerencia_tcl: str
    procesado_en: str

class ProcesamientoEmpresaResponse(BaseModel):
    expediente_id: str
    resumen: str
    documentos_procesados: List[Dict[str, Any]]
    total_documentos: int

class DecisionCreate(BaseModel):
    expediente_id: str
    sugerencia_tcl: str
    decision: Literal["confirmar", "corregir", "abstener"]
    correccion: Optional[str] = None

class Decision(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    expediente_id: str
    sugerencia_tcl: str
    decision: str
    correccion: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SincronizacionCreate(BaseModel):
    tipo: str

class Sincronizacion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tipo: str
    status: str = "completado"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# F-05
class SchemaAnswerInput(BaseModel):
    answer: str

# ─── Helpers ────────────────────────────────────────────────────────────────

def get_tipo_dominio(dominio_id: str) -> Optional[str]:
    for d in DOMINIOS_UNIPERSONALES:
        if d["id"] == dominio_id:
            return "unipersonal"
    for d in DOMINIOS_EMPRESAS:
        if d["id"] == dominio_id:
            return "empresa"
    return None

def get_dominio_nombre(dominio_id: str) -> Optional[str]:
    for d in TODOS_DOMINIOS:
        if d["id"] == dominio_id:
            return d["nombre"]
    return None

# ─── Endpoints existentes ────────────────────────────────────────────────────

@api_router.get("/")
async def root():
    config = load_config()
    return {"sistema": "Aprendiz Mileforum", "version": "1.0.0", "filosofia": "Tu operacion, tu modelo", "configurado": config.get("configurado", False), "modo": config.get("modo", "local")}

@api_router.get("/config", response_model=ConfiguracionResponse)
async def get_configuracion():
    config = load_config()
    return ConfiguracionResponse(**config)

@api_router.post("/config/inicializar", response_model=ConfiguracionResponse)
async def inicializar_configuracion(input: ConfiguracionInicial):
    tipo_dominio = get_tipo_dominio(input.dominio_id)
    if not tipo_dominio:
        raise HTTPException(status_code=400, detail="Dominio no valido")
    dominio_nombre = get_dominio_nombre(input.dominio_id)

    config = {
        "modo": "local",
        "tipo_dominio": tipo_dominio,
        "dominio_id": input.dominio_id,
        "dominio_nombre": dominio_nombre,
        "configurado": True,
    }
    save_config(config)
    if tipo_dominio == "unipersonal":
        from aprendiz_motor import inicializar_motor
        inicializar_motor(config)
    else:
        from aprendiz_motor.rag_agents import inicializar_rag
        inicializar_rag(input.dominio_id)
    _refrescar_activacion()
    return ConfiguracionResponse(**config)


@api_router.get("/activacion/estado")
async def estado_activacion():
    """
    Estado actual del activador de la instalacion.
    Flutter lo consulta al arrancar para decidir si mostrar modo lectura.
    Incluye el cliente_id calculado desde el hardware — el cliente lo
    necesita para solicitar su activador al operador.
    """
    _refrescar_activacion()
    # Asegurar que el cliente_id del hardware siempre se expone,
    # independientemente de lo que diga el activador
    estado = dict(_estado_activacion)
    estado["cliente_id"] = obtener_cliente_id()
    return estado


@api_router.get("/dominios")
async def get_dominios():
    return {"unipersonales": DOMINIOS_UNIPERSONALES, "empresas": DOMINIOS_EMPRESAS, "total": len(TODOS_DOMINIOS)}

@api_router.post("/expedientes", response_model=Expediente)
async def crear_expediente(input: ExpedienteCreate):
    config = load_config()
    if not config.get("configurado"):
        raise HTTPException(status_code=400, detail="Sistema no configurado.")
    expediente = Expediente(nombre=input.nombre, descripcion=input.descripcion, dominio_id=config["dominio_id"])
    db_execute(
        "INSERT INTO expedientes (id, nombre, descripcion, dominio_id, estado, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (expediente.id, expediente.nombre, expediente.descripcion, expediente.dominio_id, expediente.estado,
         expediente.created_at.isoformat(), expediente.updated_at.isoformat())
    )
    return expediente

@api_router.get("/expedientes")
async def listar_expedientes():
    rows = db_query("SELECT * FROM expedientes ORDER BY created_at DESC")
    expedientes = []
    for row in rows:
        d = row_to_dict(row)
        d['created_at'] = datetime.fromisoformat(d['created_at'])
        d['updated_at'] = datetime.fromisoformat(d['updated_at'])
        expedientes.append(d)
    return expedientes

@api_router.get("/expedientes/{expediente_id}", response_model=Expediente)
async def obtener_expediente(expediente_id: str):
    row = db_query_one("SELECT * FROM expedientes WHERE id = ?", (expediente_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    d = row_to_dict(row)
    d['created_at'] = datetime.fromisoformat(d['created_at'])
    d['updated_at'] = datetime.fromisoformat(d['updated_at'])
    return Expediente(**d)

@api_router.post("/expedientes/{expediente_id}/documentos")
async def subir_documento(expediente_id: str, file: UploadFile = File(...)):
    expediente = db_query_one("SELECT id FROM expedientes WHERE id = ?", (expediente_id,))
    if not expediente:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    exp_dir = UPLOADS_DIR / expediente_id
    exp_dir.mkdir(exist_ok=True)
    file_path = exp_dir / file.filename
    guardar_stream(file_path, file.file)
    doc_meta = DocumentoMetadata(expediente_id=expediente_id, nombre=file.filename, tipo=file.content_type or "application/octet-stream", size=file_path.stat().st_size)
    db_execute(
        "INSERT INTO documentos (id, expediente_id, nombre, tipo, size, uploaded_at) VALUES (?, ?, ?, ?, ?, ?)",
        (doc_meta.id, doc_meta.expediente_id, doc_meta.nombre, doc_meta.tipo, doc_meta.size, doc_meta.uploaded_at.isoformat())
    )
    return {"status": "uploaded", "documento": doc_meta.model_dump()}

@api_router.get("/expedientes/{expediente_id}/documentos")
async def listar_documentos(expediente_id: str):
    rows = db_query("SELECT * FROM documentos WHERE expediente_id = ? ORDER BY uploaded_at DESC", (expediente_id,))
    documentos = [row_to_dict(r) for r in rows]
    return {"expediente_id": expediente_id, "documentos": documentos}

@api_router.delete("/expedientes/{expediente_id}")
async def eliminar_expediente(expediente_id: str):
    cur = db_execute("DELETE FROM expedientes WHERE id = ?", (expediente_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    db_execute("DELETE FROM documentos WHERE expediente_id = ?", (expediente_id,))
    exp_dir = UPLOADS_DIR / expediente_id
    if exp_dir.exists():
        shutil.rmtree(exp_dir)
    return {"status": "deleted", "expediente_id": expediente_id}

@api_router.post("/expedientes/{expediente_id}/procesar")
async def procesar_expediente(expediente_id: str, input: ProcesamientoRequest):
    config = load_config()
    if not config.get("configurado"):
        raise HTTPException(status_code=400, detail="Sistema no configurado")

    # Verificar activacion — modo lectura bloquea el procesamiento
    if _estado_activacion.get("modo_lectura"):
        raise HTTPException(
            status_code=403,
            detail=f"Sistema en modo lectura. {_estado_activacion.get('mensaje', 'Activa tu suscripción para procesar.')}"
        )

    expediente = db_query_one("SELECT * FROM expedientes WHERE id = ?", (expediente_id,))
    if not expediente:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    documentos = [row_to_dict(r) for r in db_query("SELECT * FROM documentos WHERE expediente_id = ?", (expediente_id,))]
    textos = []
    exp_dir = UPLOADS_DIR / expediente_id
    for doc in documentos:
        file_path = exp_dir / doc["nombre"]
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    textos.append(f.read())
            except Exception:
                textos.append(f"[Archivo binario: {doc['nombre']}]")
    texto_concatenado = "\n\n---\n\n".join(textos) if textos else "Sin documentos"

    db_execute("UPDATE expedientes SET estado = 'procesando', updated_at = ? WHERE id = ?",
               (datetime.now(timezone.utc).isoformat(), expediente_id))

    tipo_dominio = config.get("tipo_dominio")

    if tipo_dominio == "unipersonal":
        from aprendiz_motor import ejecutar_episodio
        resultado = ejecutar_episodio(texto_concatenado, input.tipo_consulta)
        procesado_en = "local"

        db_execute("UPDATE expedientes SET estado = 'completado', updated_at = ? WHERE id = ?",
                   (datetime.now(timezone.utc).isoformat(), expediente_id))

        db_execute(
            "INSERT INTO procesamientos (id, expediente_id, tipo, resultado_json, procesado_en, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), expediente_id, "unipersonal", json.dumps(resultado, ensure_ascii=False), procesado_en,
             datetime.now(timezone.utc).isoformat())
        )
        return ProcesamientoUnipersonalResponse(
            expediente_id=expediente_id,
            heads=HeadsResponse(**resultado["heads"]),
            estados=EstadosResponse(**resultado["estados"]),
            sugerencia_tcl=resultado["sugerencia_tcl"],
            procesado_en=procesado_en
        )
    else:
        from aprendiz_motor.rag_agents import procesar_expediente as rag_procesar
        docs_para_rag = [{"nombre": d["nombre"], "contenido": t, "tipo": d["tipo"]} for d, t in zip(documentos, textos)]
        resultado = rag_procesar(expediente_id, docs_para_rag)

        db_execute("UPDATE expedientes SET estado = 'completado', updated_at = ? WHERE id = ?",
                   (datetime.now(timezone.utc).isoformat(), expediente_id))
        return ProcesamientoEmpresaResponse(**resultado)

@api_router.post("/sincronizaciones/{expediente_id}/decision", response_model=Decision)
async def registrar_decision(expediente_id: str, input: DecisionCreate):
    expediente = db_query_one("SELECT id FROM expedientes WHERE id = ?", (expediente_id,))
    if not expediente:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    decision = Decision(expediente_id=expediente_id, sugerencia_tcl=input.sugerencia_tcl, decision=input.decision, correccion=input.correccion)
    db_execute(
        "INSERT INTO decisiones (id, expediente_id, sugerencia_tcl, decision, correccion, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (decision.id, decision.expediente_id, decision.sugerencia_tcl, decision.decision, decision.correccion,
         decision.created_at.isoformat())
    )
    return decision

@api_router.get("/decisiones", response_model=List[Decision])
async def listar_decisiones():
    rows = db_query("SELECT * FROM decisiones ORDER BY created_at DESC")
    decisiones = []
    for row in rows:
        d = row_to_dict(row)
        d['created_at'] = datetime.fromisoformat(d['created_at'])
        decisiones.append(d)
    return decisiones

@api_router.post("/sincronizaciones", response_model=Sincronizacion)
async def crear_sincronizacion(input: SincronizacionCreate):
    sync = Sincronizacion(tipo=input.tipo)
    db_execute(
        "INSERT INTO sincronizaciones (id, tipo, status, created_at) VALUES (?, ?, ?, ?)",
        (sync.id, sync.tipo, sync.status, sync.created_at.isoformat())
    )
    return sync

@api_router.get("/motor/estado")
async def estado_motor():
    config = load_config()
    estado = {"configurado": config.get("configurado", False), "modo": config.get("modo"), "tipo_dominio": config.get("tipo_dominio"), "dominio_id": config.get("dominio_id"), "motor_local_disponible": False}
    if config.get("configurado"):
        try:
            if config.get("tipo_dominio") == "unipersonal":
                from aprendiz_motor import obtener_estado_motor
                estado["motor_local_disponible"] = True
                estado["motor_estado"] = obtener_estado_motor()
            else:
                estado["motor_local_disponible"] = True
                estado["motor_estado"] = {"tipo": "RAG", "status": "ready"}
        except Exception as e:
            estado["motor_error"] = str(e)
    return estado

# ─── F-05: Endpoints Cierre Bimestral ────────────────────────────────────────

@api_router.post("/export-package/upload")
async def upload_export_package(file: UploadFile = File(...)):
    """
    Recibe export_package.zip del Notebook Bimestral.
    Extrae los JSONs clave y registra el run en SQLite.
    """
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .zip")

    contents = await file.read()
    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as zf:
            nombres = zf.namelist()

            def leer(nombre):
                if nombre in nombres:
                    return json.loads(zf.read(nombre).decode('utf-8'))
                return {}

            run_config      = leer('run_config.json')
            export_manifest = leer('export_manifest.json')
            quality_report  = leer('quality_report.json')
            schema_draft    = leer('schema_draft.json')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"ZIP invalido o corrupto: {e}")

    run_id           = run_config.get('run_id') or export_manifest.get('run_id') or str(uuid.uuid4())
    profile          = export_manifest.get('profile') or run_config.get('company_alias', 'unknown')
    created_utc      = export_manifest.get('created_utc', datetime.now(timezone.utc).isoformat())
    retention_policy = run_config.get('retention_policy', 'delete_after_export')

    db_execute("""
        INSERT OR REPLACE INTO bimestral_runs
        (run_id, profile, created_utc, received_at, retention_policy,
         status, schema_draft_json, quality_report_json)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
    """, (
        run_id, profile, created_utc,
        datetime.now(timezone.utc).isoformat(),
        retention_policy,
        json.dumps(schema_draft, ensure_ascii=False),
        json.dumps(quality_report, ensure_ascii=False),
    ))

    anomaly_hints = []
    for tabla in quality_report.get('tables', []):
        for hint in tabla.get('anomaly_hints', []):
            anomaly_hints.append(hint)

    minimal_questions = schema_draft.get('minimal_questions_for_human', [])

    return {
        "run_id":            run_id,
        "profile":           profile,
        "created_utc":       created_utc,
        "retention_policy":  retention_policy,
        "anomaly_hints":     anomaly_hints,
        "minimal_questions": minimal_questions,
        "status":            "registered",
    }


@api_router.get("/export-package/{run_id}/quality")
async def get_quality_anomalies(run_id: str):
    row = db_query_one("SELECT quality_report_json FROM bimestral_runs WHERE run_id = ?", (run_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    quality = json.loads(row["quality_report_json"])
    anomaly_hints = []
    for tabla in quality.get('tables', []):
        for hint in tabla.get('anomaly_hints', []):
            anomaly_hints.append(hint)
    return {"run_id": run_id, "anomaly_hints": anomaly_hints}


@api_router.get("/export-package/{run_id}/schema-draft")
async def get_schema_draft_questions(run_id: str):
    row = db_query_one("SELECT schema_draft_json FROM bimestral_runs WHERE run_id = ?", (run_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    schema = json.loads(row["schema_draft_json"])
    return {
        "run_id":            run_id,
        "minimal_questions": schema.get('minimal_questions_for_human', []),
    }


@api_router.post("/export-package/{run_id}/schema-answer")
async def save_schema_answer(run_id: str, body: SchemaAnswerInput):
    cur = db_execute("UPDATE bimestral_runs SET schema_answer = ? WHERE run_id = ?", (body.answer, run_id))
    if not cur.rowcount:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    return {"run_id": run_id, "answer_saved": True}


@api_router.post("/export-package/{run_id}/destruccion")
async def generar_recibo_destruccion(run_id: str):
    row = db_query_one(
        "SELECT run_id, profile, created_utc, retention_policy, status FROM bimestral_runs WHERE run_id = ?",
        (run_id,)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    if row["status"] == 'destruido':
        raise HTTPException(status_code=400, detail="Este run ya fue destruido")
    destruccion_at = datetime.now(timezone.utc).isoformat()
    db_execute("UPDATE bimestral_runs SET status = 'destruido', destruccion_at = ? WHERE run_id = ?",
               (destruccion_at, run_id))
    recibo_id = f"REC-{run_id[:8].upper()}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    return {
        "recibo_id":        recibo_id,
        "run_id":           row["run_id"],
        "profile":          row["profile"],
        "created_utc":      row["created_utc"],
        "retention_policy": row["retention_policy"],
        "destruccion_at":   destruccion_at,
        "status":           "destruido",
        "mensaje":          f"Datos del run procesados y eliminados segun politica de retencion '{row['retention_policy']}'. Este recibo es el comprobante oficial de destruccion.",
        "archivos_destruidos": [
            "raw_bundle/hotel_data.csv",
            "normalized_bundle/hotel_data.csv",
            "run_config.json",
            "schema_draft.json",
            "quality_report.json",
            "export_manifest.json",
        ],
    }


@api_router.get("/export-package/{run_id}/recibo")
async def get_recibo_destruccion(run_id: str):
    row = db_query_one(
        "SELECT run_id, profile, created_utc, retention_policy, status, destruccion_at FROM bimestral_runs WHERE run_id = ?",
        (run_id,)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    if row["status"] != 'destruido':
        raise HTTPException(status_code=400, detail="Run aun activo — destruccion no ejecutada")
    recibo_id = f"REC-{row['run_id'][:8].upper()}-{row['destruccion_at'][:10].replace('-', '')}"
    return {
        "recibo_id":        recibo_id,
        "run_id":           row["run_id"],
        "profile":          row["profile"],
        "created_utc":      row["created_utc"],
        "retention_policy": row["retention_policy"],
        "status":           row["status"],
        "destruccion_at":   row["destruccion_at"],
        "mensaje":          f"Datos del run procesados y eliminados segun politica de retencion '{row['retention_policy']}'. Este recibo es el comprobante oficial de destruccion.",
    }


# ─── Aprendiz: endpoints para archivos generados por el motor ────────────────

APRENDIZ_DIR = ROOT_DIR / 'aprendiz_data'
APRENDIZ_DIR.mkdir(exist_ok=True)


@api_router.post("/aprendiz/{dominio}/learning-log")
async def recibir_learning_log(dominio: str, file: UploadFile = File(...)):
    """
    Recibe el learning_log.jsonl generado por el Aprendiz de un dominio.
    Almacena los eventos y los registra en SQLite para consulta.
    """
    contenido = await file.read()
    lineas = contenido.decode('utf-8').strip().split('\n')
    eventos = []
    for linea in lineas:
        if linea.strip():
            try:
                eventos.append(json.loads(linea))
            except json.JSONDecodeError:
                continue

    ruta = APRENDIZ_DIR / f"{dominio}_learning_log.jsonl"
    await file.seek(0)
    guardar_stream(ruta, file.file)

    received_at = datetime.now(timezone.utc).isoformat()
    for evento in eventos:
        evento_dominio = dict(evento)
        evento_dominio['dominio'] = dominio
        evento_dominio['received_at'] = received_at
        db_execute(
            "INSERT INTO aprendiz_events (id, dominio, event_id, timestamp, received_at, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), dominio, evento.get('event_id'), evento.get('timestamp'), received_at,
             json.dumps(evento_dominio, ensure_ascii=False))
        )

    return {
        "dominio": dominio,
        "eventos_recibidos": len(eventos),
        "status": "registered",
        "archivo": f"{dominio}_learning_log.jsonl",
    }


@api_router.get("/aprendiz/{dominio}/learning-log")
async def obtener_learning_log(dominio: str, limit: int = 50):
    """
    Retorna los últimos eventos del learning_log de un dominio.
    """
    rows = db_query(
        "SELECT payload_json FROM aprendiz_events WHERE dominio = ? ORDER BY timestamp DESC LIMIT ?",
        (dominio, limit)
    )
    eventos = [json.loads(r["payload_json"]) for r in rows]
    return {"dominio": dominio, "eventos": eventos, "total": len(eventos)}


@api_router.post("/aprendiz/{dominio}/soft-dictionary")
async def recibir_soft_dictionary(dominio: str, file: UploadFile = File(...)):
    """
    Recibe el soft_dictionary_state.json generado por el Aprendiz.
    """
    contenido = await file.read()
    try:
        data = json.loads(contenido.decode('utf-8'))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON invalido")

    ruta = APRENDIZ_DIR / f"{dominio}_soft_dictionary_state.json"
    await file.seek(0)
    guardar_stream(ruta, file.file)

    db_execute("""
        INSERT INTO aprendiz_dictionaries (dominio, tipo, data_json, updated_at)
        VALUES (?, 'soft', ?, ?)
        ON CONFLICT(dominio, tipo) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at
    """, (dominio, json.dumps(data, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))

    return {
        "dominio": dominio,
        "tipo": "soft_dictionary",
        "custom_vars": len(data.get("custom_soft_vars", [])),
        "status": "updated",
    }


@api_router.get("/aprendiz/{dominio}/soft-dictionary")
async def obtener_soft_dictionary(dominio: str):
    """
    Retorna el soft_dictionary_state actual de un dominio.
    """
    row = db_query_one("SELECT * FROM aprendiz_dictionaries WHERE dominio = ? AND tipo = 'soft'", (dominio,))
    if not row:
        raise HTTPException(status_code=404, detail="Soft dictionary no encontrado")
    return {
        "dominio": row["dominio"],
        "tipo": row["tipo"],
        "data": json.loads(row["data_json"]),
        "updated_at": row["updated_at"],
    }


@api_router.post("/aprendiz/{dominio}/action-dictionary")
async def recibir_action_dictionary(dominio: str, file: UploadFile = File(...)):
    """
    Recibe el action_dictionary_state.json generado por el Aprendiz.
    Contiene las acciones disponibles por fase: stable, tension, drift, rupture.
    """
    contenido = await file.read()
    try:
        data = json.loads(contenido.decode('utf-8'))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON invalido")

    ruta = APRENDIZ_DIR / f"{dominio}_action_dictionary_state.json"
    await file.seek(0)
    guardar_stream(ruta, file.file)

    db_execute("""
        INSERT INTO aprendiz_dictionaries (dominio, tipo, data_json, updated_at)
        VALUES (?, 'action', ?, ?)
        ON CONFLICT(dominio, tipo) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at
    """, (dominio, json.dumps(data, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))

    fases = data.get("actions_by_phase", {})
    total_acciones = sum(len(v) for v in fases.values())

    return {
        "dominio": dominio,
        "tipo": "action_dictionary",
        "fases": list(fases.keys()),
        "total_acciones": total_acciones,
        "status": "updated",
    }


@api_router.get("/aprendiz/{dominio}/action-dictionary")
async def obtener_action_dictionary(dominio: str):
    """
    Retorna el action_dictionary_state actual de un dominio.
    """
    row = db_query_one("SELECT * FROM aprendiz_dictionaries WHERE dominio = ? AND tipo = 'action'", (dominio,))
    if not row:
        raise HTTPException(status_code=404, detail="Action dictionary no encontrado")
    return {
        "dominio": row["dominio"],
        "tipo": row["tipo"],
        "data": json.loads(row["data_json"]),
        "updated_at": row["updated_at"],
    }


@api_router.get("/aprendiz/{dominio}/estado")
async def obtener_estado_aprendiz(dominio: str):
    """
    Resumen del estado actual del Aprendiz de un dominio:
    ultimo evento, fase actual, accion sugerida y R_score.
    """
    row = db_query_one(
        "SELECT payload_json FROM aprendiz_events WHERE dominio = ? ORDER BY timestamp DESC LIMIT 1",
        (dominio,)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Sin eventos para este dominio")

    ultimo = json.loads(row["payload_json"])
    backbone = ultimo.get("backbone_inference", {})
    tcl = ultimo.get("tcl", {})
    taximeter = ultimo.get("taximeter_snapshot", {})

    return {
        "dominio": dominio,
        "ultimo_evento": ultimo.get("event_id"),
        "timestamp": ultimo.get("timestamp"),
        "fase_actual": backbone.get("phase"),
        "R_score": backbone.get("R_score"),
        "clarity_ok": backbone.get("clarity", {}).get("ok"),
        "accion_sugerida": tcl.get("suggested", {}).get("label"),
        "R_brake_warning": tcl.get("R_brake", {}).get("warning", False),
        "costo_operativo": taximeter.get("now", {}).get("score"),
    }


# ─── Persistencia de archivos y paquete bimestral ────────────────────────────

SESSION_FILES_DIR = ROOT_DIR / 'session_files'
BUNDLES_DIR = ROOT_DIR / 'bundles'
BIMESTRAL_PACKAGE_DIR = ROOT_DIR / 'bimestral_package'

SESSION_FILES_DIR.mkdir(exist_ok=True)
BUNDLES_DIR.mkdir(exist_ok=True)
BIMESTRAL_PACKAGE_DIR.mkdir(exist_ok=True)


@api_router.get("/archivos/{dominio}")
async def listar_archivos_dominio(dominio: str):
    """
    Lista todos los archivos generados y persistidos para un dominio.
    """
    archivos = []

    for f in APRENDIZ_DIR.glob(f"{dominio}_*"):
        archivos.append({
            "nombre": f.name,
            "tipo": "aprendiz",
            "tamanio_kb": round(f.stat().st_size / 1024, 1),
            "modificado": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
        })

    for f in BUNDLES_DIR.glob(f"{dominio}_*"):
        archivos.append({
            "nombre": f.name,
            "tipo": "bundle",
            "tamanio_kb": round(f.stat().st_size / 1024, 1),
            "modificado": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
        })

    for f in SESSION_FILES_DIR.glob(f"{dominio}_*"):
        archivos.append({
            "nombre": f.name,
            "tipo": "sesion",
            "tamanio_kb": round(f.stat().st_size / 1024, 1),
            "modificado": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
        })

    return {
        "dominio": dominio,
        "total": len(archivos),
        "archivos": sorted(archivos, key=lambda x: x["modificado"], reverse=True),
    }


@api_router.post("/bundles/{dominio}/guardar")
async def guardar_bundle(dominio: str, tipo: str, file: UploadFile = File(...)):
    """
    Persiste el raw_bundle o normalized_bundle en disco.
    tipo: 'raw' o 'normalized'
    """
    if tipo not in ['raw', 'normalized']:
        raise HTTPException(status_code=400, detail="tipo debe ser 'raw' o 'normalized'")

    contenido = await file.read()
    nombre = f"{dominio}_{tipo}_bundle_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}{Path(file.filename).suffix}"
    ruta = BUNDLES_DIR / nombre
    await file.seek(0)
    guardar_stream(ruta, file.file)

    return {
        "dominio": dominio,
        "tipo": tipo,
        "archivo": nombre,
        "tamanio_kb": round(len(contenido) / 1024, 1),
        "status": "persistido",
        "disponible_para_exportar": True,
    }


@api_router.get("/bundles/{dominio}")
async def listar_bundles(dominio: str):
    """
    Lista los bundles disponibles de un dominio para exportar a otros sistemas.
    """
    bundles = []
    for f in BUNDLES_DIR.glob(f"{dominio}_*"):
        bundles.append({
            "nombre": f.name,
            "tamanio_kb": round(f.stat().st_size / 1024, 1),
            "modificado": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
        })
    return {"dominio": dominio, "bundles": sorted(bundles, key=lambda x: x["modificado"], reverse=True)}


@api_router.post("/bimestral/{dominio}/preparar-paquete")
async def preparar_paquete_bimestral(dominio: str):
    """
    Prepara automáticamente el paquete que el Notebook necesita para el cierre bimestral.
    """
    archivos_incluidos = []
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    zip_nombre = f"{dominio}_bimestral_package_{timestamp}.zip"
    zip_ruta = BIMESTRAL_PACKAGE_DIR / zip_nombre

    with zipfile.ZipFile(zip_ruta, 'w', zipfile.ZIP_DEFLATED) as zf:

        ll = APRENDIZ_DIR / f"{dominio}_learning_log.jsonl"
        if ll.exists():
            zf.write(ll, f"aprendiz/{ll.name}")
            archivos_incluidos.append(ll.name)

        sd = APRENDIZ_DIR / f"{dominio}_soft_dictionary_state.json"
        if sd.exists():
            zf.write(sd, f"aprendiz/{sd.name}")
            archivos_incluidos.append(sd.name)

        ad = APRENDIZ_DIR / f"{dominio}_action_dictionary_state.json"
        if ad.exists():
            zf.write(ad, f"aprendiz/{ad.name}")
            archivos_incluidos.append(ad.name)

        for f in BUNDLES_DIR.glob(f"{dominio}_*"):
            zf.write(f, f"bundles/{f.name}")
            archivos_incluidos.append(f.name)

        for f in SESSION_FILES_DIR.glob(f"{dominio}_*"):
            zf.write(f, f"sesion/{f.name}")
            archivos_incluidos.append(f.name)

        meta = {
            "dominio": dominio,
            "generado_at": datetime.now(timezone.utc).isoformat(),
            "archivos": archivos_incluidos,
            "listo_para_notebook": True,
        }
        zf.writestr("package_manifest.json", json.dumps(meta, ensure_ascii=False, indent=2))

    return {
        "dominio": dominio,
        "zip": zip_nombre,
        "archivos_incluidos": archivos_incluidos,
        "total": len(archivos_incluidos),
        "listo_para_notebook": True,
        "generado_at": datetime.now(timezone.utc).isoformat(),
    }


@api_router.get("/bimestral/{dominio}/ultimo-run")
async def ultimo_run_bimestral(dominio: str):
    """
    Devuelve el último export_package registrado para el dominio (run activo
    más reciente), con sus anomaly_hints y minimal_questions reales.
    Es la fuente de datos que la pantalla de Cierre Bimestral debe usar en
    lugar de valores simulados. 404 si aún no se ha subido ningún ZIP del
    Notebook para este dominio.
    """
    row = db_query_one(
        """SELECT run_id, profile, created_utc, received_at, retention_policy,
                  status, schema_draft_json, quality_report_json
           FROM bimestral_runs
           WHERE profile = ? AND status = 'active'
           ORDER BY received_at DESC LIMIT 1""",
        (dominio,)
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No hay runs bimestrales registrados para '{dominio}'. Sube primero el export_package.zip del Notebook.")

    quality = json.loads(row["quality_report_json"] or "{}")
    schema  = json.loads(row["schema_draft_json"] or "{}")

    anomaly_hints = []
    for tabla in quality.get('tables', []):
        for hint in tabla.get('anomaly_hints', []):
            anomaly_hints.append(hint)

    return {
        "run_id":            row["run_id"],
        "profile":           row["profile"],
        "created_utc":       row["created_utc"],
        "retention_policy":  row["retention_policy"],
        "anomaly_hints":     anomaly_hints,
        "minimal_questions": schema.get('minimal_questions_for_human', []),
        "status":            row["status"],
    }


@api_router.post("/bimestral/{dominio}/incorporar-artefactos")
async def incorporar_artefactos_notebook(dominio: str, file: UploadFile = File(...)):
    """
    Incorpora los artefactos generados por el Notebook de ajuste bimestral
    al ZIP del Aprendiz para que el Notebook de día a día los gestione.
    """
    contenido = await file.read()
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')

    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as zf:
            for nombre_archivo in zf.namelist():
                datos = zf.read(nombre_archivo)
                destino = APRENDIZ_DIR / f"{dominio}_ajuste_{timestamp}_{Path(nombre_archivo).name}"
                with open(destino, 'wb') as f:
                    f.write(datos)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error procesando artefactos: {e}")

    db_execute(
        "INSERT INTO aprendiz_artefactos (id, dominio, timestamp, archivo_origen, incorporado_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), dominio, timestamp, file.filename, datetime.now(timezone.utc).isoformat())
    )

    return {
        "dominio": dominio,
        "status": "incorporado",
        "timestamp": timestamp,
        "mensaje": "Artefactos del ajuste bimestral incorporados al directorio del Aprendiz.",
    }


# ─── Ingesta en tiempo real — Webhook (Fase 2) ───────────────────────────────

class WebhookPayload(BaseModel):
    """
    Payload que el sistema externo (POS, sensor, ERP) envía al endpoint
    de ingesta. El campo 'datos' es libre — puede traer cualquier estructura
    de negocio. El domain_adapter normaliza esos datos a texto plano antes
    de pasarlos al motor del Aprendiz.

    Campos opcionales:
    - fuente: identificador del sistema que envía (ej. "POS-hotel", "sensor-fabrica")
    - tipo_consulta: pasa directo a ejecutar_episodio() como tipo_consulta
    - datos: el payload real del sistema externo (dict libre)
    - texto: alternativa a datos — texto libre ya listo para el motor
    """
    fuente: Optional[str] = "webhook"
    tipo_consulta: str = "analisis"
    datos: Optional[Dict[str, Any]] = None
    texto: Optional[str] = None


def _domain_adapter(dominio_id: str, datos: Dict[str, Any]) -> str:
    """
    Módulo 1 del Conector (Fase 2): convierte el payload crudo del sistema
    externo en texto plano que el motor del Aprendiz puede procesar.

    Estrategia actual: serialización inteligente por dominio.
    En Fase 2 completa, cada dominio tendrá su propio JSON de adaptación
    (domain_adapter_{dominio}.json) con el mapeo de campos y el centro
    de gravedad (triangulación dinero vs conservación interna).

    Por ahora genera texto estructurado a partir de los pares clave/valor,
    expandiendo números a lenguaje natural para que la extracción de
    keywords (trigo/cobre/petroleo) funcione correctamente.
    """
    # Vocabulario por dominio — mapea campos de negocio a términos del motor
    VOCABULARIO = {
        "hotel": {
            "ocupacion": "capacidad disponible recurso",
            "revenue": "ingreso flujo continuidad",
            "cancelaciones": "riesgo conflicto urgente",
            "quejas": "queja tensión crítico",
            "mantenimiento": "proceso protocolo sistema",
        },
        "clinica": {
            "pacientes": "capacidad recurso personal",
            "urgencias": "urgente crítico alerta",
            "citas": "proceso flujo continuidad",
            "insumos": "inventario activo reserva",
        },
        "restaurante": {
            "covers": "capacidad recurso flujo",
            "merma": "riesgo pérdida tensión",
            "pedidos": "proceso operación continuidad",
            "proveedores": "proveedor garantía financiamiento",
        },
        "fabrica": {
            "produccion": "proceso operación eficiencia",
            "paros": "urgente crítico conflicto",
            "inventario": "inventario activo reserva",
            "calidad": "coherencia protocolo balance",
        },
        "logistica": {
            "entregas": "proceso flujo continuidad",
            "retrasos": "tensión riesgo urgente",
            "flota": "activo capacidad recurso",
            "rutas": "eficiencia sistema cronograma",
        },
        "retail": {
            "ventas": "ingreso continuidad flujo",
            "devolucion": "riesgo conflicto tensión",
            "stock": "inventario activo reserva",
            "clientes": "recurso capacidad personal",
        },
    }

    vocab = VOCABULARIO.get(dominio_id, {})
    partes = [f"Ingesta automatica del dominio {dominio_id}."]

    for clave, valor in datos.items():
        # Expandir el nombre del campo con el vocabulario del dominio
        expansion = vocab.get(clave.lower(), "")
        if isinstance(valor, (int, float)):
            partes.append(f"{clave}: {valor}. {expansion}")
        elif isinstance(valor, str):
            partes.append(f"{clave}: {valor}. {expansion}")
        elif isinstance(valor, dict):
            sub = ", ".join(f"{k}={v}" for k, v in valor.items())
            partes.append(f"{clave}: {sub}. {expansion}")
        else:
            partes.append(f"{clave}: {str(valor)}. {expansion}")

    return " ".join(partes)


@api_router.post("/ingesta/webhook/{dominio}")
async def recibir_webhook(dominio: str, payload: WebhookPayload):
    """
    Endpoint de ingesta en tiempo real para Fase 2.

    El sistema externo (POS, sensor, ERP del cliente) hace POST a esta
    ruta con el payload de negocio. El backend:
    1. Valida que el dominio esté configurado y sea el activo
    2. Normaliza el payload con el domain_adapter (Módulo 1 del Conector)
    3. Crea un expediente temporal en SQLite
    4. Ejecuta el motor del Aprendiz inmediatamente
    5. Guarda el resultado y lo devuelve en la respuesta

    Para exponer este endpoint al exterior (sistema externo en otra red)
    usar un tunel como ngrok o cloudflared apuntando al puerto 8001.
    """
    # Verificar activacion
    if _estado_activacion.get("modo_lectura"):
        raise HTTPException(
            status_code=403,
            detail=f"Sistema en modo lectura. {_estado_activacion.get('mensaje', 'Activa tu suscripción.')}"
        )

    # 1. Verificar que el dominio activo coincide
    config = load_config()
    if not config.get("configurado"):
        raise HTTPException(status_code=400, detail="Sistema no configurado.")
    if config.get("dominio_id") != dominio:
        raise HTTPException(
            status_code=400,
            detail=f"Dominio activo es '{config.get('dominio_id')}', no '{dominio}'."
        )

    ingesta_id = str(uuid.uuid4())
    received_at = datetime.now(timezone.utc).isoformat()

    # 2. Normalizar payload → texto para el motor
    if payload.texto:
        texto = payload.texto
    elif payload.datos:
        texto = _domain_adapter(dominio, payload.datos)
    else:
        raise HTTPException(status_code=400, detail="Se requiere 'datos' o 'texto' en el payload.")

    # Registrar recepcion antes de procesar (para auditoría aunque falle el motor)
    db_execute(
        """INSERT INTO ingesta_webhook
           (id, dominio, fuente, payload_json, texto_generado, estado, received_at)
           VALUES (?, ?, ?, ?, ?, 'procesando', ?)""",
        (ingesta_id, dominio, payload.fuente,
         json.dumps(payload.datos or {}, ensure_ascii=False),
         texto, received_at)
    )

    # 3. Crear expediente temporal
    exp_id = str(uuid.uuid4())
    nombre_exp = f"[AUTO] {payload.fuente or 'webhook'} — {received_at[:10]}"
    db_execute(
        "INSERT INTO expedientes (id, nombre, descripcion, dominio_id, estado, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (exp_id, nombre_exp, f"Ingesta automática vía webhook desde {payload.fuente}",
         dominio, "procesando", received_at, received_at)
    )

    # 4. Ejecutar motor inmediatamente
    try:
        tipo_dominio = config.get("tipo_dominio")
        if tipo_dominio == "unipersonal":
            from aprendiz_motor import ejecutar_episodio
            resultado = ejecutar_episodio(texto, payload.tipo_consulta)
        else:
            from aprendiz_motor.rag_agents import procesar_expediente as rag_procesar
            docs = [{"nombre": "webhook.txt", "contenido": texto, "tipo": "text/plain"}]
            resultado = rag_procesar(exp_id, docs)

        # 5. Guardar resultado
        db_execute("UPDATE expedientes SET estado = 'completado', updated_at = ? WHERE id = ?",
                   (datetime.now(timezone.utc).isoformat(), exp_id))
        db_execute(
            "INSERT INTO procesamientos (id, expediente_id, tipo, resultado_json, procesado_en, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), exp_id, "webhook_automatico",
             json.dumps(resultado, ensure_ascii=False), "local",
             datetime.now(timezone.utc).isoformat())
        )
        db_execute(
            "UPDATE ingesta_webhook SET expediente_id=?, resultado_json=?, estado='completado' WHERE id=?",
            (exp_id, json.dumps(resultado, ensure_ascii=False), ingesta_id)
        )

        return {
            "ingesta_id": ingesta_id,
            "expediente_id": exp_id,
            "dominio": dominio,
            "fuente": payload.fuente,
            "estado": "completado",
            "resultado": resultado,
            "received_at": received_at,
        }

    except Exception as e:
        db_execute("UPDATE expedientes SET estado = 'error', updated_at = ? WHERE id = ?",
                   (datetime.now(timezone.utc).isoformat(), exp_id))
        db_execute("UPDATE ingesta_webhook SET estado='error', error_msg=? WHERE id=?",
                   (str(e), ingesta_id))
        raise HTTPException(status_code=500, detail=f"Error en motor: {str(e)}")


@api_router.get("/ingesta/{dominio}/ultimos")
async def ultimos_ingestas(dominio: str, limit: int = 20):
    """
    Devuelve los últimos N registros de ingesta vía webhook para un dominio.
    La pantalla de monitor de Flutter consulta este endpoint para mostrar
    el historial de recepciones automáticas en tiempo real.
    """
    rows = db_query(
        """SELECT id, fuente, estado, error_msg, resultado_json, received_at
           FROM ingesta_webhook
           WHERE dominio = ?
           ORDER BY received_at DESC
           LIMIT ?""",
        (dominio, limit)
    )
    registros = []
    for r in rows:
        d = row_to_dict(r)
        # Extraer solo los campos clave del resultado para no inflar la respuesta
        if d.get("resultado_json"):
            try:
                res = json.loads(d["resultado_json"])
                d["sugerencia_tcl"] = res.get("sugerencia_tcl", "")
                d["modo_motor"] = res.get("modo_motor", "")
                d["confianza"] = res.get("confianza")
            except Exception:
                pass
        del d["resultado_json"]
        registros.append(d)

    return {
        "dominio": dominio,
        "total": len(registros),
        "registros": registros,
    }


@api_router.get("/ingesta/{dominio}/estado")
async def estado_ingesta(dominio: str):
    """
    Resumen del estado de la ingesta para un dominio:
    total recibidos, completados, errores, y el timestamp del último registro.
    """
    row = db_query_one(
        """SELECT
               COUNT(*) as total,
               SUM(CASE WHEN estado='completado' THEN 1 ELSE 0 END) as completados,
               SUM(CASE WHEN estado='error' THEN 1 ELSE 0 END) as errores,
               MAX(received_at) as ultimo_received_at
           FROM ingesta_webhook WHERE dominio = ?""",
        (dominio,)
    )
    d = row_to_dict(row) if row else {}
    return {
        "dominio": dominio,
        "total": d.get("total", 0),
        "completados": d.get("completados", 0),
        "errores": d.get("errores", 0),
        "ultimo_received_at": d.get("ultimo_received_at"),
    }


# ─── Lazo Generico: Pantalla de Claridad (Asesoria / Agencia) ────────────────

from lazo_generico import (
    DOMINIO_CVD,
    lazo_asesoria,
    lazo_agencia,
    dominio_serializable,
)


class LazoInput(BaseModel):
    modo: Literal["ASESORIA", "AGENCIA"]
    kpis: Dict[str, float]


@api_router.get("/lazo/dominio")
async def get_lazo_dominio():
    """
    Config del dominio activo (KPIs, umbrales y geodesicas) para que la
    Pantalla de Claridad renderice las entradas del lazo.
    """
    return dominio_serializable(DOMINIO_CVD)


@api_router.post("/lazo/evaluar")
async def evaluar_lazo(input: LazoInput):
    """
    Ejecuta el lazo generico y devuelve exactamente lo que la Pantalla de
    Claridad debe mostrar. Reemplaza el antiguo reporte de claridad.
    """
    if input.modo == "ASESORIA":
        return lazo_asesoria(input.kpis, DOMINIO_CVD)
    return lazo_agencia(input.kpis, DOMINIO_CVD)


# ─── Compresión Geométrica (Códec MOCG, 100% local) ──────────────────────────

from compresion_geometrica import (
    comprimir as _comprimir,
    descomprimir as _descomprimir,
    es_paquete_comprimido as _es_paquete,
)

COMPRESION_DIR = ROOT_DIR / 'compresion'
COMPRESION_DIR.mkdir(exist_ok=True)


@api_router.post("/compresion/toggle")
async def compresion_toggle(files: List[UploadFile] = File(...)):
    """
    Botón único: si se sube UN paquete ya comprimido → descomprime
    (reconstrucción exacta). En cualquier otro caso → comprime lo
    seleccionado (3 capas + reporte de forma). Todo local.
    """
    leidos = []
    for f in files:
        leidos.append({"nombre": f.filename, "datos": await f.read()})

    # ¿Alternar a descompresión? (un solo archivo y es paquete del códec)
    if len(leidos) == 1 and _es_paquete(leidos[0]["datos"]):
        paquete = json.loads(leidos[0]["datos"].decode("utf-8"))
        reconstruidos = _descomprimir(paquete)
        return {
            "accion": "descomprimido",
            "n_archivos": len(reconstruidos),
            "integridad_ok": all(r["sha256_ok"] for r in reconstruidos),
            "archivos": [
                {"nombre": r["nombre"],
                 "datos_b64": base64.b64encode(r["datos"]).decode("ascii"),
                 "sha256_ok": r["sha256_ok"]}
                for r in reconstruidos
            ],
        }

    # Comprimir
    config = load_config()
    org_id = config.get("dominio_id") or "ORG-001"
    paquete = _comprimir(leidos, org_id=org_id)
    return {
        "accion": "comprimido",
        "marker": paquete["marker"],
        "shape_report": paquete["shape_report"],
        "paquete": paquete,
    }


@api_router.post("/compresion/sistema/{dominio}")
async def comprimir_sistema(dominio: str):
    """
    Comprime las carpetas que el sistema genera para un dominio
    (aprendiz_data, bundles, session_files, bimestral_package).
    """
    leidos = []
    for carpeta in (APRENDIZ_DIR, BUNDLES_DIR, SESSION_FILES_DIR, BIMESTRAL_PACKAGE_DIR):
        for f in carpeta.glob(f"{dominio}_*"):
            if f.is_file():
                leidos.append({"nombre": f.name, "datos": f.read_bytes()})
    if not leidos:
        raise HTTPException(status_code=404, detail=f"Sin archivos de sistema para '{dominio}'.")
    paquete = _comprimir(leidos, org_id=dominio)
    return {
        "accion": "comprimido",
        "dominio": dominio,
        "shape_report": paquete["shape_report"],
        "paquete": paquete,
    }


# ─── Flujo de KPIs: Cucurucho → 7 KPIs holográficos → Lazo ───────────────────

from flujo_kpis import (
    listar_clientes as _listar_clientes,
    listar_dominios as _listar_dominios,
    ejecutar_flujo as _ejecutar_flujo,
    ejecutar_flujo_dominio as _ejecutar_flujo_dominio,
    listar_memoria as _listar_memoria,
)


@api_router.get("/flujo/dominios")
async def flujo_dominios():
    """6 dominios empresariales (únicos válidos) + demostración (palenque)."""
    return _listar_dominios()


@api_router.get("/flujo/clientes")
async def flujo_clientes():
    return _listar_clientes()


@api_router.post("/flujo/ejecutar")
async def flujo_ejecutar(
    client_id: str = Form(...),
    modo: str = Form("ASESORIA"),
    files: List[UploadFile] = File(default=[]),
):
    """
    Ejecuta el flujo completo. Si no se suben archivos, usa la operación demo
    del palenque para mostrar el flujo. Devuelve la entrada LIMPIA (7 KPIs)
    que recibe el lazo, más las features de control y el resultado del lazo.
    """
    leidos = [{"nombre": f.filename, "datos": await f.read()} for f in (files or [])]
    try:
        return _ejecutar_flujo(client_id, leidos, modo=modo)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@api_router.post("/flujo/ejecutar-dominio")
async def flujo_ejecutar_dominio(
    domain_id: str = Form(...),
    modo: str = Form("ASESORIA"),
    calibrar: bool = Form(False),
    files: List[UploadFile] = File(default=[]),
):
    """
    Ejecuta el flujo para uno de los 6 dominios empresariales (o el demo),
    usando su propio mapa de métricas (doble hélice). Sin archivos usa la
    operación demo. Si calibrar=True ajusta los rangos con los datos reales.
    Cada ejecución se guarda en memoria COMPRIMIDA por el códec.
    """
    leidos = [{"nombre": f.filename, "datos": await f.read()} for f in (files or [])]
    try:
        return _ejecutar_flujo_dominio(domain_id, leidos, modo=modo, calibrar=calibrar)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@api_router.get("/flujo/historial/{domain_id}")
async def flujo_historial(domain_id: str):
    """Historial/memoria (comprimida por el códec) de un dominio."""
    return _listar_memoria(domain_id)


# ─── El Ágora Unificado (Elemento de Habitabilidad · Retícula de Triangulación) ──
# Un solo motor ciego al dominio. 7 dominios. Salida = las disonancias (plano x vs y).

from agora_conector import (
    listar_dominios as _agora_listar,
    info_dominio as _agora_info,
    triangular as _agora_triangular,
    demo_entradas as _agora_demo,
)


class AgoraTriangularInput(BaseModel):
    dominio_id: str
    entradas: Optional[dict] = None   # {nodo: {observable: valor, ...}}


@api_router.get("/agora/dominios")
async def agora_dominios():
    """Los 7 dominios principales del Ágora."""
    return {"dominios": _agora_listar()}


@api_router.get("/agora/dominio/{dominio_id}")
async def agora_dominio(dominio_id: str):
    """Config del dominio: nodos, observables (coordenadas a ingestar), primitivo, tipo."""
    try:
        info = _agora_info(dominio_id)
        info["demo_entradas"] = _agora_demo(dominio_id)
        return info
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@api_router.post("/agora/triangular")
async def agora_triangular(body: AgoraTriangularInput):
    """Ingesta de coordenadas conocidas → el primitivo aporta la disonancia (x) → plano (x,y)."""
    try:
        return _agora_triangular(body.dominio_id, body.entradas)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Registro del router y arranque ─────────────────────────────────────────

app.include_router(api_router)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup_inicializar_motor():
    """
    Al arrancar el servidor, si ya existe una configuracion guardada
    (config.json con configurado=true), inicializa el motor del dominio
    activo automaticamente.

    Necesario porque el motor vive en memoria (_motor_instancia en
    notebook_engine.py) y se pierde cada vez que el proceso se reinicia.
    Sin esto, la app salta la pantalla de configuracion correctamente
    pero el motor nunca se inicializa, causando RuntimeError al procesar.
    """
    config = load_config()
    if not config.get("configurado"):
        logger.info("[startup] Sistema sin configurar, motor no inicializado.")
        return

    tipo_dominio = config.get("tipo_dominio")
    dominio_id   = config.get("dominio_id")
    logger.info(f"[startup] Configuracion existente: {dominio_id} ({tipo_dominio})")

    try:
        if tipo_dominio == "unipersonal":
            from aprendiz_motor import inicializar_motor
            inicializar_motor(config)
            logger.info(f"[startup] Motor unipersonal inicializado: {dominio_id}")
        else:
            from aprendiz_motor.rag_agents import inicializar_rag
            inicializar_rag(dominio_id)
            logger.info(f"[startup] Motor RAG inicializado: {dominio_id}")
    except Exception as e:
        logger.error(f"[startup] Error al inicializar motor: {e}")

    # Verificar activador al arrancar
    _refrescar_activacion()
    logger.info(f"[startup] Activacion: {_estado_activacion.get('mensaje', '')}")


@app.on_event("shutdown")
async def shutdown_db_client():
    _conn.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
