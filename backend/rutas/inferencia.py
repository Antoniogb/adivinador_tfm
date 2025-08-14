# rutas/inferencia.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Tuple, Optional
import json
import numpy as np
import pandas as pd
import os
from math import log
from db_sql import cargar_personajes  # <-- tu loader SQL -> DataFrame

router = APIRouter()

# ---------------------------------------------------------------------
#  Modelos de request
# ---------------------------------------------------------------------
class RespuestasUsuario(BaseModel):
    respuestas: Dict[str, int | None]

class EstadoUsuario(BaseModel):
    respuestas: Dict[str, int | None] = {}
    excluidas: List[str] = []  # opcional: atributos a no considerar


# ---------------------------------------------------------------------
#  Configuración / Paths de redes temáticas
# ---------------------------------------------------------------------
RUTAS_CONFIG = {
    "poderes":               "./adivinador_backend/bayes_tematica/config_poderes.json",
    "afiliaciones_heroes":   "./adivinador_backend/bayes_tematica/config_afiliaciones_heroes.json",
    "afiliaciones_villanos": "./adivinador_backend/bayes_tematica/config_afiliaciones_villanos.json",
    "especie":               "./adivinador_backend/bayes_tematica/config_especie.json",
    "origen":                "./adivinador_backend/bayes_tematica/config_origen.json",
    "armas":                 "./adivinador_backend/bayes_tematica/config_armas.json",
    "genero_ocupacion":      "./adivinador_backend/bayes_tematica/config_genero_ocupacion.json",
}

ALPHA = 1.0   # suavizado de Laplace
EPS   = 1e-9  # para evitar log(0)

# ---------------------------------------------------------------------
#  Cache en memoria
# ---------------------------------------------------------------------
# MODELOS[red] = {
#   "personajes": [str, ...],
#   "prior_log": np.ndarray (nP),
#   "attr_logs": { attr: {0: np.ndarray(nP), 1: np.ndarray(nP)} },
#   "attrs": [str, ...]
# }
MODELOS: dict[str, dict] = {}
PERSONAJES_CANON: List[str] = []  # orden canónico de personajes

# Mongo opcional para texto de preguntas
try:
    from db import db as mongo_db  # colección "preguntas"
except Exception:
    mongo_db = None


# ---------------------------------------------------------------------
#  Helpers de entrenamiento/carga
# ---------------------------------------------------------------------
def _cargar_config(ruta: str) -> List[str]:
    with open(ruta, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return list(cfg.get("atributos", []))

def _entrenar_red(df: pd.DataFrame, attrs: List[str]) -> dict:
    """
    Entrena Naive Bayes binario P(personaje) y P(attr|personaje) con Laplace.
    df debe tener 'personaje' (nombres) + attrs binarios 0/1.
    """
    attrs = [a for a in attrs if a in df.columns]
    if not attrs:
        raise ValueError("Sin atributos válidos para esta red")

    global PERSONAJES_CANON
    if not PERSONAJES_CANON:
        PERSONAJES_CANON = list(df["personaje"].astype(str).unique())

    # Conteos por personaje
    conteo_personaje = df["personaje"].value_counts().reindex(PERSONAJES_CANON, fill_value=0).astype(float)
    total = float(conteo_personaje.sum())
    prior = (conteo_personaje + ALPHA) / (total + ALPHA * len(PERSONAJES_CANON))
    prior_log = np.log(np.clip(prior.values, EPS, None))

    attr_logs: dict[str, dict[int, np.ndarray]] = {}
    for a in attrs:
        true_count = df.groupby("personaje")[a].sum().reindex(PERSONAJES_CANON, fill_value=0).astype(float)
        n_p = conteo_personaje
        p1 = (true_count + ALPHA) / (n_p + 2.0 * ALPHA)
        p0 = 1.0 - p1
        attr_logs[a] = {
            1: np.log(np.clip(p1.values, EPS, None)),
            0: np.log(np.clip(p0.values, EPS, None)),
        }

    return {
        "personajes": PERSONAJES_CANON,
        "prior_log": prior_log,
        "attr_logs": attr_logs,
        "attrs": attrs,
    }

def _asegurar_modelos(df: pd.DataFrame):
    """
    Entrena y cachea modelos si no están ya listos.
    df: contiene al menos 'nombre'/'personaje' y columnas binarias 0/1.
    """
    global MODELOS, PERSONAJES_CANON

    if "personaje" not in df.columns:
        df = df.copy()
        df["personaje"] = df["nombre"]

    # Fuerza 0/1 en todas las columnas binarias
    bin_cols = [c for c in df.columns if c not in ("personaje", "nombre", "id")]
    df[bin_cols] = df[bin_cols].fillna(0).astype(int)

    if not PERSONAJES_CANON:
        PERSONAJES_CANON = list(df["personaje"].astype(str).unique())

    for nombre_red, ruta in RUTAS_CONFIG.items():
        if nombre_red in MODELOS:
            continue
        if not os.path.exists(ruta):
            print(f"⚠️  Config no encontrada para red '{nombre_red}': {ruta} (se ignora)")
            continue
        try:
            attrs = _cargar_config(ruta)
            subset_cols = ["personaje"] + [a for a in attrs if a in df.columns]
            modelo = _entrenar_red(df[subset_cols], attrs)
            MODELOS[nombre_red] = modelo
            print(f"✅ Red '{nombre_red}' entrenada con {len(modelo['attrs'])} atributos")
        except Exception as e:
            print(f"❌ Error entrenando red '{nombre_red}': {e}")


# ---------------------------------------------------------------------
#  Helpers de inferencia/combinar
# ---------------------------------------------------------------------
def _posterior_por_red(modelo: dict, evidencia: Dict[str, int | None]) -> Tuple[np.ndarray, int]:
    """
    Devuelve (log_posterior_normalizado, evidencia_utilizada)
    Usa solo attrs presentes en evidencia (0/1) y existentes en el modelo.
    """
    suma = modelo["prior_log"].copy()
    usados = 0
    for a, v in evidencia.items():
        if v is None:
            continue
        if a not in modelo["attrs"]:
            continue
        if v not in (0, 1):
            continue
        suma += modelo["attr_logs"][a][v]
        usados += 1

    # normaliza (softmax estable)
    m = float(np.max(suma))
    exps = np.exp(suma - m)
    probs = exps / np.sum(exps)
    log_post = np.log(np.clip(probs, EPS, None))
    return log_post, usados

def _combinar_redes(resultados: List[Tuple[np.ndarray, int]]) -> np.ndarray:
    """
    Combina posteriors con peso = max(1, evidencia_en_red).
    Trabaja en log-espacio y devuelve probs normalizadas.
    """
    if not resultados:
        raise ValueError("No hay resultados de redes")
    acumulado = None
    for logp, usados in resultados:
        peso = max(1, usados)
        term = peso * logp
        acumulado = term if acumulado is None else acumulado + term

    m = float(np.max(acumulado))
    exps = np.exp(acumulado - m)
    probs = exps / np.sum(exps)
    return probs

def _posterior_actual(respuestas: Dict[str, int | None]) -> Tuple[List[str], np.ndarray]:
    """
    Usa los MODELOS cacheados para obtener P(personaje | respuestas) actual.
    Devuelve (lista_personajes, vector_probs).
    """
    if not MODELOS:
        raise RuntimeError("MODELOS no entrenados. Llama a /inferir tras arrancar o entrena con _asegurar_modelos.")
    resultados_red = []
    for nombre_red, modelo in MODELOS.items():
        try:
            logp, usados = _posterior_por_red(modelo, respuestas)
            resultados_red.append((logp, usados))
        except Exception as e:
            print(f"❌ Error en red {nombre_red}: {e}")
    if not resultados_red:
        raise RuntimeError("No se pudo calcular ninguna red para el estado actual.")
    probs = _combinar_redes(resultados_red)
    personajes = MODELOS[next(iter(MODELOS))]["personajes"]
    return personajes, probs

def _entropia(probs: np.ndarray) -> float:
    p = np.clip(probs, EPS, None)
    return float(-np.sum(p * (np.log(p) / np.log(2.0))))

def _p_attr_1(attr: str, personajes: List[str], p_personaje: np.ndarray) -> Optional[float]:
    """
    Estima P(attr=1) = sum_p P(p)*P(attr=1|p) usando la primera red que contenga el attr.
    """
    for modelo in MODELOS.values():
        if attr in modelo["attrs"]:
            p1 = np.exp(modelo["attr_logs"][attr][1])  # vector por personaje
            return float(np.sum(p_personaje * p1))
    return None

def _ganancia_por_atributo(attr: str, respuestas: Dict[str, int | None]) -> Optional[Tuple[float, float, float]]:
    """
    Devuelve (ganancia_info, H0, H1) o None si no se puede evaluar.
    Considera respuestas binarias (0/1).
    """
    if attr in respuestas and respuestas[attr] is not None:
        return None
    try:
        # Distribución actual
        personajes, p_cur = _posterior_actual(respuestas)
        H_cur = _entropia(p_cur)

        # P(attr=1) bajo estado actual
        p1 = _p_attr_1(attr, personajes, p_cur)
        if p1 is None:
            return None
        p1 = max(0.0, min(1.0, p1))
        p0 = 1.0 - p1

        # Posterior si respondiera 1
        r1 = dict(respuestas); r1[attr] = 1
        _, p_post1 = _posterior_actual(r1)
        H1 = _entropia(p_post1)

        # Posterior si respondiera 0
        r0 = dict(respuestas); r0[attr] = 0
        _, p_post0 = _posterior_actual(r0)
        H0 = _entropia(p_post0)

        H_exp = p1 * H1 + p0 * H0
        gain = H_cur - H_exp
        return (float(gain), float(H0), float(H1))
    except Exception as e:
        print(f"⚠️  No se pudo evaluar ganancia para '{attr}': {e}")
        return None

def _texto_atributo(attr: str) -> Optional[str]:
    """
    Busca el texto de la pregunta en Mongo (colección 'preguntas').
    Esquema esperado: { atributo: 'es_vengador', texto: '¿Es vengador?', activa: true }
    """
    if mongo_db is None:
        return None
    try:
        doc = mongo_db["preguntas"].find_one({"atributo": attr}, {"_id": 0, "texto": 1})
        return doc.get("texto") if doc else None
    except Exception:
        return None


# ---------------------------------------------------------------------
#  Endpoint: Inferencia con umbral del 50%
# ---------------------------------------------------------------------
@router.post("/inferir")
def inferir_personaje(datos: RespuestasUsuario):
    print("⚡ INFERENCIA ACTIVADA:", datos.respuestas)
    try:
        # A) Cargar dataset y asegurar modelos (solo primera vez tras arranque)
        df = cargar_personajes()
        if "personaje" not in df.columns:
            df["personaje"] = df["nombre"]
        if "id" in df.columns:
            df = df.drop(columns=["id"])
        _asegurar_modelos(df)

        # B) Posterior actual
        personajes, probs = _posterior_actual(datos.respuestas)
        pares = list(zip(personajes, probs.tolist()))
        pares.sort(key=lambda x: x[1], reverse=True)

        # C) Umbral 0.5 para propuesta
        umbral_alcanzado = False
        candidato = None
        if pares and pares[0][1] >= 0.5:
            umbral_alcanzado = True
            candidato = pares[0][0]

        top5 = pares[:5]
        print("🔍 TOP 3:", top5[:3])
        return {
            "resultado": top5,
            "umbral": umbral_alcanzado,
            "candidato": candidato
        }

    except Exception as e:
        print("❌ ERROR GENERAL en inferencia:", e)
        raise HTTPException(status_code=500, detail="Error en inferencia mejorada")


# ---------------------------------------------------------------------
#  Endpoint: Preguntas adaptativas (ganancia de información)
# ---------------------------------------------------------------------
@router.post("/pregunta_siguiente")
def pregunta_siguiente(estado: EstadoUsuario):
    """
    Elige el siguiente atributo que maximiza la ganancia de información.
    Devuelve { atributo, texto?, ganancia, p1, H_si_0, H_si_1 }.
    """
    try:
        # Asegura MODELOS listos (por si no se llamó /inferir aún)
        if not MODELOS:
            df = cargar_personajes()
            if "personaje" not in df.columns:
                df["personaje"] = df["nombre"]
            if "id" in df.columns:
                df = df.drop(columns=["id"])
            _asegurar_modelos(df)

        # Candidatos = todos los attrs de todas las redes menos los excluidos/ya respondidos
        candidatos: set[str] = set()
        for modelo in MODELOS.values():
            candidatos.update(modelo["attrs"])

        excl = set(estado.excluidas or [])
        for k, v in (estado.respuestas or {}).items():
            if v is not None:
                excl.add(k)

        candidatos = [a for a in candidatos if a not in excl]
        if not candidatos:
            return {"atributo": None, "ganancia": 0.0, "mensaje": "No quedan preguntas útiles."}

        mejor_attr = None
        mejor_gain = -1e9
        mejor_H0 = None
        mejor_H1 = None

        for a in candidatos:
            res = _ganancia_por_atributo(a, estado.respuestas or {})
            if res is None:
                continue
            gain, H0, H1 = res
            if gain > mejor_gain:
                mejor_gain = gain
                mejor_attr = a
                mejor_H0 = H0
                mejor_H1 = H1

        if mejor_attr is None:
            return {"atributo": None, "ganancia": 0.0, "mensaje": "No se pudo evaluar ninguna pregunta."}

        # Texto descriptivo si está en Mongo
        txt = _texto_atributo(mejor_attr)

        # P(attr=1) bajo el estado actual (útil para UI)
        personajes, p_cur = _posterior_actual(estado.respuestas or {})
        p1 = _p_attr_1(mejor_attr, personajes, p_cur)
        p1 = float(max(0.0, min(1.0, p1))) if p1 is not None else None

        return {
            "atributo": mejor_attr,
            "texto": txt,
            "ganancia": float(mejor_gain),
            "p1": p1,
            "H_si_0": float(mejor_H0) if mejor_H0 is not None else None,
            "H_si_1": float(mejor_H1) if mejor_H1 is not None else None,
        }

    except Exception as e:
        print("❌ ERROR en /pregunta_siguiente:", e)
        raise HTTPException(status_code=500, detail="Error calculando la pregunta siguiente")
