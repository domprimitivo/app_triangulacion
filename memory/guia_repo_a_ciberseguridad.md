# Guía — Del repo original al Motor de Ciberseguridad (GSL)
**Referencia de las rutas, endpoints y archivos que se retiraron al instalar el Ágora.**
El motor de ciberseguridad fue **eliminado** de esta variación (el Ágora lo reemplazó como elemento
de habitabilidad). Esta guía documenta todo para **reintegrarlo en el repo original** si se desea.

> Todo era 100% local/soberano (Python + numpy puro, sin nube). Recuperable del historial de git
> (los archivos existieron hasta el commit previo al Ágora).

---

## 1. Frontend — ruta y componente
- **Ruta React**: `/ciberseguridad` en `frontend/src/App.js`.
  ```jsx
  import { CiberModo1 } from './components/CiberModo1';
  <Route path="/ciberseguridad" element={<CiberModo1 />} />
  ```
- **Componente**: `frontend/src/components/CiberModo1.jsx` (página unificada con selector de las
  4 herramientas + dashboards por herramienta). testids `ciber-*`.

## 2. Backend — módulos (en `/app/backend/`)
| Archivo | Rol |
|---|---|
| `ciber_modo1.py` | Modo 1 (Observación Pasiva): parsers SIEM, manifold firma 8D, disonancia por ventana, reporte bimestral, memoria comprimida MOCG |
| `ciber_modo2.py` | Modo 2 (Respuesta Adaptativa): PolicyAdapter, recomendación por nivel, registro forense sha256, override/confirmar |
| `ciber_admin.py` | Capa Administrativa: manifold IAM 8D, autoprotección GSL, parsers AD/Azure/auditd/genérico |
| `ciber_movimiento.py` | Capa de Movimiento: tokens HMAC anónimos, imposible-travel (Dijkstra), resolución de identidad con doble autorización |
| `ciber_ingesta.py` | Ingesta SIEM en vivo: buffer webhook (JSONL) + poll saliente (urllib) |
| `flujo/ciber/*.json` | 6 configs por empresa (users, assets, nodes SIEM, thresholds) |
| `tests/test_ciber_modo1.py`, `tests/test_ciber_v2.py` | Regresión |

## 3. Endpoints (todos con prefijo `/api`, registrados en `server.py`)

### Comunes
- `GET  /api/ciber/herramientas` → las 4 herramientas y su disponibilidad
- `GET  /api/ciber/dominios` → las 6 empresas (excluye palenque demo)

### Modo 1 — Observación Pasiva
- `GET  /api/ciber/modo1/config?dominio=<domain_id>` → org, nodos SIEM, umbrales, formatos
- `POST /api/ciber/modo1/analizar` (multipart Form: `domain_id`, `fuente`=embudo|api_webhook|ingesta_live, `payload?`, `seed`, `files[]`) → métricas, tendencia, top_ventanas, heatmap, reporte_bimestral, memoria
- `GET  /api/ciber/modo1/historial/{domain_id}` → memoria comprimida

### Modo 2 — Respuesta Adaptativa
- `POST /api/ciber/modo2/analizar` (Form igual a modo1) → forensic[], adapter{weights,correction_rate}, reporte_adapter
- `GET  /api/ciber/modo2/forense/{domain_id}`
- `POST /api/ciber/modo2/override?domain_id=<id>` (body JSON `{override_token, admin, accion_correcta?}`)
- `POST /api/ciber/modo2/confirmar?domain_id=<id>` (body JSON `{override_token, admin}`)

### Capa Administrativa
- `POST /api/ciber/admin/analizar` (Form: `domain_id`, `fuente`, `platform`=ad|azure_ad|auditd|generic, `payload?`, `seed`, `files[]`) → stats (incl. `gsl_attacks`), records (dims 8D, `gsl_self_attack`), grafo, reporte
- `GET  /api/ciber/admin/forense/{domain_id}`

### Capa de Movimiento
- `POST /api/ciber/movimiento/analizar` (Form: `domain_id`, `fuente`, `payload?`, `seed`, `files[]`) → stats (`impossible_travel`, `id_requests`), records (token TK-*), ocupacion[], reporte
- `GET  /api/ciber/movimiento/forense/{domain_id}`
- `POST /api/ciber/movimiento/resolver-identidad?domain_id=<id>` (body JSON `{record_id, admin1, admin2}` — exige 2 admins distintos)

### Ingesta SIEM en vivo
- `POST   /api/ciber/ingesta/webhook/{domain_id}` (body = array/obj de eventos SIEM) → buffer
- `GET    /api/ciber/ingesta/buffer/{domain_id}?limit=20`
- `DELETE /api/ciber/ingesta/buffer/{domain_id}`
- `POST   /api/ciber/ingesta/poll/{domain_id}` (body JSON `{url, api_key?}` — GET saliente al nodo del cliente)

## 4. Pasos de reintegración en el repo original
1. Copiar los 5 módulos `ciber_*.py` y el directorio `flujo/ciber/` (6 JSON) a `backend/`.
2. En `server.py`, añadir los `from ciber_* import ...` y el bloque de endpoints (arriba), ANTES de
   `app.include_router(api_router)`. Requiere `from fastapi import ... Body`.
3. En `App.js`, importar `CiberModo1` y registrar `<Route path="/ciberseguridad" .../>`; enlazar
   desde el menú/landing.
4. Dependencias: solo `numpy` (ya presente). Sin librerías externas.
5. Recuperación exacta del código: `git log` → localizar el commit anterior al del Ágora y extraer
   los archivos `ciber_*.py`, `CiberModo1.jsx` y el bloque de endpoints de `server.py`.

## 5. Diferencia conceptual con el Ágora (por qué se retiró)
- **Ciberseguridad (retirada)**: 4 herramientas GSL, manifold 8D + disonancia sobre eventos
  técnicos (SIEM/IAM/badges); acciones y forense.
- **Ágora (actual)**: un solo primitivo `disonancia_vs_fisico`/`coherencia_stock` por subdominio,
  triangulación reporte-vs-físico; el único output son las **disonancias** en el plano x·y.
  Ambos son "elementos de habitabilidad" alternativos sobre el mismo contenedor (cucurucho/claridad).
