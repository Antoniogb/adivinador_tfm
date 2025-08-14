# rutas/pregunta_siguiente.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional, Tuple
import json, math
import pandas as pd
from sqlalchemy import create_engine
from pgmpy.models import DiscreteBayesianNetwork
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination
from pymongo import MongoClient

# ----------------------
# CONFIG BBDD (ajusta si es necesario)
# ----------------------
MYSQL_DSN = "mysql+mysqlconnector://fastapi:frambuesa22@localhost/personajes_marvel"
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "adivinador_tfm"
MONGO_PREGUNTAS_COL = "preguntas"

# Configs de redes (asegúrate de que existen)
CONFIG_FILES = [
    "./adivinador_backend/bayes_tematica/config_poderes.json",
    "./adivinador_backend/bayes_tematica/config_afiliaciones_heroes.json",
    "./adivinador_backend/bayes_tematica/config_afiliaciones_villanos.json",
    "./adivinador_backend/bayes_tematica/config_especie.json",
    "./adivinador_backend/bayes_tematica/config_origen.json",
    "./adivinador_backend/bayes_tematica/config_armas.json",
    "./adivinador_backend/bayes_tematica/config_genero_ocupacion.json",
]

router = APIRouter()

# ----------------------
# Entrada/salida
# ----------------------
class ReqSiguiente(BaseModel):
    respuestas: Dict[str, Optional[int]] = {}
    excluidas: Optional[List[str]] = None  # por si el front quiere forzar exclusión

class RspSiguiente(BaseModel):
    atributo: Optional[str] = None
    texto: Optional[str] = None
    info_gain: Optional[float] = None

# ----------------------
# Utilidades de red bayesiana (idénticas al /inferir)
# ----------------------
def cargar_personajes() -> pd.DataFrame:
    engine = create_engine(MYSQL_DSN)
    df = pd.read_sql("SELECT * FROM personajes", engine)
    df["personaje"] = df["nombre"]
    if "id" in df.columns:
        df = df.drop(columns=["id"])
    return df

def cargar_red_desde_config(config_path: str, df: pd.DataFrame) -> Tuple[VariableElimination, List[str], List[str]]:
    with open(config_path) as f:
        config = json.load(f)

    atributos = [a for a in config["atributos"] if a in df.columns]
    df2 = df.dropna(subset=["personaje"]).copy()
    # binario 0/1
    df2[atributos] = df2[atributos].fillna(0).astype(int)

    personajes = df2["personaje"].unique().tolist()
    # mapeo a índices
    df2["personaje"] = df2["personaje"].map({p: i for i, p in enumerate(personajes)})

    # Grafo estrella: atributos -> personaje
    modelo = DiscreteBayesianNetwork([(a, "personaje") for a in atributos])
    cpds = []

    # Priors de atributos (Bernoulli con p = media)
    for a in atributos:
        p = float(df2[a].mean())
        cpds.append(TabularCPD(variable=a, variable_card=2, values=[[1 - p], [p]]))

    # CPD de personaje condicionado a todos los atributos (conteo + smoothing)
    group = df2.groupby(atributos + ["personaje"]).size().unstack(fill_value=0)
    # Rellenar todas combinaciones de atributos
    index = pd.MultiIndex.from_product([sorted(df2[a].unique()) for a in atributos], names=atributos)
    group = group.reindex(index, fill_value=0)
    matriz = group.T.values.astype(float)

    # suavizado simple (Laplace)
    matriz = matriz + 1.0
    for i in range(matriz.shape[1]):
        total = matriz[:, i].sum()
        matriz[:, i] = matriz[:, i] / total

    cpd_personaje = TabularCPD(
        variable="personaje",
        variable_card=len(personajes),
        values=matriz.tolist(),
        evidence=atributos,
        evidence_card=[2 for _ in atributos]
    )
    cpds.append(cpd_personaje)
    modelo.add_cpds(*cpds)
    assert modelo.check_model()
    return VariableElimination(modelo), personajes, atributos

def combinar_resultados(resultados: List[Dict[str, float]]) -> Dict[str, float]:
    # Producto normalizado de varias redes
    combinada = {}
    for r in resultados:
        for k, v in r.items():
            combinada[k] = combinada.get(k, 1.0) * float(v)
    total = sum(combinada.values()) or 1.0
    return {k: v / total for k, v in combinada.items()}

def posterior_personaje(evidencia: Dict[str, Optional[int]]) -> Tuple[Dict[str,float], pd.DataFrame]:
    """Combina varias redes temáticas para obtener P(personaje | evidencia)."""
    df = cargar_personajes()
    redes = CONFIG_FILES
    resultados = []

    for path in redes:
        try:
            infer, personajes, attrs = cargar_red_desde_config(path, df)
            evidencia_valida = {k: v for k, v in evidencia.items() if v is not None and k in attrs}
            if evidencia_valida:
                q = infer.query(["personaje"], evidence=evidencia_valida, show_progress=False)
                res = {personajes[i]: float(prob) for i, prob in enumerate(q.values)}
            else:
                # distribución uniforme si no hay evidencia para esa red
                res = {p: 1.0 / len(personajes) for p in personajes}
            resultados.append(res)
        except Exception as e:
            # Si falla alguna red, la ignoramos (robustez)
            print(f"⚠ red ignorada {path}: {e}")

    if not resultados:
        # fallback uniforme si todo falla
        nombres = cargar_personajes()["personaje"].unique().tolist()
        return ({p: 1.0 / len(nombres) for p in nombres}, df)

    return combinar_resultados(resultados), df

# ----------------------
# Entropía / Information Gain
# ----------------------
def entropy(dist: Dict[str, float]) -> float:
    return -sum(p * math.log(p + 1e-12, 2) for p in dist.values())

def mezclar_con_evidencia(base_ev: Dict[str, Optional[int]], atributo: str, valor: int) -> Dict[str, Optional[int]]:
    ev = dict(base_ev)
    ev[atributo] = valor
    return ev

def estimar_p_attr1(posterior: Dict[str,float], df: pd.DataFrame, atributo: str) -> float:
    # Asumimos atributo ~ determinista por personaje (0/1), estimamos P(attr=1) = sum_p P(p)*attr(p)
    if atributo not in df.columns:
        return 0.5
    # tomamos el valor modal por personaje (si hay duplicados)
    vals = df[["personaje", atributo]].drop_duplicates().set_index("personaje")[atributo].to_dict()
    return sum(posterior.get(p, 0.0) * float(vals.get(p, 0.0)) for p in posterior.keys())

# ----------------------
# Mongo para recuperar el texto de la pregunta
# ----------------------
def texto_pregunta(atributo: str) -> Optional[str]:
    try:
        cli = MongoClient(MONGO_URI)
        col = cli[MONGO_DB][MONGO_PREGUNTAS_COL]
        doc = col.find_one({"atributo": atributo, "activa": True}, {"_id": 0, "texto": 1})
        return (doc or {}).get("texto")
    except Exception:
        return None

# ----------------------
# ENDPOINT principal
# ----------------------
@router.post("/pregunta_siguiente", response_model=RspSiguiente)
def pregunta_siguiente(req: ReqSiguiente):
    # 1) Posterior actual
    try:
        post, df = posterior_personaje(req.respuestas)
    except Exception as e:
        print("❌ Error posterior:", e)
        raise HTTPException(status_code=500, detail="Error calculando posterior")

    prior_H = entropy(post)

    # 2) Candidatos: atributos presentes en dataset menos los ya respondidos/excluidos
    respondidas = set(k for k,v in req.respuestas.items() if v is not None)
    excluidas = set(req.excluidas or [])
    candidatos = [c for c in df.columns if c not in respondidas | excluidas]
    # Filtrar columnas que no sean 0/1
    # (asumimos binario si valores ⊆ {0,1})
    binarios = []
    for c in candidatos:
        try:
            vs = set(int(x) for x in pd.Series(df[c].dropna()).unique().tolist())
            if vs.issubset({0,1}) and c not in ("personaje","nombre"):
                binarios.append(c)
        except Exception:
            pass

    if not binarios:
        return RspSiguiente(atributo=None, texto=None, info_gain=None)

    # 3) Evaluar IG para cada candidato
    best_attr, best_ig = None, -1.0
    for a in binarios:
        try:
            # prob. marginal de respuesta=1 (aprox por mapeo personaje->atributo)
            p1 = estimar_p_attr1(post, df, a)
            p0 = 1.0 - p1

            # posterior si respondiera 1 y 0
            post1, _ = posterior_personaje(mezclar_con_evidencia(req.respuestas, a, 1))
            post0, _ = posterior_personaje(mezclar_con_evidencia(req.respuestas, a, 0))

            H1 = entropy(post1)
            H0 = entropy(post0)

            ig = prior_H - (p1 * H1 + p0 * H0)
            if ig > best_ig:
                best_ig = ig
                best_attr = a
        except Exception as e:
            print(f"⚠ IG error {a}: {e}")

    if best_attr is None:
        return RspSiguiente(atributo=None, texto=None, info_gain=None)

    return RspSiguiente(
        atributo=best_attr,
        texto=texto_pregunta(best_attr) or f"¿{best_attr.replace('_',' ')}?",
        info_gain=round(best_ig, 6)
    )
