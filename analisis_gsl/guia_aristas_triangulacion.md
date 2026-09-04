# Guía — cómo caracterizar una arista de triangulación
### Qué se triangula y qué es *avance*

Para incorporar cualquier dominio nuevo a la retícula hay que definir dos cosas: **qué se triangula** (la coordenada/ancla `x`) y **qué es avance** (el throughput del dominio, cuya desaceleración es el *atascamiento antes del sumidero*). Esta guía da el método para encontrarlas y una tipología, porque **no todas las aristas son del mismo tipo** —y en algunas "avance" no aplica.

---

## El método — las seis preguntas a cualquier arista

1. **Reporte vs realidad.** ¿Cuál es la afirmación falsificable (A, B) que hace el nodo, y qué realidad *debería* haber producido? (facturas ↔ obra; plazas ↔ servicio; volumen ↔ agua entregada)
2. **Qué se triangula (ancla `x`).** ¿Qué huella infalsificable deja esa realidad? Prueba de fuerza: *¿puede el actor falsificarla sin arrastrar a otro nodo o dejar una traza de segundo orden?* Si sí → es débil (umbral, sirve para cribar). Si no → es fuerte (física o multipersona).
3. **Qué es avance.** ¿Cuál es el trabajo útil del nodo por unidad de recurso, medido por **cambio real de estado del mundo** (no por auto-reporte)? Se lee sobre la **derivada**: su desaceleración es el atascamiento.
4. **Contra qué triangula.** La coordenada `y` (dinero) y las otras aristas; se lee la coherencia en el plano (cuadrantes).
5. **Frecuencia.** ¿Periódica y anunciada (gameable) o continua y no anunciada (infalsificable por cronometraje)? Usa la continua para **disparar** la periódica.
6. **Epistemología.** Orienta, no acusa; espacio de token, no identidad; la ancla entra con su `γ`.

---

## Tipología de aristas

No fuerces "avance" donde no lo hay. Cuatro tipos:

- **Flujo / throughput** — tienen avance natural (output ÷ recurso), leído en la derivada. *agua, nómina, obra, housekeeping.*
- **Stock / coherencia** — no hay throughput; se leen como coherencia de acumulación vs justificación. *catastro, declaraciones patrimoniales.*
- **Ancla / verificación** — confirman la afirmación de otra arista; no tienen avance propio ni x propia. *vigilancia (footage), energía como ancla pura.*
- **Blanda / orientadora** — continuas, multipersona, sin prueba; **apuntan la auditoría**, no triangulan a un valor. *rotación de personal, ambiente laboral / tensor de confianza.*

---

## Cómo encontrarlas en la práctica (heurística corta)

- **El ancla `x` se encuentra siguiendo la conservación.** El reporte afirma que algo se produjo o se movió; el ancla es la medición *independiente* de ese algo. Busca el efecto que el dinero (o el insumo) *tenía que* dejar y que el actor no controla: una energía, una superficie, un servicio, un consumo, un footage.
- **El avance se encuentra preguntando "¿cuál es el trabajo útil de este nodo y qué recurso consume?"** y midiéndolo por el estado del mundo, no por lo que el nodo dice de sí. Si el nodo no tiene throughput (es stock, ancla o blanda), **no inventes un avance**: léelo como coherencia, como verificación o como orientación, según su tipo.
- **Regla de fuerza:** prefiere anclas relacionales o físicas (infalsificables por un solo nodo) sobre umbrales de un solo número (que el sofisticado esquiva por debajo).

---

## Ejemplos comunes

| Arista | Reporte (A, B) | Qué se triangula (ancla `x`) | Qué es avance | Contra qué | Frecuencia | Tipo |
|---|---|---|---|---|---|---|
| **Compras / obra** | facturas, contratos, avance reportado | avance físico de obra (satélite/supervisión); red de proveedores (69-B) | obra realmente ejecutada por peso pagado | dinero, catastro | periódica + continua | flujo |
| **Agua** | volumen extraído / facturado | energía de bombeo (kWh/m³) | m³ entregados por kWh (o por peso operativo) | dinero | continua | flujo |
| **Nómina** | plazas, monto | servicio real / asistencia | unidades de servicio por plaza pagada | dinero | continua | flujo |
| **Catastro** | valor catastral, declaración | superficie construida (satélite) | *(no aplica: stock)* coherencia patrimonio vs ingreso | dinero, compras | periódica | stock/coherencia |
| **Almacén** | inventario declarado | conteo físico continuo; patrón de acceso | rotación real de inventario; merma vs esperada | dinero, housekeeping | continua | flujo/ancla |
| **Housekeeping** | insumos/amenities surtidos | consumo por habitación-noche (ocupación) | habitaciones atendidas por hora-camarista; insumo por hab-noche | compras, ocupación | continua | flujo |
| **Vigilancia** | *(no reporta)* | footage: movimiento de bienes y personas | *(no aplica: ancla)* | almacén, compras | continua | ancla/verificación |
| **Rotación de personal** | altas / bajas | patrón de salidas (multipersona) | *(no aplica: orienta)* | apunta la auditoría | continua | blanda/orientadora |
| **Ambiente laboral** | encuestas / comunicación | resonancia (escucha, afinidad, telos) | *(no aplica: orienta)* | apunta la auditoría | continua | blanda/orientadora |

---

## Nota sobre el hotel (mismo caso, más aristas)

El robo de insumos del ejemplo original se puede triangular con varias aristas a la vez, cada una de un tipo distinto: **compras** (flujo), **housekeeping** (flujo: si compras surte el doble de amenities que la ocupación justifica consumir, el consumo por habitación-noche lo delata), **almacén** (flujo/ancla: rotación y merma), y **vigilancia** (ancla: footage de bienes saliendo fuera de horario). Ninguna prueba sola; su **coherencia conjunta** —y la disonancia entre la auditoría periódica y las señales continuas— es lo que orienta hacia dónde mirar.
