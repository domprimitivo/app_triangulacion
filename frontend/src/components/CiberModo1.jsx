import { useState, useEffect } from 'react';
import axios from 'axios';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import {
  ArrowLeft, Eye, ShieldCheck, KeyRound, DoorOpen, Play, Upload,
  Radio, Activity, AlertTriangle, FileText, Layers, Server, Zap,
  CheckCircle2, RotateCcw, Fingerprint, MapPin,
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
const colorDis = (d, a = 0.25, r = 0.4) => (d >= r ? C.red : d >= a ? C.amber : C.grass);

const Card = ({ children, testid }) => (
  <div className="p-5 rounded-xl mb-6" data-testid={testid}
    style={{ background: C.panel, border: `1px solid ${C.border}` }}>{children}</div>
);
const Titulo = ({ icon: Ic, children }) => (
  <div className="flex items-center gap-2 font-semibold text-sm mb-3" style={{ color: C.brickDark }}>
    {Ic && <Ic size={16} />} {children}
  </div>
);

export const CiberModo1 = () => {
  const [herramientas, setHerramientas] = useState([]);
  const [tool, setTool] = useState('modo1');
  const [dominios, setDominios] = useState([]);
  const [domainId, setDomainId] = useState('');
  const [config, setConfig] = useState(null);
  const [fuente, setFuente] = useState('embudo');
  const [files, setFiles] = useState([]);
  const [payload, setPayload] = useState('');
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState(null);
  const [msg, setMsg] = useState(null);
  const [admin, setAdmin] = useState('operador-1');
  const [buffer, setBuffer] = useState(null);

  useEffect(() => {
    axios.get(`${API}/ciber/herramientas`).then((r) => setHerramientas(r.data.herramientas || [])).catch(() => {});
    axios.get(`${API}/ciber/dominios`).then((r) => {
      const ds = r.data.dominios || []; setDominios(ds);
      if (ds.length) setDomainId(ds[0].domain_id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    setRes(null);
    if (domainId) axios.get(`${API}/ciber/modo1/config?dominio=${domainId}`).then((r) => setConfig(r.data)).catch(() => setConfig(null));
  }, [domainId]);

  useEffect(() => { setRes(null); setMsg(null); if (tool === 'admin' || tool === 'movimiento') setFuente('embudo'); }, [tool]);

  const refreshBuffer = () => domainId && axios.get(`${API}/ciber/ingesta/buffer/${domainId}`).then((r) => setBuffer(r.data.estado)).catch(() => {});
  useEffect(() => { if (fuente === 'ingesta_live') refreshBuffer(); }, [fuente, domainId]);

  const endpointFor = (t) => ({ modo1: 'modo1', modo2: 'modo2', administrativa: 'admin', movimiento: 'movimiento' }[t]);

  const analizar = async () => {
    setLoading(true); setMsg(null); setRes(null);
    try {
      const fd = new FormData();
      fd.append('domain_id', domainId);
      fd.append('fuente', fuente);
      if (fuente === 'api_webhook' && payload.trim()) fd.append('payload', payload.trim());
      if (fuente === 'embudo') files.forEach((f) => fd.append('files', f));
      const r = await axios.post(`${API}/ciber/${endpointFor(tool)}/analizar`, fd);
      setRes({ tool, data: r.data });
    } catch (e) {
      setMsg(e?.response?.data?.detail || 'Error al ejecutar el análisis.');
    } finally { setLoading(false); }
  };

  const enviarWebhook = async () => {
    setMsg(null);
    try {
      const body = JSON.parse(payload.trim() || '[]');
      const r = await axios.post(`${API}/ciber/ingesta/webhook/${domainId}`, body);
      setBuffer(r.data.buffer); setMsg(`Enviados ${r.data.eventos_agregados} evento(s) al buffer en vivo.`);
    } catch (e) { setMsg('Payload inválido o error de envío.'); }
  };

  const accionModo2 = async (tipo, token) => {
    try {
      const url = `${API}/ciber/modo2/${tipo}?domain_id=${domainId}`;
      const body = tipo === 'override' ? { override_token: token, admin, accion_correcta: null } : { override_token: token, admin };
      await axios.post(url, body);
      analizar();
    } catch (e) { setMsg(e?.response?.data?.detail || 'Error en la acción.'); }
  };

  const resolverIdentidad = async (recordId, a1, a2) => {
    try {
      const r = await axios.post(`${API}/ciber/movimiento/resolver-identidad?domain_id=${domainId}`, { record_id: recordId, admin1: a1, admin2: a2 });
      setMsg(r.data.msg); analizar();
    } catch (e) { setMsg(e?.response?.data?.detail || 'Error en la resolución.'); }
  };

  const usaLive = tool === 'modo1' || tool === 'modo2';
  const fuentes = [['embudo', 'Desde el embudo', Upload], ['api_webhook', 'API / Webhook', Radio]];
  if (usaLive) fuentes.push(['ingesta_live', 'En vivo', Zap]);

  return (
    <div className="min-h-screen relative" style={{ background: C.sand, color: C.ink }} data-testid="ciber-modo1-page">
      <Watermark />
      <div className="relative z-10 max-w-6xl mx-auto px-5 py-8">
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
          Selecciona una herramienta y una empresa. Cada herramienta tiene su propia ingesta: desde el <strong>embudo</strong>, desde <strong>API / webhook</strong>{usaLive ? ' o ' : ''}{usaLive ? <strong>en vivo</strong> : ''}.
        </p>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8" data-testid="ciber-herramientas">
          {herramientas.map((h) => {
            const Ic = ICONOS[h.icono] || Eye; const active = tool === h.id;
            return (
              <button key={h.id} onClick={() => setTool(h.id)} data-testid={`ciber-herramienta-${h.id}`}
                className="text-left p-4 rounded-xl transition-all"
                style={{ background: active ? C.brick : C.panel, border: `1px solid ${active ? C.brick : C.border}`, color: active ? '#fff' : C.ink }}>
                <Ic size={22} style={{ color: active ? '#fff' : C.brick }} />
                <div className="font-semibold text-sm mt-2">{h.nombre}</div>
                <div className="text-xs mt-1" style={{ color: active ? '#F4EEDF' : C.muted }}>{h.descripcion}</div>
              </button>
            );
          })}
        </div>

        {/* Controles */}
        <div className="grid md:grid-cols-3 gap-5 mb-6">
          <div className="md:col-span-2 p-5 rounded-xl" style={{ background: C.panel, border: `1px solid ${C.border}` }}>
            <Titulo icon={ICONOS[herramientas.find((h) => h.id === tool)?.icono] || Eye}>Configuración</Titulo>

            <label className="block text-xs mb-1" style={{ color: C.muted }}>Empresa</label>
            <select value={domainId} onChange={(e) => setDomainId(e.target.value)} data-testid="ciber-dominio-select"
              className="w-full p-2 rounded-lg mb-4 text-sm" style={{ background: C.sand, border: `1px solid ${C.border}`, color: C.ink }}>
              {dominios.map((d) => <option key={d.domain_id} value={d.domain_id}>{d.nombre}</option>)}
            </select>

            <label className="block text-xs mb-1" style={{ color: C.muted }}>Ingesta</label>
            <div className="flex gap-2 mb-4 flex-wrap">
              {fuentes.map(([id, label, Ic]) => (
                <button key={id} onClick={() => setFuente(id)} data-testid={`ciber-fuente-${id}`}
                  className="flex-1 min-w-[110px] p-2 rounded-lg text-sm inline-flex items-center justify-center gap-2 transition-all"
                  style={{ background: fuente === id ? C.sky : C.sand, border: `1px solid ${fuente === id ? C.sky : C.border}`, color: fuente === id ? '#fff' : C.ink }}>
                  <Ic size={15} /> {label}
                </button>
              ))}
            </div>

            {fuente === 'embudo' && (
              <div>
                <label className="block text-xs mb-1" style={{ color: C.muted }}>Archivos del cucurucho. Sin archivos → operación demo.</label>
                <input type="file" multiple onChange={(e) => setFiles(Array.from(e.target.files || []))} data-testid="ciber-files-input"
                  className="w-full text-xs p-2 rounded-lg" style={{ background: C.sand, border: `1px solid ${C.border}` }} />
                {files.length > 0 && <div className="text-xs mt-1" style={{ color: C.grass }}>{files.length} archivo(s)</div>}
              </div>
            )}
            {fuente === 'api_webhook' && (
              <div>
                <label className="block text-xs mb-1" style={{ color: C.muted }}>Payload (JSON o CEF) entregado por el nodo del cliente.</label>
                <textarea value={payload} onChange={(e) => setPayload(e.target.value)} data-testid="ciber-payload-input" rows={5}
                  placeholder='[{"_time":"2026-01-01T10:00:00","user":"u01","EventCode":"4625","severity":"HIGH","action":"blocked"}]'
                  className="w-full text-xs p-2 rounded-lg font-mono" style={{ background: C.sand, border: `1px solid ${C.border}`, color: C.ink }} />
              </div>
            )}
            {fuente === 'ingesta_live' && (
              <div data-testid="ciber-live-panel">
                <div className="text-xs mb-2 p-2 rounded" style={{ background: C.sand }}>
                  Buffer en vivo: <strong>{buffer?.total ?? 0}</strong> evento(s){buffer?.ultimo ? ` · último ${new Date(buffer.ultimo).toLocaleString()}` : ''}
                  <button onClick={refreshBuffer} className="ml-2 underline" style={{ color: C.sky }} data-testid="ciber-buffer-refresh">actualizar</button>
                </div>
                <label className="block text-xs mb-1" style={{ color: C.muted }}>Simular push del nodo (POST al webhook receiver):</label>
                <textarea value={payload} onChange={(e) => setPayload(e.target.value)} data-testid="ciber-webhook-input" rows={4}
                  placeholder='[{"_time":"2026-01-01T03:00:00","user":"u01","EventCode":"4625","severity":"CRITICAL","action":"blocked"}]'
                  className="w-full text-xs p-2 rounded-lg font-mono" style={{ background: C.sand, border: `1px solid ${C.border}`, color: C.ink }} />
                <button onClick={enviarWebhook} data-testid="ciber-webhook-send" className="mt-2 text-xs px-3 py-2 rounded-lg" style={{ background: C.sky, color: '#fff' }}>Enviar al buffer</button>
              </div>
            )}

            <button onClick={analizar} disabled={loading} data-testid="ciber-analizar-btn"
              className="mt-4 w-full py-3 rounded-lg font-semibold inline-flex items-center justify-center gap-2 transition-all"
              style={{ background: C.brick, color: '#fff', opacity: loading ? 0.7 : 1 }}>
              <Play size={17} /> {loading ? 'Procesando…' : 'Ejecutar'}
            </button>
            {msg && <div className="text-xs mt-3 p-2 rounded" style={{ background: '#F1E7DA', color: C.brickDark }} data-testid="ciber-error">{msg}</div>}
          </div>

          <div className="p-5 rounded-xl" style={{ background: C.panel, border: `1px solid ${C.border}` }} data-testid="ciber-siem-info">
            <Titulo icon={Server}>Nodo / Contexto</Titulo>
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
                {(tool === 'modo2') && <div style={{ color: C.muted }}>Modo 2 requiere administrador para confirmar/override.</div>}
                {(tool === 'movimiento') && <div style={{ color: C.muted }}>Identidad protegida: tokens anónimos + doble autorización.</div>}
              </div>
            ) : <div className="text-xs" style={{ color: C.muted }}>Selecciona una empresa…</div>}
          </div>
        </div>

        {/* Resultados */}
        {res && res.tool === 'modo1' && <ResultadoModo1 d={res.data} />}
        {res && res.tool === 'modo2' && <ResultadoModo2 d={res.data} admin={admin} setAdmin={setAdmin} onAccion={accionModo2} />}
        {res && res.tool === 'administrativa' && <ResultadoAdmin d={res.data} />}
        {res && res.tool === 'movimiento' && <ResultadoMovimiento d={res.data} onResolver={resolverIdentidad} />}
      </div>
    </div>
  );
};

// ── Modo 1 ──
const ResultadoModo1 = ({ d }) => {
  const m = d.metricas; const thA = d.thresholds?.alert ?? 0.25; const thR = d.thresholds?.report ?? 0.4;
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} data-testid="ciber-resultado">
      <div className="text-xs mb-3" style={{ color: C.muted }}>Origen: {d.origen}</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6" data-testid="ciber-metricas">
        {[['Disonancia media', m.disonancia_media, Activity], ['Disonancia máxima', m.disonancia_max, Activity],
          ['Ventanas ≥ alerta', `${m.ventanas_alerta}/${m.ventanas_total}`, AlertTriangle], ['Extremos activos', m.extremos_activos, Layers]].map(([l, v, Ic]) => (
          <div key={l} className="p-4 rounded-xl" style={{ background: C.panel, border: `1px solid ${C.border}` }}>
            <Ic size={16} style={{ color: C.brick }} /><div className="text-2xl font-bold mt-1" style={{ color: C.brickDark }}>{v}</div>
            <div className="text-xs" style={{ color: C.muted }}>{l}</div>
          </div>
        ))}
      </div>
      <Card testid="ciber-tendencia"><Titulo>Tendencia bimestral — disonancia por ventana</Titulo><Tendencia data={d.tendencia} thA={thA} thR={thR} /></Card>
      <Card testid="ciber-heatmap"><Titulo>Mapa de calor — disonancia por extremo</Titulo>
        <div className="space-y-2">{d.heatmap.map((row) => (
          <div key={row.entity_id} className="flex items-center gap-2">
            <div className="text-xs w-28 truncate" title={row.entity_id}>{row.entity_id}</div>
            <div className="flex gap-1 flex-wrap">{row.dissonances.map((x, i) => (
              <div key={i} title={x.toFixed(3)} className="w-5 h-5 rounded-sm" style={{ background: colorDis(x, thA, thR), opacity: 0.35 + Math.min(x / thR, 1) * 0.65 }} />
            ))}</div>
            <div className="text-xs ml-auto" style={{ color: C.muted }}>máx {row.max}</div>
          </div>
        ))}</div>
      </Card>
      <Card testid="ciber-top-ventanas"><Titulo>Top 20 ventanas de mayor disonancia</Titulo>
        <Tabla cols={['Extremo', 'Fuente', 'Ventana', 'Eventos', 'Disonancia']}
          rows={d.top_ventanas.map((v) => [v.entity_id, v.source, new Date(v.window_start).toLocaleString(), v.n_events,
            <span className="px-2 py-0.5 rounded-full text-white text-[11px]" style={{ background: colorDis(v.dissonance, thA, thR) }}>{v.dissonance.toFixed(3)}</span>])} />
      </Card>
      <Card testid="ciber-reporte"><Titulo icon={FileText}>Reporte bimestral</Titulo>
        <pre className="text-xs whitespace-pre-wrap leading-relaxed">{d.reporte_bimestral}</pre>
        {d.memoria?.ratio && <div className="text-xs mt-3" style={{ color: C.grass }}>Memoria comprimida (MOCG) · ratio {d.memoria.ratio}×</div>}
      </Card>
    </motion.div>
  );
};

// ── Modo 2 ──
const ResultadoModo2 = ({ d, admin, setAdmin, onAccion }) => (
  <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} data-testid="ciber-resultado">
    <div className="text-xs mb-3" style={{ color: C.muted }}>Origen: {d.origen}</div>
    <Card testid="ciber-modo2-admin">
      <label className="block text-xs mb-1" style={{ color: C.muted }}>Administrador que decide</label>
      <input value={admin} onChange={(e) => setAdmin(e.target.value)} data-testid="ciber-modo2-admin-input"
        className="p-2 rounded-lg text-sm" style={{ background: C.sand, border: `1px solid ${C.border}`, color: C.ink }} />
      <span className="text-xs ml-3" style={{ color: C.muted }}>Correction rate: <strong>{(d.adapter.correction_rate * 100).toFixed(0)}%</strong> · Decisiones: {d.adapter.decisiones}</span>
    </Card>
    <Card testid="ciber-modo2-forense"><Titulo icon={ShieldCheck}>Registro forense · acciones recomendadas por el PolicyAdapter</Titulo>
      {d.forensic.length === 0 ? <div className="text-xs" style={{ color: C.muted }}>Sin extremos por encima del umbral.</div> : (
        <div className="space-y-3">{d.forensic.slice(0, 12).map((r) => (
          <div key={r.record_id} className="p-3 rounded-lg" style={{ background: C.sand, border: `1px solid ${C.border}` }} data-testid="ciber-modo2-record">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="text-sm">
                <span className="font-semibold">{r.entity_id}</span>
                <span className="text-xs ml-2" style={{ color: C.muted }}>dis {r.dissonance} · {r.level_label}</span>
              </div>
              <div className="flex items-center gap-2">
                {r.override ? <span className="text-xs px-2 py-1 rounded" style={{ background: '#E6D9C2', color: C.brickDark }}>Override · {r.override_by}</span>
                  : r.confirmed ? <span className="text-xs px-2 py-1 rounded inline-flex items-center gap-1" style={{ background: '#DDE9CF', color: C.grass }}><CheckCircle2 size={12} /> Ejecutada</span>
                  : (<>
                    <button onClick={() => onAccion('confirmar', r.override_token)} data-testid="ciber-modo2-confirmar" className="text-xs px-2 py-1 rounded inline-flex items-center gap-1" style={{ background: C.grass, color: '#fff' }}><CheckCircle2 size={12} /> Confirmar</button>
                    <button onClick={() => onAccion('override', r.override_token)} data-testid="ciber-modo2-override" className="text-xs px-2 py-1 rounded inline-flex items-center gap-1" style={{ background: C.brick, color: '#fff' }}><RotateCcw size={12} /> Override</button>
                  </>)}
              </div>
            </div>
            <div className="mt-2 text-xs" style={{ color: C.ink }}>Acción sugerida: <strong>{r.action}</strong></div>
            <div className="mt-1 flex gap-1 flex-wrap">{r.recomendaciones.map((rc) => (
              <span key={rc.action} className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: C.panel, border: `1px solid ${C.border}`, color: C.muted }}>{rc.action} · {rc.score}</span>
            ))}</div>
            <div className="text-[10px] mt-1" style={{ color: C.muted }}>sha256 {r.sha256}</div>
          </div>
        ))}</div>
      )}
    </Card>
    <Card testid="ciber-modo2-adapter"><Titulo icon={FileText}>PolicyAdapter</Titulo>
      <pre className="text-xs whitespace-pre-wrap">{d.reporte_adapter}</pre>
    </Card>
  </motion.div>
);

// ── Admin ──
const ResultadoAdmin = ({ d }) => (
  <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} data-testid="ciber-resultado">
    <div className="text-xs mb-3" style={{ color: C.muted }}>Origen: {d.origen}</div>
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6" data-testid="ciber-admin-metricas">
      {[['Eventos', d.stats.total_events, Layers], ['Registros', d.stats.forensic_recs, FileText],
        ['Críticos', d.stats.critical, AlertTriangle], ['Auto-ataques GSL ⭐', d.stats.gsl_attacks, KeyRound]].map(([l, v, Ic]) => (
        <div key={l} className="p-4 rounded-xl" style={{ background: C.panel, border: `1px solid ${C.border}` }}>
          <Ic size={16} style={{ color: C.brick }} /><div className="text-2xl font-bold mt-1" style={{ color: C.brickDark }}>{v}</div>
          <div className="text-xs" style={{ color: C.muted }}>{l}</div>
        </div>
      ))}
    </div>
    <Card testid="ciber-admin-forense"><Titulo icon={KeyRound}>Registro forense administrativo (intenciones IAM)</Titulo>
      {d.records.length === 0 ? <div className="text-xs" style={{ color: C.muted }}>Sin anomalías administrativas.</div> : (
        <Tabla cols={['Actor', 'Disonancia', 'Evento gatillo', 'Objeto', 'GSL', 'Razones']}
          rows={d.records.slice(0, 20).map((r) => [r.actor_id, <span className="px-2 py-0.5 rounded-full text-white text-[11px]" style={{ background: colorDis(r.dissonance, 0.28, 0.55) }}>{r.dissonance}</span>,
            r.trigger_event, r.trigger_object,
            r.gsl_self_attack ? <span className="text-[10px] px-2 py-0.5 rounded-full text-white" style={{ background: C.red }}>AUTOATAQUE</span> : '—',
            <span className="text-[10px]" style={{ color: C.muted }}>{(r.reasons || []).join('; ')}</span>])} />
      )}
    </Card>
    <Card testid="ciber-admin-reporte"><Titulo icon={FileText}>Reporte</Titulo><pre className="text-xs whitespace-pre-wrap">{d.reporte}</pre></Card>
  </motion.div>
);

// ── Movimiento ──
const ResultadoMovimiento = ({ d, onResolver }) => (
  <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} data-testid="ciber-resultado">
    <div className="text-xs mb-3" style={{ color: C.muted }}>Origen: {d.origen}</div>
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6" data-testid="ciber-mov-metricas">
      {[['Eventos', d.stats.total_events, Layers], ['Registros', d.stats.forensic_recs, FileText],
        ['Imposible travel', d.stats.impossible_travel, MapPin], ['Solicitudes ID', d.stats.id_requests, Fingerprint]].map(([l, v, Ic]) => (
        <div key={l} className="p-4 rounded-xl" style={{ background: C.panel, border: `1px solid ${C.border}` }}>
          <Ic size={16} style={{ color: C.brick }} /><div className="text-2xl font-bold mt-1" style={{ color: C.brickDark }}>{v}</div>
          <div className="text-xs" style={{ color: C.muted }}>{l}</div>
        </div>
      ))}
    </div>
    <Card testid="ciber-mov-ocupacion"><Titulo icon={MapPin}>Ocupación por espacio</Titulo>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">{d.ocupacion.map((o) => (
        <div key={o.space_id} className="p-2 rounded-lg text-xs" style={{ background: o.anomalo ? '#F1E0DB' : C.sand, border: `1px solid ${o.anomalo ? C.brick : C.border}` }}>
          <div className="font-medium">{o.name}</div>
          <div style={{ color: C.muted }}>ocup. media {o.mean} / cap {o.capacity}</div>
          <div style={{ color: o.sensitivity === 'critical' || o.sensitivity === 'high' ? C.red : C.muted }}>{o.sensitivity}</div>
        </div>
      ))}</div>
    </Card>
    <Card testid="ciber-mov-forense"><Titulo icon={DoorOpen}>Registro forense de movimiento (tokens anónimos)</Titulo>
      {d.records.length === 0 ? <div className="text-xs" style={{ color: C.muted }}>Sin anomalías de movimiento.</div> : (
        <div className="space-y-2">{d.records.slice(0, 20).map((r) => (
          <div key={r.record_id} className="p-3 rounded-lg" style={{ background: C.sand, border: `1px solid ${C.border}` }} data-testid="ciber-mov-record">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="text-sm"><span className="font-semibold font-mono text-xs">{r.token}</span>
                <span className="text-xs ml-2" style={{ color: C.muted }}>{r.token_role} · {r.anomaly_type} · dis {r.combined_dissonance}</span></div>
              {r.id_resolution_requested && !r.id_resolution_authorized && <ResolverIdentidad recordId={r.record_id} onResolver={onResolver} />}
              {r.id_resolution_authorized && <span className="text-xs px-2 py-1 rounded inline-flex items-center gap-1" style={{ background: '#DDE9CF', color: C.grass }}><Fingerprint size={12} /> {r.resolved_badge_id}</span>}
            </div>
            <div className="text-xs mt-1" style={{ color: C.ink }}>{r.description}</div>
          </div>
        ))}</div>
      )}
    </Card>
    <Card testid="ciber-mov-reporte"><Titulo icon={FileText}>Reporte</Titulo><pre className="text-xs whitespace-pre-wrap">{d.reporte}</pre></Card>
  </motion.div>
);

const ResolverIdentidad = ({ recordId, onResolver }) => {
  const [a1, setA1] = useState(''); const [a2, setA2] = useState('');
  return (
    <div className="flex items-center gap-1" data-testid="ciber-mov-resolver">
      <input value={a1} onChange={(e) => setA1(e.target.value)} placeholder="admin 1" className="text-xs p-1 rounded w-20" style={{ background: '#fff', border: `1px solid ${C.border}` }} data-testid="ciber-mov-admin1" />
      <input value={a2} onChange={(e) => setA2(e.target.value)} placeholder="admin 2" className="text-xs p-1 rounded w-20" style={{ background: '#fff', border: `1px solid ${C.border}` }} data-testid="ciber-mov-admin2" />
      <button onClick={() => onResolver(recordId, a1, a2)} className="text-xs px-2 py-1 rounded inline-flex items-center gap-1" style={{ background: C.brick, color: '#fff' }} data-testid="ciber-mov-resolver-btn"><Fingerprint size={12} /> Resolver</button>
    </div>
  );
};

const Tabla = ({ cols, rows }) => (
  <div className="overflow-x-auto">
    <table className="w-full text-xs">
      <thead><tr style={{ color: C.muted }} className="text-left">{cols.map((c) => <th key={c} className="py-1 pr-2">{c}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => (
        <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>{r.map((cell, j) => <td key={j} className="py-1 pr-2">{cell}</td>)}</tr>
      ))}</tbody>
    </table>
  </div>
);

const Tendencia = ({ data, thA, thR }) => {
  if (!data || data.length === 0) return <div className="text-xs" style={{ color: C.muted }}>Sin datos de tendencia.</div>;
  const W = 720, H = 160, pad = 24;
  const xs = data.map((_, i) => pad + (i * (W - 2 * pad)) / Math.max(data.length - 1, 1));
  const maxD = Math.max(thR, ...data.map((d) => d.dissonance));
  const y = (v) => H - pad - (v / maxD) * (H - 2 * pad);
  const pts = data.map((d, i) => `${xs[i]},${y(d.dissonance)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 200 }} data-testid="ciber-tendencia-svg">
      <line x1={pad} y1={y(thR)} x2={W - pad} y2={y(thR)} stroke={C.red} strokeDasharray="4 4" strokeWidth="1" opacity="0.6" />
      <line x1={pad} y1={y(thA)} x2={W - pad} y2={y(thA)} stroke={C.amber} strokeDasharray="4 4" strokeWidth="1" opacity="0.6" />
      <polyline points={pts} fill="none" stroke={C.sky} strokeWidth="2" />
      {data.map((d, i) => <circle key={i} cx={xs[i]} cy={y(d.dissonance)} r="3" fill={colorDis(d.dissonance, thA, thR)} />)}
    </svg>
  );
};

export default CiberModo1;
