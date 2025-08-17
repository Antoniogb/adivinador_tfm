from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from servicios.inferencia_multiple import inferir_personaje_desde_redes
from rutas.partidas import router as partidas_router
from rutas.preguntas import router as preguntas_router
from rutas.inferencia import router as inferencia_router
from rutas.pregunta_siguiente import router as pregunta_siguiente_router
from rutas.fallos import router as fallos_router
from rutas.personajes import router as personajes_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RespuestasUsuario(BaseModel):
    respuestas: dict

app.include_router(partidas_router, tags=["Partidas"])

app.include_router(inferencia_router)
app.include_router(pregunta_siguiente_router)
app.include_router(preguntas_router, prefix="/preguntas", tags=["Preguntas"])
app.include_router(fallos_router)
app.include_router(personajes_router, tags=["personajes"])
@app.post("/inferir")
def inferir(respuestas: RespuestasUsuario):
    try:
        respuestas_filtradas = {k: v for k, v in respuestas.respuestas.items() if v is not None}
        resultado = inferir_personaje_desde_redes(respuestas_filtradas)
        return {"resultado": resultado}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
