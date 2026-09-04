# Nuevo Elemento de Habitabilidad — EL ÁGORA UNIFICADO (Retícula de Triangulación)
**Documento de DEFINICIÓN. NO es código. Aún NO se construye.** · 2026-06 · Español · 100% local/soberano.

> Esta variación define el **elemento de habitabilidad** como una **retícula de triangulación**:
> un solo primitivo aplicado por subdominio vía configuración JSON. Sustituye, en esta variación,
> a los elementos de habitabilidad anteriores (semáforo/trayectoria · ciberseguridad) como el
> contenido que se inserta en el contenedor integral. El **elemento de claridad** (cucurucho +
> agentes, universal) sigue intacto y es quien alimenta la retícula.

---

## 0. Alcance (confirmado por el usuario)
- **6 empresas** de siempre + **dominio adicional GOBIERNO** = dominios principales de esta variación.
- El dominio se fija en la **primera pantalla del Ágora** y NO se cambia a mitad de flujo
  (cambiarlo requiere reiniciar el sistema).

## 1. La idea (qué es la nueva habitabilidad)
Los notebooks de triangulación no son piezas sueltas: son **instancias del mismo primitivo**
aplicado a distintos subdominios. El Ágora los unifica:
- **No** un notebook por nodo → **una configuración por subdominio** (qué anclas y qué observables).
- Cada dominio principal tiene **subdominios**, y cada subdominio tiene sus **nodos de triangulación**.
- Un **único motor**: `disonancia_vs_fisico` (+ `coherencia_stock` para stock). Los subdominios
  solo aportan **parámetros** (JSON), no lógica nueva.

## 2. Primera pantalla del Ágora (define el dominio principal)
Radios de selección del dominio principal → botón **CONFIRMAR DOMINIO**. Al confirmar, el Ágora carga:
- `dominio_<seleccion>.json` (config principal + KPIs + geodésicas)
- `subdominios_<seleccion>.json` (subdominios, observables, ancla, avance)
- el **primitivo de triangulación** correspondiente
y prepara los **7 KPIs de Cantor Inverso** del dominio.

## 3. Estructura de archivos
### 3.1 `dominio_<x>.json` (principal)
`dominio`, `_descripcion`, `primaria` (p.ej. "dinero"), `triangulacion` (p.ej. "externa_dinero"),
`coordenada_compartida` (y = marcador de red de proveedores 69-B/SAT: `y_senal`, `y_gamma`,
`gamma_default`), `kpis` (los 7), `geodesicas` (gamma_0..gamma_5).

### 3.2 `subdominios_<x>.json`
Por subdominio: `descripcion`, `tipo` (flujo|stock|ancla|blanda), `observables[]`,
`ancla{ primitivo, params }`, `avance{ numerador, denominador }` (o `null` si no aplica).

### 3.3 GOBIERNO (archivo subido = autoritativo)
`dominio_gobierno.json` es el dominio de **FRAUDE** (flujo de dinero público). Centro de gravedad =
manejo del dinero (conexión al exterior/caja). Triangulación **externa contra la coordenada dinero
(marcador 69-B, SAT)**. Nodos:
- **agua** (flujo, soporte_gasto): ancla `disonancia_vs_fisico` — reportado `volumen_extraido_m3`
  vs físico `energia_kwh` (fisico_factor 2.2222, orientación `fisico_excede`, div 0.20, peso 1.0).
  Avance = m³/kWh. *("se maquilla el volumen, no los kWh").*
- **nomina** (flujo, soporte_gasto): reportado `plazas_pagadas` vs físico `servicio_real`
  (fisico_factor 0.0333, `reportado_excede`, div 0.20, peso 0.8, sec `concentracion_cuentas` 0.2).
  Avance = servicio/plazas. *(el aviador no produce servicio ni deja asistencia).*
- **catastro** (stock, soporte_activo): primitivo `coherencia_stock` — activo `valor_mercado` vs
  justificación `ingreso_declarado` (div 0.8, peso 1.0). Sin avance (es stock).
- Cada nodo importa la **coordenada_y** (69-B) con su `gamma`.

## 4. Los dos primitivos (a implementar en Python local; hoy NO existe `conector.py`)
- **`disonancia_vs_fisico`**: mide la brecha entre lo reportado y la huella física infalsificable.
  Params: `reportado`, `fisico_obs`, `fisico_factor`, `orientacion` (`reportado_excede`|`fisico_excede`),
  `div`, `peso`, `sec_obs?`, `sec_peso?`.
- **`coherencia_stock`**: coherencia de acumulación (activo vs justificación). Params: `activo`,
  `justificacion`, `div`, `peso`.

## 5. Método de la triangulación (guía de aristas) — las 6 preguntas
1) Reporte vs realidad · 2) Qué se triangula (ancla x infalsificable) · 3) Qué es avance
(throughput, se lee en la derivada; su desaceleración = atascamiento antes del sumidero) ·
4) Contra qué (coordenada y = dinero + otras aristas, coherencia en cuadrantes) · 5) Frecuencia
(continua no-anunciada dispara a la periódica anunciada) · 6) Epistemología (orienta, no acusa;
espacio de token, no identidad; la ancla entra con su γ).

### Tipología de aristas (NO forzar avance donde no lo hay)
- **Flujo/throughput** → tiene avance (output÷recurso). *agua, nómina, obra, housekeeping.*
- **Stock/coherencia** → sin throughput; coherencia acumulación vs justificación. *catastro.*
- **Ancla/verificación** → confirma otra arista; sin avance ni x propia. *vigilancia, energía pura.*
- **Blanda/orientadora** → continua, multipersona, sin prueba; **apunta la auditoría**.
  *rotación de personal, ambiente laboral / tensor de confianza.*

## 6. Salida de la habitabilidad (cómo se "ve" y se inserta) — REVISADO
- **El ÚNICO output de la triangulación son las DISONANCIAS.** NO hay mapeo a KPIs, NO hay
  "7 KPIs de Cantor Inverso", NO hay geodésicas. Se elimina todo eso de esta variación.
- **Flujo del Ágora (sin pantalla de selección):** el Ágora NO necesita primera pantalla de
  selección de dominio; pasa **directo a la ingesta de las coordenadas conocidas** de cada
  subdominio/nodo (los observables: reportado, físico, y_senal, y_gamma, etc.) → el primitivo
  **aporta la coordenada desconocida = la disonancia** → **gráficas** (plano de coordenadas /
  disonancia por nodo).
- Por nodo con `tipo=flujo` se calcula además el **avance** (numerador÷denominador) donde aplica;
  en `stock` (catastro) solo coherencia; en `ancla`/`blanda` no hay avance.
- **Inserción en el sistema integral**: el cucurucho (claridad, universal) entrega las coordenadas
  conocidas; la **habitabilidad = las disonancias + sus gráficas** que emergen de la triangulación
  por subdominios. Mismo contenedor integral; el contenido de habitabilidad ahora es la retícula.

## 7. DECISIONES CERRADAS (respuestas del usuario) y lo que falta
Decisiones:
1. **7 dominios principales**: las 6 empresas (INCLUYE fábrica) + gobierno. El usuario subirá los
   6 JSON de dominios faltantes (puede subirlos **por partes**).
2. **La triangulación REEMPLAZA a la ciberseguridad** como elemento de habitabilidad. **Nada de la
   ciberseguridad permanece** en esta variación: solo triangulación. (Al construir, retirar el
   módulo de ciberseguridad como habitabilidad.)
3. **Configs las aporta el usuario** (dominio_<x>.json + subdominios/nodos por dominio).
4. **Sin KPIs ni Cantor Inverso**: el único output es la **disonancia** (+ avance donde aplique).
5. **Sin pantalla de selección del Ágora**: va directo a **ingesta de coordenadas conocidas →
   disonancia (coordenada desconocida) → gráficas**.

Falta antes de construir:
- **A) Definición exacta de los primitivos** `disonancia_vs_fisico` y `coherencia_stock`
  (el JSON de gobierno dice "ya existe en conector.py", pero NO tenemos `conector.py`).
  → Necesito que el usuario suba `conector.py` (o la fórmula) para portarlo FIEL, sin inventar.
- **B) Los 6 dominios restantes** (hotel, clínica, restaurante, retail, logística, fábrica),
  cada uno con su `dominio_<x>.json` y su archivo de subdominios/nodos. El usuario los subirá por partes.

---

## ✅ CONSTRUIDO Y TESTEADO (2026-06) — iteration_9.json (backend 12/12 + frontend, sin issues)
- **REEMPLAZA a la ciberseguridad**, eliminada por completo (ciber_*.py, /ciberseguridad, flujo/ciber*, tests).
- Motor `backend/agora_conector.py` = puerto FIEL de `conector.py` (ciego al dominio). Primitivos:
  `disonancia_vs_fisico`, `coherencia_stock`, y los 3 de fábrica (`saturacion`, `deuda_backlog`,
  `deficit_acoplado`, fórmulas confirmadas). Python+numpy puro.
- 7 dominios en `backend/flujo/agora/dominio_*.json`. 6 externos (dinero/69-B) + fábrica interna
  (y por `deficit_acoplado`, nodos blandos que orientan sin x).
- Flujo: ingesta de coordenadas conocidas → disonancia (x) → plano (x vs y). Sin KPIs/Cantor/geodésicas.
- Endpoints: `GET /api/agora/dominios`, `GET /api/agora/dominio/{id}`, `POST /api/agora/triangular`.
- Frontend `Agora.jsx` en `/agora`. Regresión: `backend/tests/test_agora.py`.

