from fastapi import APIRouter
from db import db
import random

router = APIRouter()

@router.get("/activas")
def listar_preguntas():
    preguntas = list(db["preguntas"].find({}, {"_id": 0}))
    random.shuffle(preguntas)  # 🔹 Mezcla aleatoria
    return {"preguntas": preguntas}