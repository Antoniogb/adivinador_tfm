import json
import pandas as pd
import numpy as np
from pgmpy.models import DiscreteBayesianNetwork
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination
from sqlalchemy import create_engine

def cargar_red(config_path, df):
    with open(config_path) as f:
        config = json.load(f)

    atributos = [a for a in config["atributos"] if a in df.columns]
    df = df.dropna(subset=["personaje"]).copy()
    df[atributos] = df[atributos].fillna(0).astype(int)

    personajes = df["personaje"].unique().tolist()
    df["personaje"] = df["personaje"].map({p: i for i, p in enumerate(personajes)})

    modelo = DiscreteBayesianNetwork([(a, "personaje") for a in atributos])
    cpds = []

    for a in atributos:
        p = df[a].mean()
        cpds.append(TabularCPD(variable=a, variable_card=2, values=[[1 - p], [p]]))

    group = df.groupby(atributos + ["personaje"]).size().unstack(fill_value=0)
    index = pd.MultiIndex.from_product([sorted(df[a].unique()) for a in atributos], names=atributos)
    group = group.reindex(index, fill_value=0)
    matriz = group.T.values.astype(float)

    for i in range(matriz.shape[1]):
        total = matriz[:, i].sum()
        matriz[:, i] = matriz[:, i] / total if total > 0 else 1.0 / len(personajes)

    cpd_personaje = TabularCPD(
        variable="personaje",
        variable_card=len(personajes),
        values=matriz.tolist(),
        evidence=atributos,
        evidence_card=[len(df[a].unique()) for a in atributos]
    )
    cpds.append(cpd_personaje)

    modelo.add_cpds(*cpds)
    assert modelo.check_model()

    return VariableElimination(modelo), personajes

def combinar_resultados(resultados):
    combinada = {}
    for resultado in resultados:
        for k, v in resultado.items():
            combinada[k] = combinada.get(k, 1) * v
    total = sum(combinada.values())
    return {k: v / total for k, v in combinada.items()} if total else {k: 1/len(combinada) for k in combinada}

def inferir_personaje_desde_redes(observaciones: dict):
    print("⚡ INFERENCIA ACTIVADA:", observaciones)
    engine = create_engine("mysql+mysqlconnector://fastapi:frambuesa22@localhost/personajes_marvel")
    df = pd.read_sql("SELECT * FROM personajes", engine)
    df["personaje"] = df["nombre"]
    if "id" in df.columns:
        df = df.drop(columns=["id"])
    redes = ["poderes", "afiliaciones_heroes", "afiliaciones_villanos", "especie", "origen", "armas", "genero_ocupacion"]
    resultados = []

    for red in redes:
        try:
            infer, personajes = cargar_red(f"./adivinador_backend/bayes_tematica/config_{red}.json", df)
            evidencia_valida = {k: v for k, v in observaciones.items() if k in infer.variables}
            if evidencia_valida:
                resultado = infer.query(["personaje"], evidence=evidencia_valida)
                resultados.append({personajes[i]: float(prob) for i, prob in enumerate(resultado.values)})
            else:
                resultados.append({p: 1/len(personajes) for p in personajes})
        except Exception as e:
            print(f"❌ Error en red {red}: {e}")

    final = combinar_resultados(resultados)
    ordenado = sorted(final.items(), key=lambda x: x[1], reverse=True)
    print("🔍 TOP 3:", ordenado[:3])
    return ordenado[:5]
