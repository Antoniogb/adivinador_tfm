# rutas/personajes.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Optional
from sqlalchemy import text
from db_sql import engine  # usa el engine que ya tienes (mysql+mysqlconnector://...)

router = APIRouter()

# ---- MODELOS ----
class UpsertPersonaje(BaseModel):
    nombre: str = Field(..., min_length=1)
    atributos: Dict[str, Optional[int]]  # 0/1 o None (lo convertimos a 0)

class PersonajeExiste(BaseModel):
    nombre: str = Field(..., min_length=1)

# ---- HELPERS ----
def columnas_personajes():
    """
    Lee las columnas reales de la tabla para filtrar el dict de atributos.
    Evita columnas auto/ID y mantiene solo 0/1.
    """
    with engine.connect() as conn:
        cols = conn.execute(
            text("""
                SELECT COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'personajes'
            """)
        ).fetchall()
    # a plano
    cols = [c[0] for c in cols]
    # típicas columnas a ignorar si existen
    ignora = {"id", "_id", "created_at", "updated_at"}
    return [c for c in cols if c not in ignora]

# ---- ENDPOINTS ----
@router.post("/personajes/existe")
def personajes_existe(payload: PersonajeExiste):
    nombre = payload.nombre.strip()
    if not nombre:
        return {"existe": False}
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT COUNT(*) FROM personajes WHERE nombre = :n"
        ), {"n": nombre}).scalar_one()
    return {"existe": (r > 0)}

@router.post("/fallo/upsert_personaje")
def fallo_upsert_personaje(body: UpsertPersonaje):
    nombre = body.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="Nombre vacío")

    # Mapear None -> 0 y filtrar solo columnas válidas
    cols_validas = set(columnas_personajes())
    attrs = {k: (0 if v is None else int(v)) for k, v in (body.atributos or {}).items()}
    attrs = {k: v for k, v in attrs.items() if k in cols_validas}

    # Asegurar que existe la columna 'nombre'
    if 'nombre' not in cols_validas:
        raise HTTPException(status_code=500, detail="La tabla 'personajes' no tiene columna 'nombre'")

    # Construir INSERT dinámico (si existe, se actualiza)
    # Requiere que 'nombre' sea UNIQUE o PRIMARY KEY para que ON DUPLICATE KEY funcione como UPSERT
    columnas = ['nombre'] + list(attrs.keys())
    placeholders = [":nombre"] + [f":{k}" for k in attrs.keys()]
    ondup = ", ".join([f"{k}=VALUES({k})" for k in attrs.keys()]) or "nombre=nombre"

    params = {"nombre": nombre, **attrs}
    sql = f"""
        INSERT INTO personajes ({", ".join(columnas)})
        VALUES ({", ".join(placeholders)})
        ON DUPLICATE KEY UPDATE {ondup}
    """

    try:
        with engine.begin() as conn:
            res = conn.execute(text(sql), params)
        # Si res.rowcount > 0 se insertó o actualizó
        return {"ok": True, "insertado": True}
    except Exception as e:
        # Log claro para depurar
        print("❌ upsert_personaje:", e)
        raise HTTPException(status_code=500, detail="No se pudo upsertar el personaje")
