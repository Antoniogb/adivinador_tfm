from fastapi import APIRouter
from db import db

router = APIRouter()

@router.get("/activas")
def obtener_preguntas_activas():
    coleccion = db["preguntas"]
    preguntas = list(coleccion.find({}, {"_id": 0}))
    return {"preguntas": preguntas}
