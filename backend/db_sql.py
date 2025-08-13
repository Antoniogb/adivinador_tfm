from sqlalchemy import create_engine
import pandas as pd

# Cambia estos valores si es necesario
USER = "adivinador"
PASSWORD = "clave_segura123"
HOST = "localhost"
DATABASE = "personajes_marvel"

# Crea el motor de conexión
engine = create_engine(f"mysql+mysqlconnector://{USER}:{PASSWORD}@{HOST}/{DATABASE}")

# Función para cargar todos los personajes en un DataFrame
def cargar_personajes():
    df = pd.read_sql("SELECT * FROM personajes", engine)
    return df
