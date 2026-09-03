# Segundo Producto — Motor Empresa · Elemento de Ciberseguridad (GSL)
**Documento de DISEÑO (endpoints + flujo de uso). NO es código. Aún NO se construye.**

Fecha: 2026-06 · Idioma operativo: Español · Regla soberana: 100% local (FastAPI + SQLite),
sin nube, sin terceros, sin build/deploy externo. Dashboards Gradio de los notebooks = referencia
de features a reconstruir nativamente en React + FastAPI local.

---

## 0. Alcance y decisiones del operador (confirmadas)
- Aplica **solo a las 6 empresas** (restaurante, retail, hotel, fábrica, logística, clínica).
  El palenque (dom_fermentacion_lotes_v1) sigue siendo SOLO demo y NO usa este motor.
- Las 6 empresas comparten **el mismo Aprendiz de logística** (`logistica_multiceph_bundle_v1`).
- El **Elemento de Ciberseguridad** REEMPLAZA al Elemento de Habitabilidad en este 2º producto.
  El **Elemento de Claridad** (cucurucho + agentes) permanece universal e intacto.
- Las 4 herramientas GSL quedan **disponibles como opciones**. Al seleccionar UNA se
  **despliega su dashboard** (reconstruido del Gradio) y esa herramienta tiene **su propia ingesta
  con DOS opciones**:
  1. **Desde el embudo** (cucurucho → señales, reutiliza el flujo existente).
  2. **Desde API / webhook** (nodo externo del cliente: SIEM, IAM, control de accesos).

---

## 1. Contrato geométrico común (idéntico en las 4 herramientas)
Todas siguen el mismo pipeline que ya usa Mileforum:

```
datos crudos → normalización a eventos → manifold de firma (vector 8D)
             → score de disonancia → payload estándar (to_mode2_payload)
```

- **Vector de firma 8D**: contraparte geométrica de la métrica (misma idea que la doble hélice).
- **Disonancia**: distancia al manifold de "lo normal"; umbrales `alert` / `critical`.
- **Payload estándar** hacia el Modo 2 (PolicyAdapter): `{entity_id, dissonance, event_type, timestamp, context}`.
- **Registro forense** (`ForensicRecord`): inmutable, con `sha256`, override y timestamps → esta es la
  **lista rastreable de acciones/observaciones** que administra el **Aprendiz**.

### Ingesta dual (por herramienta seleccionada)
```
POST /api/ciber/{herramienta}/ingesta
  body: { fuente: "embudo" | "api_webhook",
          cliente_id, dominio,           # una de las 6 empresas
          # si fuente=embudo: usa archivos del cucurucho ya subidos
          # si fuente=api_webhook: { formato, endpoint_url?, api_key?, payload? } }
  → { run_id, eventos_normalizados, resumen }
```
`{herramienta}` ∈ `modo1` | `modo2` | `administrativa` | `movimiento`.

---

## 2. 🛡️ Herramienta A — Modo 1 (Observación Pasiva)
**Qué hace:** solo observa. Construye el manifold de lo normal y produce un score de disonancia
continuo + reporte bimestral. No bloquea, no alerta, no interviene.

**Formatos de ingesta soportados (nodo SIEM):** Chronicle UDM · Splunk JSON · Sentinel · CEF · CSV.
**Niveles de ingesta:** 0 archivo exportado · 1 API polling (lectura) · 2 webhook/stream.

**Features del dashboard (a reconstruir en React):**
- Configuración (JSON de la org), selector de plataforma SIEM, semilla.
- Métricas bimestrales: disonancia media, máxima, ventanas ≥ umbral, extremos activos.
- Mapa de calor de disonancia, tendencia bimestral, top 20 ventanas, reporte bimestral (texto).

**Flujo de uso:**
1. Operador elige empresa (1 de 6) → selecciona herramienta "Modo 1".
2. Elige ingesta: embudo o API/webhook (SIEM).
3. Ejecuta análisis → ve manifold, disonancia y reporte bimestral.
4. No hay acciones; solo lectura. Artefactos guardados COMPRIMIDOS (códec MOCG).

**Endpoints propuestos:**
```
GET  /api/ciber/modo1/config?dominio=...           → config org + umbrales
POST /api/ciber/modo1/ingesta                       → (contrato dual §1)
POST /api/ciber/modo1/analizar                      → { run_id }
       → { disonancia_media, disonancia_max, ventanas_alerta, extremos,
           heatmap_data, tendencia_data, top_ventanas[] }
GET  /api/ciber/modo1/reporte-bimestral/{run_id}    → { markdown, scores_csv_ref }
GET  /api/ciber/modo1/manifiestos/{run_id}          → refs a manifold_*.json (comprimidos)
```

---

## 3. 🛡️ Herramienta B — Modo 2 (Respuesta Adaptativa)
**Prerequisito:** consume artefactos del Modo 1 (manifold + dissonance_scores). No reconstruye la firma.

**Qué agrega:** `PolicyAdapter` (disonancia+contexto → acción recomendada con pesos aprendidos),
motor de ejecución por **nivel** (0 solo recomienda · 1 webhook saliente · 2 API directa · 3 agente local),
**override humano en un click** (con señal de entrenamiento) y **registro forense inmutable**.

**Features del dashboard (a reconstruir):**
- Estado: registros forenses, acciones ejecutadas, overrides, correction rate, fases de sesión.
- Override / Confirmación (token del registro + admin + acción correcta).
- Disonancia por sesión (timeline), pesos del PolicyAdapter, reporte del adapter, registro forense (tabla).

**Flujo de uso:**
1. Selecciona empresa → herramienta "Modo 2" (requiere Modo 1 ejecutado ≥1 ciclo).
2. El PolicyAdapter recomienda acciones por entidad según disonancia.
3. Según el nivel activo por acción: Nivel 0 pide confirmación humana; Nivel 1 manda webhook; etc.
4. Operador puede **override** (revierte + entrena pesos) o **confirmar** (refuerza pesos).
5. Cada acción queda como `ForensicRecord` (hash sha256) → bitácora del Aprendiz.

**Endpoints propuestos:**
```
POST /api/ciber/modo2/recomendar          { entity_id, dissonance, context } → [(accion, score)]
POST /api/ciber/modo2/ejecutar            { action, entity_id, dissonance, nivel } → ForensicRecord
POST /api/ciber/modo2/confirmar           { override_token, admin } → { ok, weights }
POST /api/ciber/modo2/override            { override_token, admin, accion_correcta } → { ok, weights }
GET  /api/ciber/modo2/forense             → [ForensicRecord...]  (lista rastreable)
GET  /api/ciber/modo2/adapter/reporte     → { correction_rate, weights, markdown }
GET  /api/ciber/modo2/sesiones            → timeline disonancia por sesión
```

---

## 4. 🔑 Herramienta C — Capa Administrativa (manifold de intenciones IAM)
**Qué observa:** intenciones declaradas (no efectos): cada acción admin con autor, timestamp y objeto.
**Fuentes:** Active Directory (Event Log), Azure AD (Audit), Linux auditd, IAM genérico (JSON/CSV).
**Único diferenciador:** **autoprotección del GSL** — detecta ataques contra el propio sistema
(`gsl_protected_resources`, peso ×5). Emite `admin_anomaly` al Modo 2.

**Dimensiones del manifold:** secuencia lógica de cambios, ventana temporal sensible, coherencia
actor-objeto, duración de privilegio elevado, correlación entre capas, autoprotección del GSL.

**Features del dashboard (a reconstruir):**
- Config (org, plataforma IAM, recursos GSL protegidos, umbrales), escenario, nº eventos, ventana, semilla, dry-run.
- Métricas: eventos, registros, críticos, **auto-ataques GSL ⭐**, actores detectados.
- Línea de tiempo de disonancia por actor, radar de anomalía, grafo de permisos, registro forense + log de eventos.

**Flujo de uso:**
1. Selecciona empresa → "Capa Administrativa".
2. Ingesta embudo o API/webhook (AD/Azure/auditd/IAM).
3. Ejecuta → ve disonancia por actor, grafo de permisos y alertas de auto-ataque al GSL.
4. Anomalías se envían al Modo 2 como `admin_anomaly`.

**Endpoints propuestos:**
```
GET  /api/ciber/admin/config?dominio=...   → config + recursos GSL + umbrales + taxonomía
POST /api/ciber/admin/ingesta              → (contrato dual §1; formato ad|azure_ad|auditd|generic)
POST /api/ciber/admin/analizar             → { eventos, registros, criticos, auto_ataques_gsl,
                                               actores[], timeline_data, radar_data, grafo_data }
GET  /api/ciber/admin/forense/{run_id}     → registro forense administrativo
```

---

## 5. 🚪 Herramienta D — Capa de Movimiento (físico, privacidad por diseño)
**Dos capas:** anónima (tokens HMAC-SHA256 con sal que **rota bimestralmente**) siempre activa;
de identidad (token→persona) SOLO con **autorización dual de dos administradores**.
**Detecta:** imposible travel, secuencia inversa, badge clonado, espacio anómalo, patrón de rol roto.
Emite `movement_anomaly` al Modo 2.

**Features del dashboard (a reconstruir):**
- Config (topología del edificio), escenario, días, semilla, dry-run.
- Métricas: eventos, registros, imposible travel, solicitudes de ID, tokens activos.
- **Resolución de identidad con doble autorización** (record + admin1 + admin2).
- Mapa del edificio, trayectorias de tokens, ocupación por espacio, registro forense.

**Flujo de uso:**
1. Selecciona empresa → "Capa de Movimiento".
2. Ingesta embudo o API/webhook (lectores de badge/accesos).
3. Ejecuta → ve trayectorias/ocupación anónimas y anomalías físicas.
4. Si una anomalía sostenida supera umbral → se **solicita resolución de identidad**;
   requiere **dos admins distintos** para revelar la persona (queda en el log forense).

**Endpoints propuestos:**
```
GET  /api/ciber/movimiento/config?dominio=...   → topología edificio + umbrales + sal bimestral (ref)
POST /api/ciber/movimiento/ingesta              → (contrato dual §1)
POST /api/ciber/movimiento/analizar             → { eventos, registros, imposible_travel,
                                                    solicitudes_id, tokens_activos, mapa_data,
                                                    trayectorias_data, ocupacion_data }
POST /api/ciber/movimiento/resolver-identidad   { record_id, admin1, admin2 } → { persona, log_ref }
GET  /api/ciber/movimiento/forense/{run_id}     → registro forense de movimiento
```

---

## 6. Endpoints comunes del 2º producto
```
GET  /api/ciber/herramientas                 → [modo1, modo2, administrativa, movimiento] (opciones)
GET  /api/ciber/dominios                     → las 6 empresas (excluye palenque demo)
POST /api/ciber/aprendiz/registrar           { run_id, accion|observacion, timestamp } → bitácora
GET  /api/ciber/aprendiz/bitacora/{dominio}  → lista rastreable (acciones + variables blandas)
```
- Toda ejecución guarda artefactos **comprimidos** con el códec MOCG (como el 1er producto).
- El **Aprendiz de logística** es único y compartido por las 6 empresas; etiqueta y registra
  acciones/observaciones con timestamp, mapeadas a KPIs tradicionales.

---

## 7. Notas de reconstrucción (Gradio → React/FastAPI local)
- Cada `demo.launch()` de Gradio → una **pantalla React** (dashboard) que se despliega al
  seleccionar la herramienta. Los `gr.Plot`/`gr.Image` → datos JSON que React grafica localmente.
- Nada de `requests` a la nube en runtime del backend salvo el webhook saliente OPCIONAL del
  cliente (Modo 2 Nivel 1 / ingesta API) que el operador configura explícitamente y apunta a SU
  propia infraestructura. Sigue siendo soberano (el operador controla el endpoint).
- `pandas/networkx/plotly/gradio` de los notebooks NO se importan: se reimplementa con Python
  stdlib + numpy (como se hizo con el códec y el lazo).

## 8. Pendiente de confirmar con el operador antes de construir
- Orden de construcción de las 4 herramientas (¿empezar por Modo 1?).
- Si el "dashboard basado en Gradio" debe replicar TODAS las gráficas o un subconjunto MVP.
- Formato exacto de configuración por empresa (¿un JSON por dominio como el cucurucho?).
