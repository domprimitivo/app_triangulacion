"""
Aprendiz Mileforum — Ajuste Bimestral (Policy Fine-Tune)
========================================================
Port fiel al servicio del notebook `Mileforum_Aprendiz_Ajuste_Bimestral_v0_1.ipynb`.

NO construye modelos nuevos (no es "fábrica"). Su única función:
  1) Cargar el bundle multicefálico del dominio (zip)
  2) Cargar el histórico bimestral (learning_log.jsonl del Aprendiz día-a-día)
  3) Ajustar SOLO la capa policy entrenando un `PolicyAdapter` prudencial
  4) Consolidar y versionar:
       - allowed_actions_by_phase.json  (allowlist operacional)
       - actions_added_this_bimester.json (diff)
       - policy_adapter.pt              (pesos del adaptador entrenado)
       - bimester_report.json
  5) REEMPLAZAR EN SU LUGAR el policy del bundle activo por el recién ajustado
     (se conserva un respaldo .bak del bundle anterior).

El adaptador requiere PyTorch. Si PyTorch no está disponible o no hay datos
suficientes, se ejecuta igualmente la consolidación de allowlist/catálogo y se
marca el entrenamiento como omitido en el reporte (comportamiento prudencial).
"""

import os
import re
import json
import math
import shutil
import random
import hashlib
import zipfile
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter
from typing import Dict, Any, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Config de entrenamiento (idéntica al notebook v0.1) ──────────────────────
SEED = 7
EPOCHS = 8
BATCH_SIZE = 64
LR = 2e-4
WEIGHT_DECAY = 1e-4
W_CORRECTION = 2.0     # el profesional NO aceptó la sugerencia (gold)
W_CONFIRM = 1.0        # aceptó la sugerencia (silver)
W_LOW_CLARITY = 0.5    # multiplica el peso si clarity.ok == False
ALLOWLIST_POLICY = "conservative"   # o "catalog_fast"
MIN_NEW_ACTION_FREQ = 2
MIN_SAMPLES_ENTRENAR = 8            # mínimo prudencial para entrenar

# Nombre de bundle por dominio (unipersonales tienen backbone GRU real)
BUNDLE_NAMES = {
    "abogado":         "abogado_unipersonal_multiceph_bundle_v1",
    "arquitecto":      "arquitectura_unipersonal_multiceph_bundle_v1",
    "contador":        "contador_multiceph_bundle_v1",
    "consultor_pyme":  "consultor_pyme_multiceph_bundle_v1",
    "diseno_producto": "diseno_produccion_unipersonal_multiceph_bundle_v1",
    "operaciones":     "logistica_multiceph_bundle_v1",
}


# ─────────────────────────────────────────────────────────────────
# Utilidades (Celda 3 del notebook)
# ─────────────────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_ts(ts: str) -> datetime:
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")
    except Exception:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _iter_jsonl(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _within_window(e: Dict[str, Any], start: datetime, end: datetime) -> bool:
    ts = e.get("timestamp")
    if not ts:
        return False
    try:
        t = _parse_ts(ts)
    except Exception:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (t >= start) and (t <= end)


def _safe_get(d: Dict[str, Any], path: List[str], default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


# ─────────────────────────────────────────────────────────────────
# Extracción de samples (Celda 7)
# ─────────────────────────────────────────────────────────────────

def _extract_sample(e: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    bi = e.get("backbone_inference") or {}
    ae = e.get("action_execution") or None
    if ae is None:
        return None

    phase = bi.get("phase", "unknown")
    probs = bi.get("phase_probs", {}) or {}
    clarity = bi.get("clarity", {}) or {}
    R = bi.get("R_score", None)

    soft_tags = _safe_get(e, ["soft_context", "soft_tags"], []) or []
    accepted = ae.get("user_accepted_suggestion", False)

    w = W_CORRECTION if (accepted is False) else W_CONFIRM
    if clarity.get("ok") is False:
        w *= W_LOW_CLARITY

    return {
        "domain": e.get("domain"),
        "node_id": e.get("node_id"),
        "phase": phase,
        "phase_probs": probs,
        "clarity": clarity,
        "R_score": float(R) if R is not None else 0.0,
        "soft_tags": soft_tags,
        "target_action_id": ae.get("action_id"),
        "target_action_label": ae.get("action_label"),
        "accepted": bool(accepted),
        "action_known": bool(ae.get("action_known", True)),
        "weight": float(w),
        "timestamp": e.get("timestamp"),
    }


def _normalize_label(x: Optional[str]) -> str:
    if not x:
        return ""
    return re.sub(r"\s+", " ", x.strip().lower())


# ─────────────────────────────────────────────────────────────────
# Bundle helpers — resolver / respaldar / reemplazar in-place
# ─────────────────────────────────────────────────────────────────

class BundleRefs:
    """Rutas relevantes de un dominio para el ajuste bimestral."""

    def __init__(self, root_dir: Path, dominio: str):
        self.root_dir = root_dir
        self.dominio = dominio
        self.bundle_name = BUNDLE_NAMES.get(dominio)
        # El bundle "activo" vive en aprendiz_motor/modelos/ (lo que carga el motor)
        from runtime_paths import get_base_dir
        self.modelos_dir = get_base_dir() / "aprendiz_motor" / "modelos"
        self.modelos_dir.mkdir(parents=True, exist_ok=True)
        self.aprendiz_dir = root_dir / "aprendiz_data"
        self.learning_log = self.aprendiz_dir / f"{dominio}_learning_log.jsonl"
        self.action_dict = self.aprendiz_dir / f"{dominio}_action_dictionary_state.json"
        self.soft_dict = self.aprendiz_dir / f"{dominio}_soft_dictionary_state.json"

    def bundle_activo(self) -> Optional[Path]:
        """Devuelve el zip del bundle activo, sembrándolo desde el repo si hace falta."""
        if not self.bundle_name:
            return None
        activo = self.modelos_dir / f"{self.bundle_name}.zip"
        if activo.exists():
            return activo
        # Sembrar desde el zip del repositorio (raíz del proyecto)
        semilla = self.root_dir.parent / f"{self.bundle_name}.zip"
        if semilla.exists():
            shutil.copy2(semilla, activo)
            logger.info(f"[AJUSTE] Bundle activo sembrado desde repo: {activo.name}")
            return activo
        return None


def _reemplazar_policy_in_place(bundle_zip: Path,
                                bundle_name: str,
                                policy_adapter_bytes: Optional[bytes],
                                allowed_actions: dict,
                                report: dict) -> dict:
    """
    Reemplaza EN SU LUGAR los artefactos de policy dentro del bundle activo.
    Conserva un respaldo .bak del bundle previo antes de sobrescribir.

    Escribe/actualiza dentro del zip, bajo {bundle_name}/policy/:
      - policy_adapter.pt
      - allowed_actions_by_phase.json
      - policy_meta.json
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = bundle_zip.with_suffix(f".bak_{ts}.zip")
    shutil.copy2(bundle_zip, backup)

    prefix = f"{bundle_name}/policy/"
    # Archivos de policy que vamos a (re)escribir — se excluyen del copiado
    reescribir = {
        prefix + "allowed_actions_by_phase.json",
        prefix + "policy_meta.json",
    }
    if policy_adapter_bytes is not None:
        reescribir.add(prefix + "policy_adapter.pt")

    tmp = bundle_zip.with_suffix(".tmp.zip")
    with zipfile.ZipFile(backup, "r") as zin, \
         zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            if item in reescribir:
                continue  # se sustituye por la nueva versión
            zout.writestr(item, zin.read(item))

        zout.writestr(prefix + "allowed_actions_by_phase.json",
                      json.dumps(allowed_actions, ensure_ascii=False, indent=2))
        policy_meta = {
            "reemplazado_at": datetime.now(timezone.utc).isoformat(),
            "run_id": report.get("run_id"),
            "training": report.get("training", {}),
            "counts": report.get("counts", {}),
            "allowlist_policy": report.get("allowlist_policy", {}),
            "adapter_incluido": policy_adapter_bytes is not None,
        }
        zout.writestr(prefix + "policy_meta.json",
                      json.dumps(policy_meta, ensure_ascii=False, indent=2))
        if policy_adapter_bytes is not None:
            zout.writestr(prefix + "policy_adapter.pt", policy_adapter_bytes)

    # Sanity-check estructural antes del reemplazo atómico: el bundle nuevo debe
    # abrirse sin errores y conservar el backbone. Si falla, se aborta y se
    # conserva el bundle original intacto (con su respaldo).
    try:
        with zipfile.ZipFile(tmp, "r") as ztest:
            if ztest.testzip() is not None:
                raise zipfile.BadZipFile("CRC inválido en el zip resultante")
            if not any(n.endswith("backbone/phase_rnn_state_dict.pt")
                       for n in ztest.namelist()):
                raise ValueError("El bundle resultante no conserva el backbone")
    except Exception as e:
        if tmp.exists():
            tmp.unlink()
        raise RuntimeError(f"Reemplazo abortado: bundle inválido tras el ajuste ({e})")

    os.replace(tmp, bundle_zip)  # reemplazo atómico en su lugar
    return {
        "bundle_reemplazado": bundle_zip.name,
        "respaldo": backup.name,
        "sha256_nuevo": _sha256_file(bundle_zip),
        "adapter_incluido": policy_adapter_bytes is not None,
    }


# ─────────────────────────────────────────────────────────────────
# Entrenamiento del PolicyAdapter (Celdas 9-11)
# ─────────────────────────────────────────────────────────────────

def _seed_all(seed: int = 7):
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
    except Exception:
        pass


def _entrenar_adapter(samples: List[dict], allowed: dict, out_dir: Path) -> dict:
    """
    Vectoriza (Celda 9), mapea acciones a clases por allowlist (Celda 10)
    y entrena el PolicyAdapter (Celda 11). Devuelve metadatos de entrenamiento.
    Requiere PyTorch. Lanza ImportError si no está disponible.
    """
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    _seed_all(SEED)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Vocabularios de features
    phase_prob_keys = sorted({k for s in samples for k in (s["phase_probs"] or {}).keys()})
    soft_vocab = sorted({t for s in samples for t in (s["soft_tags"] or [])})
    soft_index = {t: i for i, t in enumerate(soft_vocab)}

    def vectorize(s: Dict[str, Any]) -> np.ndarray:
        probs = s["phase_probs"] or {}
        clarity = s["clarity"] or {}
        v = [float(probs.get(k, 0.0)) for k in phase_prob_keys]
        v.append(1.0 if clarity.get("ok") else 0.0)
        v.append(float(clarity.get("pmax", 0.0)))
        v.append(float(clarity.get("gap", 0.0)))
        v.append(float(clarity.get("entropy", 0.0)))
        v.append(float(s.get("R_score", 0.0)))
        st = np.zeros(len(soft_vocab), dtype=np.float32)
        for t in (s.get("soft_tags") or []):
            if t in soft_index:
                st[soft_index[t]] = 1.0
        v.extend(st.tolist())
        return np.array(v, dtype=np.float32)

    X = np.stack([vectorize(s) for s in samples], axis=0)
    w = np.array([s["weight"] for s in samples], dtype=np.float32)

    allow_action_ids = sorted({a["action_id"] for ph in allowed for a in allowed[ph]})
    action_to_idx = {aid: i for i, aid in enumerate(allow_action_ids)}

    keep = [i for i, s in enumerate(samples) if s["target_action_id"] in action_to_idx]
    if not keep:
        raise ValueError("Ningún sample cae dentro de la allowlist entrenable.")

    X2 = X[keep]
    w2 = w[keep]
    y2 = np.array([action_to_idx[samples[i]["target_action_id"]] for i in keep], dtype=np.int64)

    n_clases = len(allow_action_ids)
    if n_clases < 2:
        raise ValueError("Se requieren >= 2 acciones distintas para entrenar la policy.")

    N = len(y2)
    idx = np.arange(N)
    np.random.shuffle(idx)
    cut = max(1, int(0.85 * N))
    tr, va = idx[:cut], idx[cut:]
    if len(va) == 0:
        va = tr[-1:]

    class PolicyAdapter(nn.Module):
        def __init__(self, in_dim, out_dim, hidden=256, dropout=0.1):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(in_dim, hidden), nn.ReLU(), nn.Dropout(dropout),
                nn.Linear(hidden, hidden), nn.ReLU(), nn.Dropout(dropout),
                nn.Linear(hidden, out_dim),
            )

        def forward(self, x):
            return self.net(x)

    in_dim = int(X2.shape[1])
    adapter = PolicyAdapter(in_dim, n_clases).to(device)
    opt = torch.optim.AdamW(adapter.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)

    def batch_iter(Xa, ya, wa, bs=64, shuffle=True):
        ids = np.arange(len(ya))
        if shuffle:
            np.random.shuffle(ids)
        for i in range(0, len(ya), bs):
            b = ids[i:i + bs]
            yield Xa[b], ya[b], wa[b]

    def eval_split(Xa, ya, wa):
        adapter.eval()
        correct = total = 0
        loss_sum = 0.0
        with torch.no_grad():
            for xb, yb, wb in batch_iter(Xa, ya, wa, bs=512, shuffle=False):
                xb = torch.tensor(xb, device=device)
                yb = torch.tensor(yb, device=device)
                wb = torch.tensor(wb, device=device)
                logits = adapter(xb)
                loss = (F.cross_entropy(logits, yb, reduction="none") * wb).mean()
                loss_sum += float(loss.item()) * len(yb)
                correct += int((logits.argmax(dim=-1) == yb).sum().item())
                total += int(len(yb))
        return {"loss": loss_sum / max(total, 1), "acc": correct / max(total, 1)}

    best = {"val_loss": float("inf"), "epoch": -1}
    history = []
    adapter_path = out_dir / "policy_adapter.pt"
    for ep in range(1, EPOCHS + 1):
        adapter.train()
        for xb, yb, wb in batch_iter(X2[tr], y2[tr], w2[tr], bs=BATCH_SIZE, shuffle=True):
            xb = torch.tensor(xb, device=device)
            yb = torch.tensor(yb, device=device)
            wb = torch.tensor(wb, device=device)
            logits = adapter(xb)
            loss = (F.cross_entropy(logits, yb, reduction="none") * wb).mean()
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(adapter.parameters(), 1.0)
            opt.step()
        tr_m = eval_split(X2[tr], y2[tr], w2[tr])
        va_m = eval_split(X2[va], y2[va], w2[va])
        history.append({"epoch": ep, "train": tr_m, "val": va_m})
        if va_m["loss"] < best["val_loss"]:
            best = {"val_loss": va_m["loss"], "epoch": ep}
            torch.save(adapter.state_dict(), adapter_path)

    if not adapter_path.exists():  # asegurar que siempre exista un checkpoint
        torch.save(adapter.state_dict(), adapter_path)

    (out_dir / "train_history.json").write_text(
        json.dumps(history, indent=2), encoding="utf-8")
    (out_dir / "soft_vocab.json").write_text(
        json.dumps(soft_vocab, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "action_vocab.json").write_text(
        json.dumps(allow_action_ids, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "entrenado": True,
        "device": device,
        "epochs": EPOCHS,
        "batch_size": BATCH_SIZE,
        "lr": LR,
        "weight_decay": WEIGHT_DECAY,
        "best_epoch": best["epoch"],
        "best_val_loss": best["val_loss"],
        "in_dim": in_dim,
        "out_dim": n_clases,
        "phase_prob_keys": phase_prob_keys,
        "soft_vocab_size": len(soft_vocab),
        "samples_after_allowlist": int(len(y2)),
        "adapter_path": str(adapter_path),
    }


# ─────────────────────────────────────────────────────────────────
# API pública — ejecutar el ajuste bimestral completo
# ─────────────────────────────────────────────────────────────────

def ejecutar_ajuste_bimestral(dominio: str,
                              root_dir: Path,
                              window_start: Optional[datetime] = None,
                              window_end: Optional[datetime] = None,
                              period_index: Optional[int] = None,
                              disparado_por: str = "manual") -> dict:
    """
    Ejecuta el ajuste bimestral completo para un dominio, portando el notebook.
    Devuelve el reporte (bimester_report.json). Reemplaza el policy del bundle
    activo EN SU LUGAR cuando hay un bundle disponible.
    """
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    now = datetime.now(timezone.utc)
    if window_end is None:
        window_end = now
    if window_start is None:
        window_start = window_end - timedelta(days=50)

    refs = BundleRefs(root_dir, dominio)
    out_dir = refs.aprendiz_dir / "ajustes" / dominio / f"bimester_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Cargar histórico bimestral (learning log)
    eventos = []
    if refs.learning_log.exists():
        eventos = [e for e in _iter_jsonl(refs.learning_log)
                   if _within_window(e, window_start, window_end)]

    # 2. Extraer samples supervisados
    samples = []
    for e in eventos:
        s = _extract_sample(e)
        if s is not None and s["target_action_id"]:
            samples.append(s)

    new_actions_obs = [s for s in samples if s["action_known"] is False]
    freq_new = Counter([(s["phase"], s["target_action_id"]) for s in new_actions_obs])

    # 3. Catálogo + allowlist por fase (Celda 8)
    action_state = {}
    if refs.action_dict.exists():
        try:
            action_state = json.loads(refs.action_dict.read_text(encoding="utf-8"))
        except Exception:
            action_state = {}
    actions_by_phase = action_state.get("actions_by_phase", {})

    catalog = {ph: list(v) for ph, v in actions_by_phase.items()}
    added = []
    for s in new_actions_obs:
        ph = s["phase"]
        aid = s["target_action_id"]
        label = s["target_action_label"] or aid
        catalog.setdefault(ph, [])
        existing = {a.get("action_id") for a in catalog[ph] if isinstance(a, dict)}
        if aid not in existing:
            catalog[ph].append({"action_id": aid, "label": label})
            added.append({"phase": ph, "action_id": aid, "label": label,
                          "first_seen": s["timestamp"], "domain": s["domain"],
                          "node_id": s["node_id"]})

    allowed = {ph: [] for ph in catalog.keys()}
    for ph, lst in catalog.items():
        if ALLOWLIST_POLICY == "catalog_fast":
            allowed[ph] = lst
        else:
            allow_ids = {a.get("action_id") for a in actions_by_phase.get(ph, [])
                         if isinstance(a, dict)}
            for a in lst:
                aid = a.get("action_id") if isinstance(a, dict) else None
                if aid and freq_new.get((ph, aid), 0) >= MIN_NEW_ACTION_FREQ:
                    allow_ids.add(aid)
            allowed[ph] = [a for a in lst if isinstance(a, dict)
                           and a.get("action_id") in allow_ids]

    (out_dir / "actions_added_this_bimester.json").write_text(
        json.dumps(added, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "allowed_actions_by_phase.json").write_text(
        json.dumps(allowed, ensure_ascii=False, indent=2), encoding="utf-8")

    # 4. Entrenar PolicyAdapter (si hay torch y datos suficientes)
    allow_action_ids = sorted({a["action_id"] for ph in allowed for a in allowed[ph]})
    training: Dict[str, Any] = {"entrenado": False}
    if len(samples) >= MIN_SAMPLES_ENTRENAR and len(allow_action_ids) >= 2:
        try:
            training = _entrenar_adapter(samples, allowed, out_dir)
        except ImportError:
            training = {"entrenado": False, "motivo": "PyTorch no disponible"}
        except Exception as e:
            training = {"entrenado": False, "motivo": f"error_entrenamiento: {e}"}
    else:
        training = {
            "entrenado": False,
            "motivo": f"datos insuficientes (samples={len(samples)}, "
                      f"acciones_allowlist={len(allow_action_ids)}; "
                      f"minimo={MIN_SAMPLES_ENTRENAR} y >=2 acciones)",
        }

    # 5. Bundle activo + reemplazo in-place del policy
    bundle_zip = refs.bundle_activo()
    reemplazo = None
    bundle_sha_previo = None
    if bundle_zip is not None:
        bundle_sha_previo = _sha256_file(bundle_zip)
        adapter_path = out_dir / "policy_adapter.pt"
        adapter_bytes = adapter_path.read_bytes() if adapter_path.exists() else None
        report_parcial = {
            "run_id": run_id,
            "training": training,
            "allowlist_policy": {"mode": ALLOWLIST_POLICY,
                                 "min_new_action_freq": MIN_NEW_ACTION_FREQ},
            "counts": {"allow_vocab_size": len(allow_action_ids)},
        }
        reemplazo = _reemplazar_policy_in_place(
            bundle_zip, refs.bundle_name, adapter_bytes, allowed, report_parcial)

    # 6. Reporte final (Celda 12)
    report = {
        "run_id": run_id,
        "dominio": dominio,
        "disparado_por": disparado_por,
        "period_index": period_index,
        "ejecutado_at": now.isoformat(),
        "time_window": {"start": window_start.isoformat(),
                        "end": window_end.isoformat()},
        "bundle": {
            "nombre": refs.bundle_name,
            "activo": bundle_zip.name if bundle_zip else None,
            "sha256_previo": bundle_sha_previo,
            "reemplazo_in_place": reemplazo,
        },
        "counts": {
            "events_in_window": len(eventos),
            "samples_supervised": len(samples),
            "new_actions_observed": len(new_actions_obs),
            "actions_added_to_catalog": len(added),
            "allow_vocab_size": len(allow_action_ids),
        },
        "allowlist_policy": {"mode": ALLOWLIST_POLICY,
                             "min_new_action_freq": MIN_NEW_ACTION_FREQ},
        "training": training,
        "output_dir": str(out_dir),
    }
    (out_dir / "bimester_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Empaquetar salidas del run
    try:
        shutil.make_archive(str(out_dir), "zip", root_dir=out_dir)
        report["zip"] = f"{out_dir}.zip"
    except Exception as e:
        logger.warning(f"[AJUSTE] No se pudo empaquetar el run: {e}")

    logger.info(f"[AJUSTE] Ajuste bimestral {dominio} run={run_id} "
                f"entrenado={training.get('entrenado')} "
                f"reemplazo={'sí' if reemplazo else 'no'}")
    return report
