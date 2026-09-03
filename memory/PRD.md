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
