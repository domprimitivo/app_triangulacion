# Mileforum — App Local Soberana (PRD)

## Regla soberana (invariante)
App 100% local: FastAPI + SQLite, sin MongoDB, sin dependencias/referencias a terceros,
sin build/deploy en ninguna plataforma. Cambios puntuales; no reconstruir; mantener
intacto el resto de funciones. Almacenamiento de archivos en disco local (nunca nube).

## Implementado

### 1) Pantalla de Claridad — Lazo genérico (2026-09-02)
- `backend/lazo_generico.py`: puerto fiel del notebook (evaluar_kpis, detectar_autoengano,
  sugerir_geodesica, lazo_asesoria, lazo_agencia). Endpoints `GET /api/lazo/dominio`,
  `POST /api/lazo/evaluar`. Frontend `/claridad`. Testeado 100%.
- REDISEÑO (2026-09-02): paleta arquitectónica (ladrillo/cielo/césped/arena). KPIs 100%
  gráficos = SEMÁFORO (verde/amarillo/rojo), sin nombres ni números. "Geodésicas" →
  "Trayectorias": único texto; oculto hasta que el usuario lo CONVOCA (indicador que
  pulsa), o automático cuando el backend marca CÉNIT (requiere_cenit) con estilo de alta
  atención (ladrillo). Distinción gráfica/baja-atención vs texto/alta-atención. Testeado 100%.

### 2) Activador / Validador (verificado, sin cambios de código)
- La verificación en `server.py` (`verificar_activador`, `_generar_firma`) coincide
  EXACTAMENTE con `generar_activador.py` (referencia externa del operador):
  clave `mileforum-prudential-2026-clave-privada-antonio`, HMAC-SHA256 sobre
  `json.dumps(campos, sort_keys=True, ensure_ascii=False)` sin el campo `firma`.
- Probado: válido→activo; firma alterada / cliente_id ajeno / vencido→rechazado.
- La generación NO está en la app (solo verificación). `mileforum_activador.json` de
  prueba está ligado al cliente_id de esta máquina de preview.

### 3) Compresión Geométrica — Códec MOCG (2026-09-02)
- `backend/compresion_geometrica.py` (Python puro + numpy; sin gradio/plotly/scipy):
  clasifica por contenido, normaliza a eventos, manifold incremental 8D, comprime en
  3 capas (íntegra lossless / inferible PCA2 / geométrica) + reporte de forma con
  anomalías. `comprimir`, `descomprimir` (exacto, sha256), `es_paquete_comprimido`.
- Endpoints: `POST /api/compresion/toggle` (alterna: comprime, o descomprime si se
  sube un paquete MOCG_CODEC_V1) y `POST /api/compresion/sistema/{dominio}` (comprime
  carpetas del sistema: aprendiz_data, bundles, session_files, bimestral_package).
- Frontend `/archivos` (`ArchivosEmbudo.jsx`): subida de archivos, botón
  "Procesar con el embudo" (RAG: expedientes/documentos/procesar) y botón único
  "Comprimir / Descomprimir". Testeado 100% (round-trip lossless).

### Modo del lazo (hardcodeado)
- Constante `MODO_LAZO = 'ASESORIA'` en `frontend/src/components/ArchivosEmbudo.jsx`.
  Para otro repo/build cambiar a `'AGENCIA'` en esa línea (comentada).

### 4) Flujo de KPIs — Cucurucho → 7 KPIs → Lazo (2026-09-02)
- `backend/flujo_kpis.py`: cliente→dominio→cucurucho. El embudo (AG3 limpiador +
  AG5 ingeniero de features) SEPARA los 7 KPIs holográficos + features de control
  (c_viabilidad, firmeza_suelo_R, delta_coherencia) desde archivos de operación
  (cosecha, pagos, etc.) y entrega ENTRADA LIMPIA al lazo. Sin archivos → usa la
  operación demo del palenque.
- Config en `backend/flujo/`: clientes/, dominios/, params/ (parametrización palenque),
  cucurucho/cucurucho_base_v1.json. 6 dominios empresariales = únicos válidos; palenque
  (dom_fermentacion_lotes_v1) es SOLO demostración (es_demo).
- Endpoints: `GET /api/flujo/dominios`, `GET /api/flujo/clientes`, `POST /api/flujo/ejecutar`.
- Frontend: sección "Observación · Cucurucho → Métricas" en `/archivos` (selector de cliente,
  botón "Preparar las métricas y ejecutar la observación", muestra cada métrica geométrica
  (semáforo) EN ARMONÍA con sus datos tradicionales/discretos + control + trayectoria).
  Lenguaje técnico: KPIs=nombre interno → "métricas"; lazo → "observación". Cucurucho+agentes
  = elemento de claridad (universal); semáforo/trayectoria = elemento de habitabilidad
  (variará más adelante). Backend expone `metricas_discretas` (dato discreto ↔ geométrico).

## Estilo / Paleta (2026-09-02)

### 5) Doble hélice por dominio — 7 métricas para los 6 tipos de empresa (2026-09-02)
- Cada `cucurucho_{sector}_v1.json` en `/app` (main) se amplió con `mapa_metricas`
  (categorias_operacion + kpi_map + demo_operacion) que define qué significa cada una de
  las 7 métricas geométricas para ese dominio (restaurante, retail, hotel, fábrica,
  logística, clínica). Así cada uno tiene su doble hélice: dato tradicional (discreto) ↔
  contraparte geométrica, y entrega el input necesario al elemento de habitabilidad.
- Backend `flujo_kpis.py`: `cargar_mapa_dominio` lee el `mapa_metricas` del cucurucho en
  main; `ejecutar_flujo_dominio(domain_id,...)`. Endpoint `POST /api/flujo/ejecutar-dominio`.
- Frontend `/archivos`: selector `flujo-dominio-select` (6 empresariales + demo palenque);
  ejecutar por dominio muestra las 7 métricas (semáforo + valor + detalle discreto) + control
  + trayectoria. Elemento de claridad (cucurucho+agentes) universal e intacto. Testeado 100%
  (pytest parametrizado + Playwright).
- Paleta arquitectónica (ladrillo/cielo/césped/arena) en `/claridad` y `/archivos`.
- Marca de agua `Watermark.jsx` (acuarela clara de las dos épocas + cielo, degradada).

## Cambios de infraestructura (sin alterar comportamiento)
- `backend/local_storage.py`: helper de persistencia local (disco), usado por las
  subidas para centralizar la escritura. Comportamiento idéntico (archivos locales).
- `backend/app/db/sqlite_db.py`: reparado docstring corrupto (comilla triple sin cerrar).
  Archivo huérfano (no importado por nadie).

## Pruebas
- iteration_2.json (lazo) OK; iteration_3.json (compresión) OK. Backend/Frontend 100%.
- Tests: `backend/tests/test_lazo.py`, `backend/tests/test_compresion.py`.

## Backlog / Next

### 6) Calibración real + columnas reales + memoria comprimida (2026-09-02)
- **Auto-calibración**: `POST /api/flujo/ejecutar-dominio` acepta `calibrar=true`; ajusta los
  rangos de normalización de cada métrica con el min/max observado en los archivos reales
  (el semáforo refleja la operación exacta). Devuelve `calibracion.rangos` aplicados.
- **Columnas reales**: `_mapear_columnas` + `SINONIMOS` mapean nombres reales de columnas
  (occupancy→ocupacion_pct, otif, ventas, etc.) a las señales esperadas por dominio; ya no
  depende del demo cuando se suben archivos.
- **Memoria comprimida**: cada ejecución se guarda automáticamente COMPRIMIDA por el códec
  MOCG en `backend/flujo/memoria/{domain_id}/`. Endpoint `GET /api/flujo/historial/{domain_id}`.
  Frontend muestra checkbox "Calibrar", etiqueta de memoria (ratio) e historial. Testeado.

- P2: Pantalla de configuración inicial en React (hoy el sistema no está "configurado",
  por eso el embudo RAG pide configuración). El flujo real vive en el exe Flutter.
- P2: Descarga directa del paquete/archivos del sistema comprimido desde /archivos.

## SEGUNDO PRODUCTO — Motor Empresa · Elemento de Ciberseguridad (GSL) — DISEÑO (2026-06)
> Estado: **DEFINIDO, NO CONSTRUIDO**. Detalle completo (endpoints + flujo de uso) en
> `/app/memory/segundo_producto_diseno.md`.

- **Alcance:** solo las **6 empresas** (no el palenque demo). Comparten el **mismo Aprendiz de
  logística**. El **Elemento de Ciberseguridad reemplaza al de Habitabilidad**; el Elemento de
  Claridad (cucurucho+agentes) sigue universal.
- **4 herramientas GSL** (analizadas de los notebooks, se reconstruyen nativas en React/FastAPI
  local, sin gradio/pandas/plotly/networkx; el `demo.launch` de cada Gradio → una pantalla React):
  1. **Modo 1 — Observación Pasiva:** solo observa; manifold 8D + disonancia + reporte bimestral;
     ingesta SIEM (Chronicle/Splunk/Sentinel/CEF/CSV).
  2. **Modo 2 — Respuesta Adaptativa:** consume Modo 1; PolicyAdapter + ejecución por nivel (0-3)
     + override humano + **registro forense inmutable** (ForensicRecord sha256) = lista rastreable.
  3. **Capa Administrativa:** manifold de intenciones IAM (AD/Azure/auditd/genérico); autoprotección
     del GSL (detecta ataques al propio sistema); emite `admin_anomaly` al Modo 2.
  4. **Capa de Movimiento:** badges/espacios con tokens anónimos (HMAC, sal bimestral) + resolución
     de identidad con **doble autorización**; emite `movement_anomaly` al Modo 2.
- **Ingesta dual por herramienta seleccionada:** (a) desde el **embudo** (cucurucho) o
  (b) desde **API/webhook** externo del cliente. Contrato: `POST /api/ciber/{herramienta}/ingesta`.
- **Contrato común:** manifold 8D → disonancia → payload → PolicyAdapter (Modo 2). Artefactos
  guardados COMPRIMIDOS (códec MOCG). Bitácora del Aprendiz: `/api/ciber/aprendiz/*`.
- **Pendiente antes de construir:** orden de construcción (¿Modo 1 primero?), alcance de gráficas
  (MVP vs completo), formato de config por empresa. Ver §8 del documento de diseño.

### CONSTRUIDO — Herramienta A: GSL Modo 1 (Observación Pasiva) (2026-06)
> Estado: **IMPLEMENTADO Y TESTEADO 100%** (backend + frontend). iteration_7.json.
- Motor `backend/ciber_modo1.py` (numpy puro, sin pandas/plotly/gradio): parsers SIEM
  (Chronicle UDM · Splunk · Sentinel · CEF · CSV), generador sintético demo, manifold de
  firma 8D por extremo, disonancia ponderada por ventana temporal (2h), reporte bimestral,
  memoria comprimida con códec MOCG.
- **Ingesta dual** (decisión del usuario): `fuente=embudo` (archivos del cucurucho; sin archivos →
  operación demo sintética por config) o `fuente=api_webhook` (payload SIEM inline JSON/CEF).
- **Config: un JSON por dominio** en `backend/flujo/ciber/{domain_id}.json` (6 empresas, temáticas
  por sector: users/assets/nodes/thresholds). Palenque demo EXCLUIDO.
- **Alcance dashboard (valor vs peso, decidido):** tarjetas de métricas, tendencia bimestral (línea
  SVG), mapa de calor por extremo, top-20 ventanas (tabla), reporte bimestral (texto). Sin gráficas
  pesadas sin datos nuevos.
- Endpoints: `GET /api/ciber/herramientas` (4 opciones; modo1 activo, resto "próximamente"),
  `GET /api/ciber/dominios` (6 empresas), `GET /api/ciber/modo1/config?dominio=`,
  `POST /api/ciber/modo1/analizar` (Form: domain_id, fuente, payload?, seed, files[]),
  `GET /api/ciber/modo1/historial/{domain_id}`.
- Frontend `frontend/src/components/CiberModo1.jsx`, ruta `/ciberseguridad`. Selector de 4
  herramientas + empresa + toggle de ingesta. testids `ciber-*`. Regresión:
  `backend/tests/test_ciber_modo1.py`.
- **Próximo:** Modo 2 (Respuesta Adaptativa: PolicyAdapter + acciones por nivel + registro
  forense = lista rastreable del Aprendiz). Luego Capa Administrativa y Capa de Movimiento.

### CONSTRUIDO — Herramientas B, C, D + Ingesta SIEM en vivo (2026-06)
> Estado: **IMPLEMENTADO Y TESTEADO 100%** (backend 13/13 + frontend). iteration_8.json.
> Regresión: `backend/tests/test_ciber_v2.py`. Las 4 herramientas GSL ya están activas.
- **Modo 2 — Respuesta Adaptativa** (`ciber_modo2.py`): consume la disonancia del Modo 1;
  `PolicyAdapter` (pesos por bucket, aprende), recomendación de acciones con nivel (0-3),
  **registro forense inmutable** (sha256) = lista rastreable; override/confirmar humano con
  señal de entrenamiento (correction_rate). Estado persistido por dominio en
  `flujo/ciber_modo2/{domain}.json`. Endpoints `/api/ciber/modo2/{analizar,forense/{id},override,confirmar}`.
- **Capa Administrativa** (`ciber_admin.py`): manifold IAM 8D (off_hours, critical, seq_viol,
  priv_dur, obj_divers, gsl_touch, fail_rate, centrality); parsers AD/Azure/auditd/genérico;
  **autoprotección GSL** (detecta auto-ataques al propio sistema, peso ×5). Forense por dominio.
  Endpoints `/api/ciber/admin/{analizar,forense/{id}}`.
- **Capa de Movimiento** (`ciber_movimiento.py`): tokens anónimos HMAC-SHA256 (sal bimestral),
  firma badge 7D, detección de imposible-travel (Dijkstra sobre grafo del edificio), rol roto,
  ocupación anómala; **resolución de identidad con doble autorización** (2 admins distintos).
  Endpoints `/api/ciber/movimiento/{analizar,forense/{id},resolver-identidad}`.
- **Ingesta SIEM en vivo** (`ciber_ingesta.py`): receptor **webhook** (push del nodo del cliente
  → buffer JSONL local por dominio) + **poll** saliente (GET Nivel 1 con urllib stdlib) +
  fuente `ingesta_live` en Modo 1/2 que consume el buffer. Endpoints
  `/api/ciber/ingesta/{webhook/{id}(POST),buffer/{id}(GET/DELETE),poll/{id}(POST)}`.
- **Frontend** unificado `CiberModo1.jsx` (`/ciberseguridad`): selector de las 4 herramientas;
  Modo 1/2 con 3 fuentes (embudo/api_webhook/en vivo), Admin/Movimiento con 2; dashboards por
  herramienta (forense con confirmar/override, autoataque GSL, ocupación, resolución dual).
  Motores en Python+numpy puro (sin pandas/networkx/gradio), soberanos y locales.

## SIGUIENTE VARIACIÓN — Insertar el "elemento de habitabilidad" en un SISTEMA INTEGRAL (2026-06)
> Estado: **DEFINIDO, NO CONSTRUIDO**. Diagnóstico buyer-journey confirmado con el usuario.
> La conversación se resume aquí para avanzar a esta variación.

### Idea central: el sujeto tiene 3 caras bajo la MISMA empresa
Al seleccionar una empresa, el sujeto es a la vez **agente de ciberseguridad + empleado + persona**.
Las 3 caras alimentan un mismo lugar, y el **elemento de habitabilidad = las herramientas**
(en Producto 1 = semáforo/trayectoria; en Producto 2/empresa = las 4 herramientas GSL de
ciberseguridad). "Variar e insertar la habitabilidad" = mostrarla como **salida ordenada dentro
de un panel empresa-céntrico**, alimentada por los 3 flujos, no como ruta aislada.

### Las 3 entradas (flujos) que deben converger y ordenarse en el mismo lugar
1. **Cara agente (técnica)** → SIEM / permisos → herramientas GSL (YA construido, hoy en `/ciberseguridad`).
2. **Cara empleado** → archivos de empresa / **correos internos** → embudo RAG (existe en `/archivos`,
   falta etiquetarlo como flujo "empleado / correos internos").
3. **Cara persona** → **campo de escritura libre**: el buyer pega texto de WhatsApp con etiqueta
   **"nuevo contacto"** → el **Aprendiz sugiere "verificar confiabilidad"** (100% local/heurística,
   pendiente confirmar). **NO existe** aún (ni UI ni backend).

### Cómo se INSERTA/VARÍA el elemento de habitabilidad (plan)
- **Registro paralelo unificado por empresa**: una bitácora única (gestionada por el Aprendiz) que
  ordena con timestamp los 3 flujos en paralelo (técnico ↔ empresa/correos ↔ persona/confiabilidad).
- **Panel empresa-céntrico ("mismo lugar")**: al elegir la empresa se ven las 3 caras + las
  herramientas (habitabilidad) integradas como parte del todo. La habitabilidad se "inserta" como
  el resultado ordenado y navegable que emerge de los 3 flujos, coherente con la observación
  (elemento de claridad universal) que ya separa métrica discreta ↔ contraparte geométrica.
- **Variación del contenido de habitabilidad según producto**: unipersonal → semáforo/trayectoria;
  empresa → ciberseguridad. Mismo contenedor integral, distinto elemento de habitabilidad insertado.

### Huecos a cerrar (prioridad)
- P0: Campo "nuevo contacto" (texto libre) + sugerencia de confiabilidad del Aprendiz (local).
- P0: Registro paralelo unificado por empresa (bitácora del Aprendiz sobre los 3 flujos).
- P1: Panel empresa-céntrico que inserta la habitabilidad (herramientas) como parte del sistema.
- P2: Etiquetar la cara "empleado" del embudo RAG como flujo de correos internos.

### Pendiente de confirmar antes de construir
- Confiabilidad: 100% local/heurística (esperado por soberanía) — falta OK explícito.
- Panel integral: pantalla nueva vs. integrarlo en `/ciberseguridad`.
- Pantalla de inicialización: sigue en el exe Flutter (no en este React); aquí solo tocamos "empresas".

---

## Actualización 2026-09-09 — Ajuste Bimestral Automático (Feature Aprendiz)

**Objetivo:** Portar la lógica del notebook `Mileforum_Aprendiz_Ajuste_Bimestral_v0_1.ipynb` (fine-tune del PolicyAdapter) al backend y ejecutarla automáticamente cada 50 días desde la activación del cliente. El modelo ajustado reemplaza al original en su lugar dentro del bundle activo.

**Implementado:**
- `aprendiz_motor/bimestral_ajuste.py`: port fiel del notebook (carga bundle, learning_log en ventana, samples con pesos prudenciales, catálogo+allowlist por fase, entrenamiento PolicyAdapter con PyTorch CPU, artefactos + reporte). `_reemplazar_policy_in_place()` inyecta `policy/{policy_adapter.pt, allowed_actions_by_phase.json, policy_meta.json}` dentro del bundle activo, con respaldo `.bak` y sanity-check estructural (testzip + backbone) antes del reemplazo atómico.
- `aprendiz_motor/scheduler.py`: `ProgramadorBimestral` (APScheduler BackgroundScheduler) que corre cada 6h y dispara el ajuste del período de 50 días pendiente desde `emitido_en` del activador. Soporta catch-up e idempotencia por `period_index`.
- `server.py`: tabla `ajuste_bimestral_runs`; endpoints `GET /api/bimestral/ajuste/estado`, `POST /api/bimestral/{dominio}/ajuste/ejecutar`, `GET /api/bimestral/{dominio}/ajuste/historial`; arranque del scheduler en startup.
- Dependencias añadidas: `torch` (CPU), `apscheduler`.

**Verificado:** 7/7 pruebas backend (testing agent, iteration_11) — estado, ejecución con entrenamiento real + reemplazo in-place + respaldo + integridad de bundle, historial, caso datos insuficientes, y lógica del scheduler.

**Backlog / Próximos:**
- Extraer endpoints bimestral a un router propio (server.py grande).
- Persistir `last_tick_at` del scheduler para observabilidad.
- UI en Flutter/React para mostrar estado del próximo ajuste y disparo manual.

## Actualización 2026-09-09 — Cucurucho como EMBUDO ÚNICO (KPIs ∥ Ágora)

**Objetivo (confirmado por el usuario):** el cucurucho es el embudo único; de UNA sola
ingesta de archivos de operación prepara EN PARALELO (a) el bundle de KPIs holográficos
(elemento de claridad, ya existía, intacto) y (b) las coordenadas LIMPIAS para la
triangulación del Ágora (elemento de habitabilidad). "Todo pasa por el cucurucho".

**Implementado (aditivo, sin romper nada, sin tocar frontend):**
- `cucurucho_embudo.py` (nuevo): `preparar_agora(domain_id, archivos)` → base = `demo_entradas`
  del dominio Ágora; AG3 limpia/agrega columnas de los archivos (por keyword de nombre de
  archivo) y sobreescribe observables según `mapa_agora.columnas`; llama a `triangular` y
  agrega `preparacion{dominio_agora, senales_agora, observables_aplicados, n_aplicados}`.
  `except Exception` → None (el Ágora es aditivo, no compromete el bundle KPIs).
- `flujo_kpis.py::ejecutar_flujo_dominio`: al final llama a `preparar_agora` (import perezoso)
  y agrega el campo `agora` a la respuesta. Todos los campos previos + memoria comprimida
  (archivos de agentes) se CONSERVAN.
- Config: cada `cucurucho_{hotel,restaurante,retail,fabrica,logistica,clinica}_v1.json` ganó
  el bloque `mapa_agora` (dominio_agora + categorias_operacion + columnas → observables del
  `dominio_{sector}.json` del Ágora). Nuevo `cucurucho_gobierno_v1.json` (mapa_metricas +
  mapa_agora) para continuidad (gobierno existía solo en el Ágora).
- Continuidad verificada: hotel → embudo → AG3 limpia (compras + actividad) → 13 observables
  aplicados → triangula → historial del Ágora actualizado. Los 6 dominios + gobierno sin errores.

**Verificado:** 12/12 pruebas backend (testing agent, iteration_12). Sin bugs.
Detección de categoría por NOMBRE de archivo (keywords), comportamiento heredado del sistema.

**Backlog / Próximos:**
- (Opcional, requiere OK) mostrar la salida `agora` del embudo en `/archivos` (hoy el frontend
  la recibe pero no la pinta; el usuario pidió NO tocar frontend).
- Bimestral: extraer endpoints a router propio; persistir `last_tick_at`.

## Actualización 2026-09-09 — Infraestructura de EMPAQUETADO FINAL (.exe Windows)

**Objetivo:** archivos de infraestructura para empaquetar el backend como ejecutable único
(PyInstaller) y orquestar backend + interfaz Flutter en Windows. Rutas robustas frozen-aware
para BD y modelos que persisten en disco.

**Implementado:**
- `backend/runtime_paths.py` (nuevo): `get_base_dir()` (carpeta PERSISTENTE: `Path(sys.executable).parent`
  si `sys.frozen`, si no la carpeta de `backend/`) y `get_resource_dir()` (`sys._MEIPASS`).
- Rutas de datos/modelos ahora usan `get_base_dir()` preservando estructura (comportamiento IDÉNTICO
  en dev): `server.py` (ROOT_DIR/`mileforum.db`, ya lo era), `flujo_kpis.py` (BASE + MAIN_DIR),
  `agora_conector.py` (BASE), `aprendiz_motor/{notebook_engine,bundle_loader,bimestral_ajuste}.py`
  (modelos y `data/modelos`). Se eliminó el `Path("data/modelos")` relativo a CWD (bug latente).
- `backend/build_backend.bat` (nuevo): PyInstaller `--onefile --name mileforum_backend` con
  hidden-imports de módulos importados de forma perezosa + `--collect-submodules aprendiz_motor/uvicorn/apscheduler`
  + `--collect-all torch`. Ensambla `dist\Mileforum\` con el layout operativo: `backend\mileforum_backend.exe`
  + carpetas de datos junto al exe, `cucurucho_*.json` en `backend.parent` (= raíz del paquete),
  `Iniciar_App.bat` y `app\` para el exe de Flutter. Los datos NO se embeben (el Aprendiz reescribe
  modelos in-place y el operador edita los cucurucho → deben ser persistentes en disco).
- `Iniciar_App.bat` (raíz del proyecto, nuevo): arranca `mileforum_backend.exe` minimizado, espera
  a `http://127.0.0.1:8001/api/` (poll con PowerShell, hasta 30s), lanza `app\mileforum_app.exe`
  (Flutter) con `/wait`, y al cerrar la interfaz hace `taskkill mileforum_backend.exe /F`.

**Nota:** los `.bat` son entregables Windows (no ejecutables en el contenedor Linux). El refactor
de rutas Python fue verificado (imports OK + endpoints agora/embudo responden tras reinicio).
Diferencias vs plantilla original: BD = `mileforum.db` (no aprendiz.db); modelos = `.pt` en bundles
(no `.npz`); "catalogs/models" → `flujo/`+`cucurucho_*.json` y `bundles/`+`aprendiz_motor/modelos/`.
