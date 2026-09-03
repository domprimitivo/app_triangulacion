import { useState, useEffect } from 'react';
import axios from 'axios';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import {
  ArrowLeft, Eye, ShieldCheck, KeyRound, DoorOpen, Play, Upload,
  Radio, Activity, AlertTriangle, FileText, Layers, Server,
} from 'lucide-react';
import { Watermark } from './Watermark';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const C = {
  sand: '#E9DFC9', panel: '#F4EEDF', border: '#D8C8A6',
  brick: '#A94E34', brickDark: '#7E3A26', sky: '#3E7CB1',
  grass: '#4E7A34', amber: '#E0A82E', red: '#C0392B',
  ink: '#3A2E28', muted: '#8A7A66',
};

const ICONOS = { Eye, ShieldCheck, KeyRound, DoorOpen };

// Escala disonancia → color (verde bajo, ámbar medio, ladrillo/rojo alto)
const colorDis = (d, thA = 0.25, thR = 0.4) =>
  d >= thR ? C.red : d >= thA ? C.amber : C.grass;

export const CiberModo1 = () => {
  const [herramientas, setHerramientas] = useState([]);
  const [herramienta, setHerramienta] = useState('modo1');
  const [dominios, setDominios] = useState([]);
  const [domainId, setDomainId] = useState('');
  const [config, setConfig] = useState(null);
  const [fuente, setFuente] = useState('embudo');
  const [files, setFiles] = useState([]);
  const [payload, setPayload] = useState('');
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState(null);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    axios.get(`${API}/ciber/herramientas`).then((r) => setHerramientas(r.data.herramientas || [])).catch(() => {});
    axios.get(`${API}/ciber/dominios`).then((r) => {
      const ds = r.data.dominios || [];
      setDominios(ds);
      if (ds.length) setDomainId(ds[0].domain_id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!domainId) return;
    setRes(null);
    axios.get(`${API}/ciber/modo1/config?dominio=${domainId}`)
      .then((r) => setConfig(r.data)).catch(() => setConfig(null));
  }, [domainId]);

  const analizar = async () => {
    setLoading(true); setMsg(null); setRes(null);
    try {
      const fd = new FormData();
      fd.append('domain_id', domainId);
      fd.append('fuente', fuente);
      if (fuente === 'api_webhook' && payload.trim()) fd.append('payload', payload.trim());
      if (fuente === 'embudo') files.forEach((f) => fd.append('files', f));
      const r = await axios.post(`${API}/ciber/modo1/analizar`, fd);
      setRes(r.data);
    } catch (e) {
      setMsg(e?.response?.data?.detail || 'Error al ejecutar el análisis.');
    } finally {
      setLoading(false);
    }
  };

  const disponible = herramientas.find((h) => h.id === herramienta)?.disponible ?? true;
  const m = res?.metricas;
  const thA = res?.thresholds?.alert ?? 0.25;
  const thR = res?.thresholds?.report ?? 0.4;

  return (
    <div className="min-h-screen relative" style={{ background: C.sand, color: C.ink }} data-testid="ciber-modo1-page">
      <Watermark />
      <div className="relative z-10 max-w-6xl mx-auto px-5 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <Link to="/" className="inline-flex items-center gap-2 text-sm" style={{ color: C.brickDark }} data-testid="ciber-back-link">
            <ArrowLeft size={18} /> Volver
          </Link>
          <span className="text-xs px-3 py-1 rounded-full" style={{ background: C.panel, border: `1px solid ${C.border}`, color: C.muted }}>
            Elemento de Ciberseguridad · Segundo Producto
          </span>
        </div>

        <h1 className="text-4xl sm:text-5xl font-bold mb-2" style={{ color: C.brickDark }}>Motor Empresa · Ciberseguridad</h1>
        <p className="text-sm mb-8" style={{ color: C.muted }}>
          Selecciona una herramienta y una empresa. Cada herramienta tiene su propia ingesta:
          desde el <strong>embudo</strong> o desde <strong>API / webhook</strong>.
        </p>

        {/* Selector de herramientas (4 opciones) */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8" data-testid="ciber-herramientas">
          {herramientas.map((h) => {
            const Ic = ICONOS[h.icono] || Eye;
            const active = herramienta === h.id;
            return (
              <button
                key={h.id}
                onClick={() => setHerramienta(h.id)}
                data-testid={`ciber-herramienta-${h.id}`}
                className="text-left p-4 rounded-xl transition-all"
                style={{
                  background: active ? C.brick : C.panel,
                  border: `1px solid ${active ? C.brick : C.border}`,
                  color: active ? '#fff' : C.ink,
                  opacity: h.disponible ? 1 : 0.6,
                }}
              >
                <Ic size={22} style={{ color: active ? '#fff' : C.brick }} />
                <div className="font-semibold text-sm mt-2">{h.nombre}</div>
                <div className="text-xs mt-1" style={{ color: active ? '#F4EEDF' : C.muted }}>{h.descripcion}</div>
                {!h.disponible && <div className="text-[10px] mt-2 uppercase tracking-wide">Próximamente</div>}
              </button>
            );
          })}
        </div>

        {!disponible ? (
          <div className="p-6 rounded-xl text-sm" style={{ background: C.panel, border: `1px solid ${C.border}`, color: C.muted }} data-testid="ciber-herramienta-no-disp">
            Esta herramienta está definida en el diseño y se activará en una próxima entrega. Por ahora, el <strong>Modo 1 (Observación Pasiva)</strong> está operativo.
          </div>
        ) : (
          <>
            {/* Panel de control */}
            <div className="grid md:grid-cols-3 gap-5 mb-6">
              <div className="md:col-span-2 p-5 rounded-xl" style={{ background: C.panel, border: `1px solid ${C.border}` }}>
                <div className="flex items-center gap-2 mb-4" style={{ color: C.brickDark }}>
                  <Eye size={18} /> <span className="font-semibold">Observación Pasiva — Configuración</span>
                </div>

                <label className="block text-xs mb-1" style={{ color: C.muted }}>Empresa</label>
                <select
                  value={domainId}
                  onChange={(e) => setDomainId(e.target.value)}
                  data-testid="ciber-dominio-select"
                  className="w-full p-2 rounded-lg mb-4 text-sm"
                  style={{ background: C.sand, border: `1px solid ${C.border}`, color: C.ink }}
                >
                  {dominios.map((d) => <option key={d.domain_id} value={d.domain_id}>{d.nombre}</option>)}
                </select>

                <label className="block text-xs mb-1" style={{ color: C.muted }}>Ingesta</label>
                <div className="flex gap-2 mb-4">
                  {[['embudo', 'Desde el embudo', Upload], ['api_webhook', 'API / Webhook', Radio]].map(([id, label, Ic]) => (
                    <button
                      key={id}
                      onClick={() => setFuente(id)}
                      data-testid={`ciber-fuente-${id}`}
                      className="flex-1 p-2 rounded-lg text-sm inline-flex items-center justify-center gap-2 transition-all"
                      style={{
                        background: fuente === id ? C.sky : C.sand,
                        border: `1px solid ${fuente === id ? C.sky : C.border}`,
                        color: fuente === id ? '#fff' : C.ink,
                      }}
                    >
                      <Ic size={15} /> {label}
                    </button>
                  ))}
                </div>

                {fuente === 'embudo' ? (
                  <div>
                    <label className="block text-xs mb-1" style={{ color: C.muted }}>
                      Archivos del cucurucho (SIEM: Chronicle / Splunk / Sentinel / CEF / CSV). Sin archivos → operación demo.
                    </label>
                    <input
                      type="file" multiple
                      onChange={(e) => setFiles(Array.from(e.target.files || []))}
                      data-testid="ciber-files-input"
                      className="w-full text-xs p-2 rounded-lg"
                      style={{ background: C.sand, border: `1px solid ${C.border}` }}
                    />
                    {files.length > 0 && <div className="text-xs mt-1" style={{ color: C.grass }}>{files.length} archivo(s) seleccionado(s)</div>}
                  </div>
                ) : (
                  <div>
                    <label className="block text-xs mb-1" style={{ color: C.muted }}>Payload SIEM (JSON o CEF). Ej.: un array de eventos exportados del nodo del cliente.</label>
                    <textarea
                      value={payload}
                      onChange={(e) => setPayload(e.target.value)}
                      data-testid="ciber-payload-input"
                      rows={5}
                      placeholder='[{"_time":"2026-01-01T10:00:00","user":"u01","EventCode":"4625","severity":"HIGH","action":"blocked"}]'
                      className="w-full text-xs p-2 rounded-lg font-mono"
                      style={{ background: C.sand, border: `1px solid ${C.border}`, color: C.ink }}
                    />
                  </div>
                )}

                <button
                  onClick={analizar}
                  disabled={loading}
                  data-testid="ciber-analizar-btn"
                  className="mt-4 w-full py-3 rounded-lg font-semibold inline-flex items-center justify-center gap-2 transition-all"
                  style={{ background: C.brick, color: '#fff', opacity: loading ? 0.7 : 1 }}
                >
                  <Play size={17} /> {loading ? 'Observando…' : 'Ejecutar observación pasiva'}
                </button>
                {msg && <div className="text-xs mt-3 p-2 rounded" style={{ background: '#F8E7E2', color: C.red }} data-testid="ciber-error">{msg}</div>}
              </div>

              {/* Info nodo SIEM */}
              <div className="p-5 rounded-xl" style={{ background: C.panel, border: `1px solid ${C.border}` }} data-testid="ciber-siem-info">
                <div className="flex items-center gap-2 mb-3" style={{ color: C.brickDark }}>
                  <Server size={18} /> <span className="font-semibold">Nodo SIEM</span>
                </div>
                {config ? (
                  <div className="text-xs space-y-2" style={{ color: C.ink }}>
                    <div><span style={{ color: C.muted }}>Empresa:</span> {config.org_name}</div>
                    <div><span style={{ color: C.muted }}>Bimestre:</span> {config.bimester}</div>
                    <div><span style={{ color: C.muted }}>Usuarios:</span> {config.usuarios} · <span style={{ color: C.muted }}>Activos:</span> {config.activos}</div>
                    {(config.nodos_siem || []).map((n) => (
                      <div key={n.node_id} className="p-2 rounded" style={{ background: C.sand }}>
                        <div className="font-medium">{n.node_id}</div>
                        <div style={{ color: C.muted }}>Plataforma: {n.siem_platform} · Nivel {n.deployment_level}</div>
                      </div>
                    ))}
                    <div style={{ color: C.muted }} className="pt-1">Umbrales: alerta {config.thresholds?.geo_dissonance_alert} · reporte {config.thresholds?.geo_dissonance_report}</div>
                  </div>
                ) : <div className="text-xs" style={{ color: C.muted }}>Selecciona una empresa…</div>}
              </div>
            </div>

            {/* Resultados */}
            {res && (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} data-testid="ciber-resultado">
                <div className="text-xs mb-3" style={{ color: C.muted }}>Origen: {res.origen}</div>

                {/* Tarjetas de métricas */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6" data-testid="ciber-metricas">
                  {[
                    ['Disonancia media', m.disonancia_media, Activity],
                    ['Disonancia máxima', m.disonancia_max, Activity],
                    ['Ventanas ≥ alerta', `${m.ventanas_alerta}/${m.ventanas_total}`, AlertTriangle],
                    ['Extremos activos', m.extremos_activos, Layers],
                  ].map(([label, val, Ic]) => (
                    <div key={label} className="p-4 rounded-xl" style={{ background: C.panel, border: `1px solid ${C.border}` }}>
                      <Ic size={16} style={{ color: C.brick }} />
                      <div className="text-2xl font-bold mt-1" style={{ color: C.brickDark }}>{val}</div>
                      <div className="text-xs" style={{ color: C.muted }}>{label}</div>
                    </div>
                  ))}
                </div>

                {/* Tendencia bimestral (línea) */}
                <div className="p-5 rounded-xl mb-6" style={{ background: C.panel, border: `1px solid ${C.border}` }} data-testid="ciber-tendencia">
                  <div className="font-semibold text-sm mb-3" style={{ color: C.brickDark }}>Tendencia bimestral — disonancia por ventana</div>
                  <Tendencia data={res.tendencia} thA={thA} thR={thR} />
                </div>

                {/* Mapa de calor por extremo */}
                <div className="p-5 rounded-xl mb-6" style={{ background: C.panel, border: `1px solid ${C.border}` }} data-testid="ciber-heatmap">
                  <div className="font-semibold text-sm mb-3" style={{ color: C.brickDark }}>Mapa de calor — disonancia por extremo</div>
                  <div className="space-y-2">
                    {res.heatmap.map((row) => (
                      <div key={row.entity_id} className="flex items-center gap-2">
                        <div className="text-xs w-28 truncate" style={{ color: C.ink }} title={row.entity_id}>{row.entity_id}</div>
                        <div className="flex gap-1 flex-wrap">
                          {row.dissonances.map((d, i) => (
                            <div key={i} title={d.toFixed(3)} className="w-5 h-5 rounded-sm"
                              style={{ background: colorDis(d, thA, thR), opacity: 0.35 + Math.min(d / thR, 1) * 0.65 }} />
                          ))}
                        </div>
                        <div className="text-xs ml-auto" style={{ color: C.muted }}>máx {row.max}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Top 20 ventanas */}
                <div className="p-5 rounded-xl mb-6" style={{ background: C.panel, border: `1px solid ${C.border}` }} data-testid="ciber-top-ventanas">
                  <div className="font-semibold text-sm mb-3" style={{ color: C.brickDark }}>Top 20 ventanas de mayor disonancia</div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr style={{ color: C.muted }} className="text-left">
                          <th className="py-1">Extremo</th><th>Fuente</th><th>Ventana</th><th>Eventos</th><th>Disonancia</th>
                        </tr>
                      </thead>
                      <tbody>
                        {res.top_ventanas.map((v, i) => (
                          <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                            <td className="py-1 font-medium">{v.entity_id}</td>
                            <td style={{ color: C.muted }}>{v.source}</td>
                            <td style={{ color: C.muted }}>{new Date(v.window_start).toLocaleString()}</td>
                            <td>{v.n_events}</td>
                            <td><span className="px-2 py-0.5 rounded-full text-white text-[11px]" style={{ background: colorDis(v.dissonance, thA, thR) }}>{v.dissonance.toFixed(3)}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Reporte bimestral */}
                <div className="p-5 rounded-xl" style={{ background: C.panel, border: `1px solid ${C.border}` }} data-testid="ciber-reporte">
                  <div className="flex items-center gap-2 font-semibold text-sm mb-3" style={{ color: C.brickDark }}>
                    <FileText size={16} /> Reporte bimestral
                  </div>
                  <pre className="text-xs whitespace-pre-wrap leading-relaxed" style={{ color: C.ink }}>{res.reporte_bimestral}</pre>
                  {res.memoria?.ratio && (
                    <div className="text-xs mt-3" style={{ color: C.grass }}>
                      Memoria guardada comprimida (códec MOCG) · ratio {res.memoria.ratio}×
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

// Gráfico de línea SVG (dependencia cero)
const Tendencia = ({ data, thA, thR }) => {
  if (!data || data.length === 0) return <div className="text-xs" style={{ color: C.muted }}>Sin datos de tendencia.</div>;
  const W = 720, H = 160, pad = 24;
  const xs = data.map((_, i) => pad + (i * (W - 2 * pad)) / Math.max(data.length - 1, 1));
  const maxD = Math.max(thR, ...data.map((d) => d.dissonance));
  const y = (d) => H - pad - (d / maxD) * (H - 2 * pad);
  const pts = data.map((d, i) => `${xs[i]},${y(d.dissonance)}`).join(' ');
  const lineA = y(thA), lineR = y(thR);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 200 }} data-testid="ciber-tendencia-svg">
      <line x1={pad} y1={lineR} x2={W - pad} y2={lineR} stroke={C.red} strokeDasharray="4 4" strokeWidth="1" opacity="0.6" />
      <line x1={pad} y1={lineA} x2={W - pad} y2={lineA} stroke={C.amber} strokeDasharray="4 4" strokeWidth="1" opacity="0.6" />
      <polyline points={pts} fill="none" stroke={C.sky} strokeWidth="2" />
      {data.map((d, i) => (
        <circle key={i} cx={xs[i]} cy={y(d.dissonance)} r="3" fill={colorDis(d.dissonance, thA, thR)} />
      ))}
    </svg>
  );
};

export default CiberModo1;
