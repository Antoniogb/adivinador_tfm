from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Tuple, Optional, Iterable
import json
import pandas as pd
import numpy as np

# ➜ usa tu helper de BD
from db_sql import cargar_personajes

# pgmpy
from pgmpy.models import DiscreteBayesianNetwork
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination

router = APIRouter()


class RespuestasUsuario(BaseModel):
    respuestas: Dict[str, Optional[int]]  # 0/1 o None


def _cargar_red(config_path: str, df: pd.DataFrame) -> Tuple[VariableElimination, List[str]]:
    """
    Crea una red bayesiana Discreta A->personaje para los atributos listados en el JSON.
    Devuelve el inferenciador y el listado de nombres de personajes para indexar los resultados.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    atributos = [a for a in config["atributos"] if a in df.columns]

    # normaliza dataset
    work = df.copy()
    work = work.dropna(subset=["personaje"])
    work[atributos] = work[atributos].fillna(0).astype(int)

    # index de personaje
    personajes = work["personaje"].unique().tolist()
    map_idx = {p: i for i, p in enumerate(personajes)}
    work["personaje"] = work["personaje"].map(map_idx)

    # estructura: todos los atributos apuntan a "personaje"
    model = DiscreteBayesianNetwork([(a, "personaje") for a in atributos])

    # CPDs de atributos como Bernoulli con prior empírico
    cpds = []
    for a in atributos:
        p = float(work[a].mean()) if len(work) else 0.5
        # variable_card=2 ⇒ estados {0,1}
        cpds.append(TabularCPD(variable=a, variable_card=2, values=[[1 - p], [p]]))

    # CPD de personaje condicional a todos los atributos (tabla grande)
    # construimos conteos por combinación de atributos
    if atributos:
        group = work.groupby(atributos + ["personaje"]).size().unstack(fill_value=0)
        index = pd.MultiIndex.from_product(
            [sorted(work[a].unique()) for a in atributos], names=atributos
        )
        group = group.reindex(index, fill_value=0)
        matriz = group.T.values.astype(float)  # shape: [n_personajes, n_configs]

        # normaliza por columna (p(personaje | atributos))
        for i in range(matriz.shape[1]):
            total = matriz[:, i].sum()
            if total > 0:
                matriz[:, i] = matriz[:, i] / total
            else:
                matriz[:, i] = 1.0 / len(personajes)
        evidence_card = [len(work[a].unique()) for a in atributos]
    else:
        # sin atributos en esa red (debería no ocurrir): prior uniforme
        matriz = np.ones((len(personajes), 1), dtype=float)
        matriz /= matriz.sum(axis=0, keepdims=True)
        evidence_card = []

    cpd_personaje = TabularCPD(
        variable="personaje",
        variable_card=len(personajes),
        values=matriz.tolist(),
        evidence=atributos,
        evidence_card=evidence_card,
    )
    cpds.append(cpd_personaje)

    model.add_cpds(*cpds)
    assert model.check_model(), "La red bayesiana no es consistente"

    return VariableElimination(model), personajes


def _combinar_resultados(resultados: List[Dict[str, float]]) -> Dict[str, float]:
    """
    Combina varias distribuciones sobre personajes por producto y renormaliza.
    """
    acumulado: Dict[str, float] = {}
    for dist in resultados:
        for k, v in dist.items():
            acumulado[k] = acumulado.get(k, 1.0) * float(v)

    total = sum(acumulado.values())
    if total <= 0:
        # si algo salió mal, reparte uniforme
        n = max(1, len(acumulado))
        return {k: 1.0 / n for k in acumulado}

    return {k: v / total for k, v in acumulado.items()}


def inferir_personaje_desde_redes(
    observaciones: Dict[str, Optional[int]],
    *,
    umbral: float = 0.5,
    excluir: Optional[Iterable[str]] = None,
) -> Dict:
    """
    ➜ Función *pura* que usa las distintas redes temáticas y devuelve:
       {
         "resultado": [(nombre, prob), ...]  # ordenado desc,
         "umbral": bool,                     # si top1 >= umbral
         "candidato": str | None             # nombre top1 (no excluido)
       }

    - `excluir`: lista/conjunto de nombres a descartar del ranking (p.ej. top rechazados).
    """
    print("⚡ INFERENCIA ACTIVADA:", observaciones)

    # Carga datos desde tu BD
    df = cargar_personajes()
    # tu esquema: columna 'nombre' es el display; mapeamos a 'personaje' para la red
    df = df.copy()
    df["personaje"] = df["nombre"]
    if "id" in df.columns:
        df = df.drop(columns=["id"])

    # Redes temáticas
    redes = [
        "poderes",
        "afiliaciones_heroes",
        "afiliaciones_villanos",
        "especie",
        "origen",
        "armas",
        "genero_ocupacion",
    ]

    resultados: List[Dict[str, float]] = []

    for red in redes:
        try:
            # ⚠️ Ajusta el path a donde tengas tus JSONs
            infer, personajes = _cargar_red(
                f"./adivinador_backend/bayes_tematica/config_{red}.json", df
            )

            # filtra evidencia válida para esta red
            evidencia_valida = {k: v for k, v in observaciones.items() if k in infer.variables and v is not None}

            if evidencia_valida:
                q = infer.query(["personaje"], evidence=evidencia_valida)
                dist = {personajes[i]: float(prob) for i, prob in enumerate(q.values)}
                resultados.append(dist)
            else:
                # sin evidencia para esta red => uniforme
                uniform = 1.0 / len(personajes) if personajes else 1.0
                resultados.append({p: uniform for p in personajes})
        except Exception as e:
            print(f"❌ Error en red {red}: {e}")

    # combina distribuciones
    final = _combinar_resultados(resultados)

    # aplica exclusiones si las hubiera
    excluir_set = set(excluir or [])
    if excluir_set:
        final = {k: v for k, v in final.items() if k not in excluir_set}
        # renormaliza tras excluir
        s = sum(final.values())
        if s > 0:
            final = {k: v / s for k, v in final.items()}

    ordenado: List[Tuple[str, float]] = sorted(final.items(), key=lambda x: x[1], reverse=True)
    print("🔍 TOP 3:", ordenado[:3])

    top1 = ordenado[0] if ordenado else None
    umbral_alcanzado = bool(top1 and top1[1] >= umbral)
    candidato = top1[0] if umbral_alcanzado else None

    return {
        "resultado": ordenado[:5],
        "umbral": umbral_alcanzado,
        "candidato": candidato,
    }


@router.post("/inferir")
def inferir_endpoint(datos: RespuestasUsuario):
    """
    Endpoint HTTP que usa la función pura.
    """
    try:
        payload = inferir_personaje_desde_redes(datos.respuestas)
        return payload
    except Exception as e:
        print("❌ ERROR GENERAL en inferencia:", e)
        raise HTTPException(status_code=500, detail="Error en inferencia múltiple")
