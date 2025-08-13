from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Tuple
from db_sql import cargar_personajes
import json
import numpy as np
import pandas as pd
import os
from math import log, exp

router = APIRouter()

class RespuestasUsuario(BaseModel):
    respuestas: Dict[str, int | None]

# -------------------
# CONFIG
# -------------------
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

# -------------------
# CACHE DE MODELOS
# -------------------
# Para cada red guardamos:
# {
#   "personajes": [str, ...],
#   "prior_log": np.array(n_personajes),
#   "attr_logs": {
#       attr: {
#           0: np.array(n_personajes)  # log P(attr=0 | personaje)
#           1: np.array(n_personajes)  # log P(attr=1 | personaje)
#       }, ...
#   },
#   "attrs": [attr, ...]
# }
MODELOS: dict[str, dict] = {}
PERSONAJES_CANON: List[str] = []  # orden canónico de personajes


def _entrenar_red(df: pd.DataFrame, attrs: List[str]) -> dict:
    """
    Entrena Naive Bayes binario P(personaje) y P(attr|personaje) con Laplace.
    """
    # Asegura columnas binarias 0/1 presentes
    attrs = [a for a in attrs if a in df.columns]
    if not attrs:
        raise ValueError("Sin atributos válidos para esta red")

    # Personajes y orden canónico
    global PERSONAJES_CANON
    if not PERSONAJES_CANON:
        PERSONAJES_CANON = df["personaje"].tolist() if df["personaje"].dtype != object else df["personaje"].unique().tolist()

    # Si "personaje" es nombre, mantenemos PERSONAJES_CANON como lista de nombres
    # y construimos vista por personaje
    # Contadores por personaje
    # prior: conteo de cada personaje
    conteo_personaje = df["personaje"].value_counts().reindex(PERSONAJES_CANON, fill_value=0).astype(float)
    total = float(conteo_personaje.sum())
    prior = (conteo_personaje + ALPHA) / (total + ALPHA * len(PERSONAJES_CANON))
    prior_log = np.log(np.clip(prior.values, EPS, None))

    # Para cada atributo binario, contamos #1 y #0 por personaje
    attr_logs = {}
    for a in attrs:
        # valores 0/1; si hay NaN, tratamos como 0 (o podrías ignorarlos)
        col = df[a].fillna(0).astype(int)
        # agrupamos por personaje
        # true_count[p] = cuántas filas de p tienen a==1
        true_count = df.groupby("personaje")[a].sum().reindex(PERSONAJES_CANON, fill_value=0).astype(float)
        # total por personaje
        n_p = conteo_personaje

        # Laplace: P(a=1|p) = (true_count + α) / (n_p + 2α)
        p1 = (true_count + ALPHA) / (n_p + 2.0 * ALPHA)
        p0 = 1.0 - p1

        # guarda logs
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


def _cargar_config(ruta: str) -> List[str]:
    with open(ruta, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # esperamos {"atributos": ["a","b",...]}
    return list(cfg.get("atributos", []))


def _asegurar_modelos(df: pd.DataFrame):
    """
    Entrena y cachea modelos si no están ya listos.
    """
    global MODELOS, PERSONAJES_CANON

    # Normaliza df: columna 'personaje' (nombres) y asegura 0/1 en attrs
    if "nombre" in df.columns and "personaje" not in df.columns:
        df = df.copy()
        df["personaje"] = df["nombre"]

    # Asegura binarios 0/1 en todo lo que no sea 'personaje' (si hay NaN -> 0)
    bin_cols = [c for c in df.columns if c not in ("personaje", "nombre", "id")]
    df[bin_cols] = df[bin_cols].fillna(0).astype(int)

    # Fija orden canónico de personajes (nombres)
    if not PERSONAJES_CANON:
        # usa el orden de aparición
        PERSONAJES_CANON = list(df["personaje"].astype(str).unique())

    # Entrena cada red si falta
    for nombre_red, ruta in RUTAS_CONFIG.items():
        if nombre_red in MODELOS:
            continue
        if not os.path.exists(ruta):
            # si no existe el config, sáltala
            print(f"⚠️  Config no encontrada para red '{nombre_red}': {ruta} (se ignora esta red)")
            continue
        try:
            attrs = _cargar_config(ruta)
            modelo = _entrenar_red(df[["personaje"] + [a for a in attrs if a in df.columns]], attrs)
            MODELOS[nombre_red] = modelo
            print(f"✅ Red '{nombre_red}' entrenada con {len(modelo['attrs'])} atributos")
        except Exception as e:
            print(f"❌ Error entrenando red '{nombre_red}': {e}")


def _posterior_por_red(modelo: dict, evidencia: Dict[str, int | None]) -> Tuple[np.ndarray, int]:
    """
    Devuelve (log_posterior_normalizado, evidencia_utilizada)
    Solo usa atributos presentes en evidencia y que existan en el modelo.
    """
    prior_log = modelo["prior_log"].copy()
    attrs = modelo["attrs"]
    attr_logs = modelo["attr_logs"]

    usados = 0
    suma = prior_log.copy()
    for a, v in evidencia.items():
        if v is None:
            continue
        if a not in attrs:
            continue
        if v not in (0, 1):
            continue
        suma += attr_logs[a][v]
        usados += 1

    # normaliza para obtener probs: softmax estable
    m = float(np.max(suma))
    exps = np.exp(suma - m)
    probs = exps / np.sum(exps)
    # para combinar entre redes, volvemos a log con EPS
    log_post = np.log(np.clip(probs, EPS, None))
    return log_post, usados


def _combinar_redes(resultados: List[Tuple[np.ndarray, int]]) -> np.ndarray:
    """
    Combina posteriors de cada red con peso = max(1, evidencia_usada_en_red).
    Trabaja en log-espacio para estabilidad.
    """
    if not resultados:
        raise ValueError("No hay resultados de redes")

    # suma ponderada de log-probs
    acumulado = None
    for logp, usados in resultados:
        peso = max(1, usados)  # si una red no aporta evidencia, que pese 1 (neutral)
        term = peso * logp
        acumulado = term if acumulado is None else acumulado + term

    # normaliza
    m = float(np.max(acumulado))
    exps = np.exp(acumulado - m)
    probs = exps / np.sum(exps)
    return probs  # vector de tamaño n_personajes


@router.post("/inferir")
def inferir_personaje(datos: RespuestasUsuario):
    print("⚡ INFERENCIA ACTIVADA:", datos.respuestas)
    try:
        # 1) Cargar dataset de entrenamiento (SQL -> DataFrame)
        df = cargar_personajes()  # debe incluir columnas binarias y 'nombre'
        if "personaje" not in df.columns:
            df["personaje"] = df["nombre"]
        if "id" in df.columns:
            df = df.drop(columns=["id"])

        # 2) Entrenar/cargar modelos (cache)
        _asegurar_modelos(df)

        if not MODELOS:
            raise RuntimeError("No hay redes entrenadas ni configs válidas.")

        # 3) Para cada red, obtener posterior y evidencia usada
        resultados_red = []
        for nombre_red, modelo in MODELOS.items():
            try:
                logp, usados = _posterior_por_red(modelo, datos.respuestas)
                resultados_red.append((logp, usados))
            except Exception as e:
                print(f"❌ Error en red {nombre_red}: {e}")

        if not resultados_red:
            raise RuntimeError("No se pudo calcular ninguna red.")

        # 4) Combinar redes (suma ponderada de log-posteriors)
        probs = _combinar_redes(resultados_red)

        # 5) Armar salida ordenada
        personajes = MODELOS[next(iter(MODELOS))]["personajes"]  # orden canónico
        pares = list(zip(personajes, probs.tolist()))
        pares.sort(key=lambda x: x[1], reverse=True)

        # 6) Umbral 50%
        umbral_alcanzado = False
        personaje_candidato = None
        if pares and pares[0][1] >= 0.5:
            umbral_alcanzado = True
            personaje_candidato = pares[0][0]

        top5 = pares[:5]
        print("🔍 TOP 3:", top5[:3])

        return {
            "resultado": top5,
            "umbral": umbral_alcanzado,
            "candidato": personaje_candidato
        }

    except Exception as e:
        print("❌ ERROR GENERAL en inferencia:", e)
        raise HTTPException(status_code=500, detail="Error en inferencia mejorada")
