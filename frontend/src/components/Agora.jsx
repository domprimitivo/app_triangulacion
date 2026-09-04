import { useState, useEffect } from 'react';
import axios from 'axios';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import {
  ArrowLeft, Play, Crosshair, Sparkles, Layers, Activity, Info, ChevronDown, ChevronRight,
} from 'lucide-react';
import { Watermark } from './Watermark';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const C = {
  sand: '#E9DFC9', panel: '#F4EEDF', border: '#D8C8A6',
  brick: '#A94E34', brickDark: '#7E3A26', sky: '#3E7CB1',
  grass: '#4E7A34', amber: '#E0A82E', red: '#C0392B',
  ink: '#3A2E28', muted: '#8A7A66',
};

const colorX = (x) => (x >= 0.66 ? C.red : x >= 0.4 ? C.amber : C.grass);

export const Agora = () => {
  const [dominios, setDominios] = useState([]);
  const [domId, setDomId] = useState('');
  const [info, setInfo] = useState(null);
  const [entradas, setEntradas] = useState({});
  const [abierto, setAbierto] = useState({});
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    axios.get(`${API}/agora/dominios`).then((r) => {
      const ds = r.data.dominios || []; setDominios(ds);
      if (ds.length) setDomId(ds[0].id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!domId) return;
    setRes(null); setMsg(null);
    axios.get(`${API}/agora/dominio/${domId}`).then((r) => {
      setInfo(r.data);
      setEntradas(JSON.parse(JSON.stringify(r.data.demo_entradas || {})));
      const ab = {}; (r.data.nodos || []).forEach((n, i) => { ab[n.nodo] = i === 0; });
      setAbierto(ab);
    }).catch(() => setInfo(null));
  }, [domId]);

  const setCampo = (nodo, campo, valor) => {
    setEntradas((prev) => ({ ...prev, [nodo]: { ...prev[nodo], [campo]: valor === '' ? '' : Number(valor) } }));
  };

  const cargarDemo = () => {
    if (info?.demo_entradas) setEntradas(JSON.parse(JSON.stringify(info.demo_entradas)));
    setMsg('Cargado ejemplo de coordenadas conocidas.');
  };

  const triangular = async () => {
    setLoading(true); setMsg(null); setRes(null);
    try {
      const r = await axios.post(`${API}/agora/triangular`, { dominio_id: domId, entradas });
      setRes(r.data);
    } catch (e) {
      setMsg(e?.response?.data?.detail || 'Error al triangular.');
    } finally { setLoading(false); }
  };

  const dom = dominios.find((d) => d.id === domId);

  return (
    <div className="min-h-screen relative" style={{ background: C.sand, color: C.ink }} data-testid="agora-page">
      <Watermark />
      <div className="relative z-10 max-w-6xl mx-auto px-5 py-8">
        <div className="flex items-center justify-between mb-6">
          <Link to="/" className="inline-flex items-center gap-2 text-sm" style={{ color: C.brickDark }} data-testid="agora-back-link">
            <ArrowLeft size={18} /> Volver
          </Link>
          <span className="text-xs px-3 py-1 rounded-full" style={{ background: C.panel, border: `1px solid ${C.border}`, color: C.muted }}>
            Ágora · Retícula de Triangulación
          </span>
        </div>

        <h1 className="text-4xl sm:text-5xl font-bold mb-2" style={{ color: C.brickDark }}>El Ágora Unificado</h1>
        <p className="text-sm mb-6" style={{ color: C.muted }}>
          Un solo motor, siete dominios. Ingresa las <strong>coordenadas conocidas</strong> de cada nodo;
          el primitivo aporta la coordenada desconocida: la <strong>disonancia</strong>. Se grafica el plano <em>x</em> (disonancia) vs <em>y</em> (dinero/interna).
        </p>

        {/* Selector de dominio */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2 mb-6" data-testid="agora-dominios">
          {dominios.map((d) => {
            const active = domId === d.id;
            return (
              <button key={d.id} onClick={() => setDomId(d.id)} data-testid={`agora-dominio-${d.id}`}
                className="text-left p-3 rounded-xl transition-all"
                style={{ background: active ? C.brick : C.panel, border: `1px solid ${active ? C.brick : C.border}`, color: active ? '#fff' : C.ink }}>
                <div className="font-semibold text-xs">{d.etiqueta}</div>
                <div className="text-[10px] mt-1" style={{ color: active ? '#F4EEDF' : C.muted }}>{d.n_nodos} nodos</div>
              </button>
            );
          })}
        </div>

        {info && (
          <div className="p-3 rounded-lg mb-6 text-xs flex flex-wrap gap-x-6 gap-y-1" style={{ background: C.panel, border: `1px solid ${C.border}` }} data-testid="agora-info">
            <span><span style={{ color: C.muted }}>Dominio:</span> <strong>{info.dominio}</strong></span>
            <span><span style={{ color: C.muted }}>Triangulación:</span> {info.triangulacion}</span>
            <span><span style={{ color: C.muted }}>Primaria:</span> {info.primaria}</span>
            {info.descripcion && <span className="w-full mt-1" style={{ color: C.muted }}>{info.descripcion}</span>}
          </div>
        )}

        <div className="grid lg:grid-cols-2 gap-6">
          {/* Ingesta de coordenadas */}
          <div className="p-5 rounded-xl" style={{ background: C.panel, border: `1px solid ${C.border}` }} data-testid="agora-ingesta">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 font-semibold text-sm" style={{ color: C.brickDark }}>
                <Crosshair size={16} /> Ingesta de coordenadas conocidas
              </div>
              <button onClick={cargarDemo} data-testid="agora-cargar-demo" className="text-xs px-3 py-1.5 rounded-lg inline-flex items-center gap-1" style={{ background: C.sky, color: '#fff' }}>
                <Sparkles size={13} /> Cargar ejemplo
              </button>
            </div>

            <div className="space-y-2 max-h-[560px] overflow-y-auto pr-1">
              {(info?.nodos || []).map((n) => {
                const isOpen = abierto[n.nodo];
                const ent = entradas[n.nodo] || {};
                const campos = Object.keys(ent).filter((k) => k !== 'token' && k !== 'timestamp_fase');
                return (
                  <div key={n.nodo} className="rounded-lg" style={{ border: `1px solid ${C.border}`, background: C.sand }} data-testid={`agora-nodo-${n.nodo}`}>
                    <button onClick={() => setAbierto((p) => ({ ...p, [n.nodo]: !p[n.nodo] }))}
                      className="w-full flex items-center gap-2 p-2.5 text-left">
                      {isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                      <span className="font-medium text-sm flex-1">{n.nodo}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: C.panel, color: C.muted, border: `1px solid ${C.border}` }}>{n.tipo}</span>
                      {n.primitivo && <span className="text-[10px]" style={{ color: C.muted }}>{n.primitivo}</span>}
                    </button>
                    {isOpen && (
                      <div className="px-3 pb-3">
                        {n.descripcion && <p className="text-[11px] mb-2" style={{ color: C.muted }}>{n.descripcion}</p>}
                        <div className="grid grid-cols-2 gap-2">
                          {campos.map((c) => (
                            <label key={c} className="text-[11px]" style={{ color: C.muted }}>
                              {c}
                              <input type="number" step="any" value={ent[c]} onChange={(e) => setCampo(n.nodo, c, e.target.value)}
                                data-testid={`agora-input-${n.nodo}-${c}`}
                                className="w-full mt-0.5 p-1.5 rounded text-xs" style={{ background: '#fff', border: `1px solid ${C.border}`, color: C.ink }} />
                            </label>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <button onClick={triangular} disabled={loading} data-testid="agora-triangular-btn"
              className="mt-4 w-full py-3 rounded-lg font-semibold inline-flex items-center justify-center gap-2"
              style={{ background: C.brick, color: '#fff', opacity: loading ? 0.7 : 1 }}>
              <Play size={17} /> {loading ? 'Triangulando…' : 'Triangular'}
            </button>
            {msg && <div className="text-xs mt-3 p-2 rounded" style={{ background: '#F1E7DA', color: C.brickDark }} data-testid="agora-msg">{msg}</div>}
          </div>

          {/* Salida: plano + disonancias */}
          <div>
            {res ? (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} data-testid="agora-resultado">
                <div className="p-5 rounded-xl mb-6" style={{ background: C.panel, border: `1px solid ${C.border}` }} data-testid="agora-plano">
                  <div className="flex items-center gap-2 font-semibold text-sm mb-1" style={{ color: C.brickDark }}>
                    <Layers size={16} /> Plano de triangulación
                  </div>
                  <p className="text-[11px] mb-3" style={{ color: C.muted }}>x = disonancia · y = {res.triangulacion === 'interna_conservacion' ? 'déficit interno' : 'señal de dinero (69-B)'}</p>
                  <Plano puntos={res.plano} />
                </div>
                <div className="p-5 rounded-xl" style={{ background: C.panel, border: `1px solid ${C.border}` }} data-testid="agora-disonancias">
                  <div className="font-semibold text-sm mb-3" style={{ color: C.brickDark }}>Disonancias por nodo</div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead><tr style={{ color: C.muted }} className="text-left"><th className="py-1 pr-2">Nodo</th><th>x (disonancia)</th><th>y</th><th>avance</th></tr></thead>
                      <tbody>
                        {res.plano.map((p) => (
                          <tr key={p.nodo} style={{ borderTop: `1px solid ${C.border}` }}>
                            <td className="py-1 pr-2 font-medium">{p.nodo}</td>
                            <td><span className="px-2 py-0.5 rounded-full text-white text-[11px]" style={{ background: colorX(p.x) }}>{p.x}</span></td>
                            <td style={{ color: C.muted }}>{p.y ?? '—'} <span className="text-[10px]">{p.y_tipo}</span></td>
                            <td style={{ color: C.muted }}>{p.avance ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {/* Nodos blandos (orientan, no triangulan) */}
                  {Object.values(res.paquetes).some((p) => p.tipo === 'blanda') && (
                    <div className="mt-4 pt-3" style={{ borderTop: `1px dashed ${C.border}` }} data-testid="agora-blandas">
                      <div className="text-[11px] font-semibold mb-2 inline-flex items-center gap-1" style={{ color: C.muted }}>
                        <Info size={12} /> Nodos blandos (orientan, no triangulan)
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {Object.values(res.paquetes).filter((p) => p.tipo === 'blanda').map((p) => (
                          <span key={p.nodo} className="text-[11px] px-2 py-1 rounded-full" style={{ background: C.sand, border: `1px solid ${C.border}` }}>
                            {p.nodo} · coherencia {p.coherencia}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </motion.div>
            ) : (
              <div className="p-8 rounded-xl h-full flex flex-col items-center justify-center text-center" style={{ background: C.panel, border: `1px dashed ${C.border}`, color: C.muted }} data-testid="agora-vacio">
                <Activity size={28} style={{ color: C.brick }} />
                <p className="text-sm mt-3">Ingresa las coordenadas y pulsa <strong>Triangular</strong> para ver el plano y las disonancias.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// Plano scatter x (disonancia) vs y (dinero/interna), ambos en [0,1]
const Plano = ({ puntos }) => {
  const W = 460, H = 360, pad = 40;
  const px = (x) => pad + x * (W - 2 * pad);
  const py = (y) => H - pad - (y ?? 0) * (H - 2 * pad);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" data-testid="agora-plano-svg">
      {/* ejes y cuadrantes */}
      <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} stroke={C.border} strokeWidth="1" />
      <line x1={pad} y1={pad} x2={pad} y2={H - pad} stroke={C.border} strokeWidth="1" />
      <line x1={px(0.5)} y1={pad} x2={px(0.5)} y2={H - pad} stroke={C.border} strokeDasharray="3 3" strokeWidth="1" opacity="0.7" />
      <line x1={pad} y1={py(0.5)} x2={W - pad} y2={py(0.5)} stroke={C.border} strokeDasharray="3 3" strokeWidth="1" opacity="0.7" />
      <text x={W - pad} y={H - pad + 16} fontSize="10" fill={C.muted} textAnchor="end">disonancia →</text>
      <text x={pad - 6} y={pad - 8} fontSize="10" fill={C.muted}>y ↑</text>
      {puntos.map((p, i) => (
        <g key={p.nodo}>
          <circle cx={px(p.x)} cy={py(p.y)} r="7" fill={colorX(p.x)} opacity="0.85" />
          <text x={px(p.x) + 10} y={py(p.y) + 3} fontSize="9" fill={C.ink}>{p.nodo}</text>
        </g>
      ))}
    </svg>
  );
};

export default Agora;
