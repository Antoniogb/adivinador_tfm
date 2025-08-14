from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Union, Optional
from db import db
from datetime import datetime

router = APIRouter()

# ==== MODELOS ====
class Partida(BaseModel):
    respuestas: Dict[str, Union[int, None]]
    resultado: List[List[Union[str, float]]]
    acertado: Optional[bool] = None
    propuesto: Optional[str] = None
    personaje_real: Optional[str] = None     
    motivo_fallo: Optional[str] = None        
# ==== ENDPOINTS ====
@router.post("/guardar_partida")
def guardar_partida(partida: Partida):
    doc = partida.dict()
    doc["timestamp"] = datetime.utcnow().isoformat()
    db["partidas"].insert_one(doc)

    # Guardar si fue fallida para mejorar después
    if partida.acertado is False and partida.propuesto:
        print(f"⚠ Partida fallida: propuso {partida.propuesto}, real {partida.personaje_real}")

    return {"mensaje": "✅ Partida guardada correctamente"}
@router.get("/partidas")
def listar_partidas(limit: int = 50):
    cur = db["partidas"].find({}, {"_id": 0}).sort("timestamp", -1).limit(limit)
    return {"partidas": list(cur)}
@router.get("/partidas_fallidas")
def partidas_fallidas():
    return {"partidas": list(db["partidas"].find({"acertado": False}, {"_id": 0}).sort("timestamp", -1))}

@router.get("/sugerir_pregunta")
def sugerir_pregunta():
    # Buscar preguntas que más aparecen como null en fallidas
    pipeline = [
        {"$match": {"acertado": False}},
        {"$project": {"respuestas": 1}},
        {"$unwind": {"path": "$respuestas"}},
        {"$match": {"respuestas": None}},
        {"$group": {"_id": "$respuestas", "frecuencia": {"$sum": 1}}},
        {"$sort": {"frecuencia": -1}},
        {"$limit": 5}
    ]
    sugerencias = list(db["partidas"].aggregate(pipeline))
    return {"sugerencias": sugerencias}

@router.get("/partidas")
def listar_partidas(limit: int = 50):
    cur = db["partidas"].find({}, {"_id": 0}).sort("timestamp", -1).limit(limit)
    return {"partidas": list(cur)}

@router.get("/estadisticas")
def estadisticas():
    col = db["partidas"]

    total = col.count_documents({})
    acertadas = col.count_documents({"acertado": True})
    falladas = col.count_documents({"acertado": False})

    tasa_acierto = (acertadas / total) if total else 0.0

    # Top propuestos
    pipeline_top = [
        {"$match": {"propuesto": {"$ne": None}}},
        {"$group": {"_id": "$propuesto", "veces": {"$sum": 1},
                    "aciertos": {"$sum": {"$cond": [{"$eq": ["$acertado", True]}, 1, 0]}}}},
        {"$project": {"personaje": "$_id", "_id": 0, "veces": 1, "aciertos": 1,
                      "precision": {"$cond": [{"$eq": ["$veces", 0]}, 0, {"$divide": ["$aciertos", "$veces"]}]}}},
        {"$sort": {"veces": -1}},
        {"$limit": 10}
    ]
    top_propuestos = list(col.aggregate(pipeline_top))

    # Últimas partidas (resumen)
    ultimas = list(
        col.find({}, {"_id": 0, "timestamp": 1, "acertado": 1, "propuesto": 1})
           .sort("timestamp", -1)
           .limit(20)
    )

    return {
        "total": total,
        "acertadas": acertadas,
        "falladas": falladas,
        "tasa_acierto": tasa_acierto,
        "top_propuestos": top_propuestos,
        "ultimas": ultimas
    }
