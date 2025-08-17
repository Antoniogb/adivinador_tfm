# db_sql.py
from __future__ import annotations
from typing import Dict, List
import pandas as pd

from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, select, text
)
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.engine import Engine

# =========================
#  ⚙️ CONFIGURACIÓN MYSQL
# =========================
USER = "adivinador"
PASSWORD = "clave_segura123"
HOST = "localhost"
DATABASE = "personajes_marvel"

# Conexión
engine: Engine = create_engine(
    f"mysql+mysqlconnector://{USER}:{PASSWORD}@{HOST}/{DATABASE}",
    pool_pre_ping=True,
    future=True,
)

metadata = MetaData()

# =========================
#  🧱 DEFINICIÓN DE CAMPOS
# =========================
# Lista completa de atributos (todos binarios 0/1) usados en tu proyecto
ATR_PODERES = [
    "tiene_superfuerza", "puede_volar", "tiene_regeneracion", "tiene_elasticidad",
    "tiene_telepatia", "tiene_telequinesis", "tiene_invisibilidad", "tiene_velocidad",
    "tiene_vision_laser", "controla_fuego", "controla_hielo", "tiene_magia",
    "controla_electricidad", "puede_cambiar_forma",
]

ATR_AFILI_HEROES = [
    "es_vengador", "es_x_men", "es_cuatro_fantasticos", "es_defensor",
    "es_a_force", "es_campeon", "es_midnight_sons", "es_red_de_guerreros_arana",
]

ATR_AFILI_VILLANOS = [
    "es_hydra", "es_seis_siniestros", "es_aim", "es_hermandad", "es_enemigo_vengadores",
]

ATR_ESPECIE = [
    "especie_humano", "especie_mutante", "especie_dios_asgardiano", "especie_androide",
    "especie_alienigena", "especie_hibrido_kree_humano", "especie_inhumano",
    "especie_dios_jotun", "especie_flora_colossi", "especie_robot", "especie_animal_modificado",
]

ATR_ORIGEN = [
    "origen_tierra", "origen_extraterrestre", "origen_magico", "origen_tecnologico",
]

ATR_ARMAS = [
    "usa_escudo", "usa_martillo", "usa_espadas", "usa_pistolas",
    "usa_espada_de_alma", "usa_armas_tecnologicas",
]

ATR_GENERO_OCUP = [
    "genero_hombre", "genero_mujer", "es_adolescente",
    "es_cientifico", "es_soldado", "es_profesional",
]

ATRIBUTOS_BINARIOS: List[str] = (
    ATR_PODERES
    + ATR_AFILI_HEROES
    + ATR_AFILI_VILLANOS
    + ATR_ESPECIE
    + ATR_ORIGEN
    + ATR_ARMAS
    + ATR_GENERO_OCUP
)

# =========================
#  🗄️ TABLA SQLALCHEMY
# =========================
personajes = Table(
    "personajes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nombre", String(100), nullable=False, unique=True, index=True),
    # Todas las columnas binarias como TINYINT(1)
    *[Column(col, TINYINT(1), nullable=False, server_default="0") for col in ATRIBUTOS_BINARIOS],
)

# Crear tabla si no existe
metadata.create_all(engine)


# =========================
#  🔧 HELPERS INTERNOS
# =========================
def _normalizar_atributos(atributos: Dict[str, int | None]) -> Dict[str, int]:
    """
    Asegura que cada atributo definido en ATRIBUTOS_BINARIOS esté presente (0/1).
    - Valores None o faltantes -> 0
    - Recorta atributos desconocidos
    """
    normalizado: Dict[str, int] = {k: 0 for k in ATRIBUTOS_BINARIOS}
    for k, v in (atributos or {}).items():
        if k in normalizado:
            normalizado[k] = int(v) if v in (0, 1) else 0
    return normalizado


# =========================
#  📦 API DEL MÓDULO
# =========================
def cargar_personajes() -> pd.DataFrame:
    """Devuelve un DataFrame con toda la tabla personajes."""
    return pd.read_sql("SELECT * FROM personajes", engine)


def columnas_personajes() -> List[str]:
    """Devuelve la lista de columnas binarias (para validaciones externas si las necesitas)."""
    return list(ATRIBUTOS_BINARIOS)


def personaje_existe(nombre: str) -> bool:
    """Comprueba si existe un personaje por nombre (case sensitive)."""
    with engine.connect() as conn:
        res = conn.execute(
            text("SELECT 1 FROM personajes WHERE nombre = :n LIMIT 1"),
            {"n": nombre},
        ).first()
        return res is not None


def upsert_personaje(nombre: str, atributos: Dict[str, int | None]) -> dict:
    """
    Inserta o actualiza un personaje:
    - Si no existe -> INSERT con todos los campos normalizados (0/1).
    - Si existe     -> UPDATE de los campos provistos (normalizados), sin tocar los demás (se mantienen).

    Devuelve un dict con {accion: 'insert'|'update', nombre: str}
    """
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre del personaje no puede estar vacío")

    # Normalizamos a 0/1
    norm = _normalizar_atributos(atributos)

    with engine.begin() as conn:
        if not personaje_existe(nombre):
            # INSERT con todos los campos
            cols = ["nombre"] + ATRIBUTOS_BINARIOS
            vals = [nombre] + [norm[c] for c in ATRIBUTOS_BINARIOS]
            placeholders = ", ".join([":" + c for c in cols])
            sql = text(f"INSERT INTO personajes ({', '.join(cols)}) VALUES ({placeholders})")
            params = {c: v for c, v in zip(cols, vals)}
            conn.execute(sql, params)
            return {"accion": "insert", "nombre": nombre}

        # UPDATE solo de los campos que llegan (pero normalizados)
        set_fragments = []
        params = {"n": nombre}
        for col in ATRIBUTOS_BINARIOS:
            if col in atributos:  # solo actualiza los que el usuario respondió en esta sesión
                set_fragments.append(f"{col} = :{col}")
                params[col] = norm[col]

        if set_fragments:
            sql = text(f"UPDATE personajes SET {', '.join(set_fragments)} WHERE nombre = :n")
            conn.execute(sql, params)
            return {"accion": "update", "nombre": nombre}

        # Si no había nada que actualizar (p.ej. atributos vacío)
        return {"accion": "noop", "nombre": nombre}
