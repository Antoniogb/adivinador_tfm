from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import Dict, Optional, Any
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError

from db_sql import engine  # usa el engine que ya tienes

router = APIRouter()

# ===== Pydantic =====
class ExisteReq(BaseModel):
    nombre: str

class UpsertPersonajeReq(BaseModel):
    personaje_real: str
    respuestas: Dict[str, Optional[int]]        # lo que contestó el usuario (puede traer None)
    atributos: Dict[str, Optional[int]]         # atributos (0/1/None). None -> 0
    propuesto: Optional[str] = None

    @field_validator("respuestas", "atributos")
    @classmethod
    def valida_binarios(cls, v: Dict[str, Any]) -> Dict[str, int]:
        # Acepta 0/1/None/True/False y los normaliza a 0/1
        norm: Dict[str, int] = {}
        for k, val in v.items():
            if val in (None, "null", ""):
                norm[k] = 0
            elif isinstance(val, bool):
                norm[k] = 1 if val else 0
            elif isinstance(val, int):
                # fuerza a 0/1
                norm[k] = 1 if val != 0 else 0
            elif isinstance(val, str):
                s = val.strip().lower()
                if s in ("1", "true", "sí", "si"):
                    norm[k] = 1
                else:
                    norm[k] = 0
            else:
                norm[k] = 0
        return norm


# ===== Utilidades internas =====
def _tabla_personajes_columnas() -> set[str]:
    """Lee las columnas reales de la tabla para filtrar el dict antes de insertar."""
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("personajes")}
    return cols

def _existe_personaje(nombre: str) -> bool:
    with engine.connect() as conn:
        r = conn.execute(text("SELECT COUNT(*) FROM personajes WHERE nombre = :n"), {"n": nombre}).scalar()
        return (r or 0) > 0


# ===== Endpoints =====

@router.post("/personajes/existe")
def personajes_existe(body: ExisteReq):
    try:
        return {"existe": _existe_personaje(body.nombre)}
    except SQLAlchemyError as e:
        # Mensaje claro para el frontend
        raise HTTPException(status_code=500, detail=f"Error comprobando existencia: {str(e)}")


@router.post("/fallo/upsert_personaje")
def upsert_personaje(req: UpsertPersonajeReq):
    """
    Inserta un personaje NUEVO si no existe. Si ya existe, no lo toca y solo informa.
    Campos binarios: cualquier None/True/False/strings -> normalizados a 0/1.
    Solo inserta columnas que existan realmente en la tabla `personajes`.
    """
    nombre = req.personaje_real.strip()
    if not nombre:
        raise HTTPException(status_code=422, detail="personaje_real vacío")

    # 1) si ya existe, no insertamos y devolvemos estado
    try:
        if _existe_personaje(nombre):
            return {
                "insertado": False,
                "motivo": "ya_existe",
                "nombre": nombre
            }
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Error comprobando existencia: {str(e)}")

    # 2) Construir diccionario a insertar
    try:
        columnas = _tabla_personajes_columnas()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"No pude leer columnas de 'personajes': {str(e)}")

    # Base: nombre
    row: Dict[str, Any] = {"nombre": nombre}

    # Unir atributos y (si te interesa) respuestas. Normalmente basta con 'atributos'.
    combinados = {**req.atributos}  # puedes mezclar también req.respuestas si quieres aprovechar huecos

    # Filtra por columnas reales
    for k, v in combinados.items():
        if k in columnas:
            # asegurar int 0/1
            row[k] = 1 if v else 0

    # Asegura que todas las columnas binarias que tengas en la tabla
    # existan en el row (si quieres cubrir huecos con 0 automáticamente):
    for col in columnas:
        if col == "id" or col == "nombre":
            continue
        if col not in row:
            row[col] = 0  # por defecto 0

    # 3) Insert
    # Construir SQL dinámico seguro
    cols_sorted = sorted(row.keys())
    placeholders = ", ".join([f":{c}" for c in cols_sorted])
    cols_sql = ", ".join(cols_sorted)
    sql = f"INSERT INTO personajes ({cols_sql}) VALUES ({placeholders})"

    try:
        with engine.begin() as conn:
            conn.execute(text(sql), row)
        return {
            "insertado": True,
            "nombre": nombre,
            "columnas_set": [c for c in cols_sorted if c not in ("id",)],
        }
    except SQLAlchemyError as e:
        # Mensaje claro para ver exactamente qué falló
        raise HTTPException(status_code=500, detail=f"Fallo insertando personaje: {str(e)}")