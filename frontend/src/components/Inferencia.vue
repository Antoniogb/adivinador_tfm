<!-- src/components/Inferencia.vue -->
<template>
  <div class="p-6 max-w-2xl mx-auto">
    <h1 class="text-2xl font-bold mb-4">🔍 ¿Quién es tu personaje?</h1>

    <!-- PREGUNTAS -->
    <div v-if="preguntaActual && !mostrandoConfirmacion">
      <h2 class="text-lg mb-4">Pregunta {{ totalRespondidas + 1 }}</h2>
      <p class="text-xl font-semibold mb-6">
        {{ preguntaActual.texto || ('¿' + (preguntaActual.atributo || '').replaceAll('_',' ') + '?') }}
      </p>

      <div class="space-x-4">
        <button :disabled="cargando" @click="responder(1)" class="btn">Sí</button>
        <button :disabled="cargando" @click="responder(0)" class="btn">No</button>
        <button :disabled="cargando" @click="responder(null)" class="btn">No sé</button>
      </div>

      <!-- TOP 3 EN TIEMPO REAL -->
      <div v-if="resultado.length > 0" class="mt-6">
        <h3 class="font-semibold mb-2">🔎 Más probables por ahora:</h3>
        <ul>
          <li v-for="(item, i) in resultado.slice(0, 3)" :key="i" class="text-gray-700">
            {{ i + 1 }}. {{ item[0] }} — {{ (item[1] * 100).toFixed(2) }}%
          </li>
        </ul>
      </div>
    </div>

    <!-- CONFIRMACIÓN EN CALIENTE (umbral >= 50%) -->
    <div v-if="mostrandoConfirmacion" class="mt-6">
      <h3 class="text-lg font-semibold">
        🎯 ¿Estás pensando en <span class="text-blue-700">{{ candidato }}</span>?
      </h3>
      <div class="space-x-4 mt-3">
        <button class="btn" @click="confirmarSI">✅ Sí</button>
        <button class="btn" @click="confirmarNO">❌ No</button>
      </div>
      <p class="text-sm text-gray-600 mt-2">Tu respuesta quedará guardada y ayudará a mejorar el sistema.</p>

      <!-- Captura del personaje real si dice NO -->
      <div v-if="pidiendoReal" class="mt-4 p-4 border rounded bg-gray-50">
        <label class="block text-sm mb-2">¿Cuál era tu personaje?</label>
        <input
          v-model="personajeReal"
          type="text"
          placeholder="Escribe el nombre (opcional)"
          class="w-full border rounded px-3 py-2 mb-3"
        />
        <div class="flex gap-3">
          <button class="btn" @click="finalizarFallo">Guardar</button>
          <button class="btn" @click="cancelarFallo">Cancelar</button>
        </div>
        <p class="text-xs text-gray-600 mt-2">Si no quieres decirlo, deja el campo vacío y pulsa Guardar.</p>
      </div>
    </div>

    <!-- FINAL -->
    <div v-if="!preguntaActual && !mostrandoConfirmacion" class="mt-6">
      <div v-if="cargando" class="text-gray-600">Calculando…</div>

      <template v-else-if="resultado[0] && resultado[0][1] >= 0.5 && respuestaConfirmada === null">
        <h2 class="text-xl font-bold mb-4">
          🎯 ¿Estás pensando en <span class="text-blue-700">{{ resultado[0][0] }}</span>?
        </h2>
        <div class="space-x-4 mt-4">
          <button class="btn" @click="confirmarSI">✅ Sí</button>
          <button class="btn" @click="confirmarNO">❌ No</button>
        </div>
      </template>

      <template v-else>
        <h2 class="text-xl font-bold mb-4">🎯 Resultado Final</h2>
        <p v-if="resultado.length === 0" class="mb-2 text-gray-600">No hay suficiente información.</p>
        <p v-else class="text-base mb-2">Los más probables:</p>
        <ul v-if="resultado.length > 0">
          <li v-for="(item, i) in resultado.slice(0, 5)" :key="i" class="mb-1">
            {{ i + 1 }}. {{ item[0] }} — {{ (item[1] * 100).toFixed(2) }}%
          </li>
        </ul>
        <div class="mt-4 space-x-3">
          <button class="btn" @click="guardarPartida(null, nombreTopLocal())">💾 Guardar partida</button>
          <button class="btn" @click="reiniciar()">↩️ Reiniciar</button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'

/** Estado */
const respuestas = ref({})                 // dict atributo -> 0/1/null
const preguntas = ref([])                  // si no usas /pregunta_siguiente
const indice = ref(0)                      // modo secuencial fallback
const preguntaActual = ref(null)           // { atributo, texto }
const resultado = ref([])                  // [[nombre, prob], ...]
const candidato = ref('')                  // nombre top1 cuando umbral >= 0.5
const mostrandoConfirmacion = ref(false)   // panel "¿es X?"
const respuestaConfirmada = ref(null)      // true/false/null
const cargando = ref(false)

// Aprendizaje (opción 2)
const pidiendoReal = ref(false)
const personajeReal = ref('')

const totalRespondidas = computed(() =>
  Object.entries(respuestas.value).filter(([,v]) => v !== undefined).length
)

function top1() {
  return resultado.value?.[0] ?? null
}
function nombreTopLocal() {
  return candidato.value || (top1()?.[0] ?? null)
}

/** Flujo principal */
async function reiniciar() {
  respuestas.value = {}
  preguntas.value = []
  indice.value = 0
  preguntaActual.value = null
  resultado.value = []
  candidato.value = ''
  mostrandoConfirmacion.value = false
  respuestaConfirmada.value = null
  pidiendoReal.value = false
  personajeReal.value = ''

  await solicitarSiguientePregunta() 
  await cargarPreguntasSecuencial() // fallback secuencial
  await inferir()
}

async function solicitarSiguientePregunta() {
  try {
    const excluidas = [] // si quieres forzar exclusiones, añade aquí
    const { data } = await api.post('/pregunta_siguiente', {
      respuestas: respuestas.value,
      excluidas
    })
    if (data?.atributo) {
      preguntaActual.value = { atributo: data.atributo, texto: data.texto }
    } else {
      // No quedan preguntas útiles
      preguntaActual.value = null
    }
  } catch (e) {
    console.error('❌ Error pidiendo pregunta siguiente:', e)
    preguntaActual.value = null
  }
}

async function cargarPreguntasSecuencial() {
  try {
    const { data } = await api.get('/preguntas/activas') // devuelve [{texto, atributo}, ...]
    preguntas.value = data.preguntas || []
    indice.value = 0
    preguntaActual.value = preguntas.value[indice.value] || null
  } catch (e) {
    console.error('❌ Error cargando preguntas:', e)
  }
}

async function responder(valor) {
  if (!preguntaActual.value || cargando.value) return
  const attr = preguntaActual.value.atributo
  respuestas.value = { ...respuestas.value, [attr]: valor }

  // recalcula inferencia
  await inferir()

  // si no se activó confirmación, avanzamos (modo secuencial)
  if (!mostrandoConfirmacion.value) {
    indice.value++
    preguntaActual.value = preguntas.value[indice.value] || null
  }
}

async function inferir() {
  try {
    cargando.value = true
    const { data } = await api.post('/inferir', { respuestas: respuestas.value })
    // { resultado: [[nombre, prob],...], umbral?: bool, candidato?: string }
    resultado.value = data.resultado || []

    if (data.umbral === true) {
      candidato.value = data.candidato || (resultado.value[0]?.[0] ?? '')
      mostrandoConfirmacion.value = true
    } else {
      mostrandoConfirmacion.value = false
      candidato.value = ''
    }
  } catch (e) {
    console.error('❌ Error en inferencia:', e)
  } finally {
    cargando.value = false
  }
}

/** Confirmaciones */
function confirmarSI() {
  terminarYGuardar(true)
}
function confirmarNO() {
  // Pedimos personaje real antes de guardar
  pidiendoReal.value = true
}
function terminarYGuardar(acertado) {
  respuestaConfirmada.value = acertado
  const propuesto = nombreTopLocal()
  // termina visualmente
  preguntaActual.value = null
  mostrandoConfirmacion.value = false
  // guarda
  guardarPartida(acertado, propuesto)
}

/** Aprendizaje – flujo de fallo */
function finalizarFallo() {
  const propuesto = nombreTopLocal()
  const real = (personajeReal.value || '').trim() || null
  // cerrar modal y terminar
  pidiendoReal.value = false
  personajeReal.value = ''
  respuestaConfirmada.value = false
  preguntaActual.value = null
  mostrandoConfirmacion.value = false
  guardarPartida(false, propuesto, real)
}
function cancelarFallo() {
  pidiendoReal.value = false
  personajeReal.value = ''
}

/** Persistencia */
async function guardarPartida(acertado = null, propuesto = null, personaje_real = null) {
  try {
    await api.post('/guardar_partida', {
      respuestas: respuestas.value,
      resultado: resultado.value,
      acertado,
      propuesto,
      personaje_real,
    })
    console.log('✅ Partida guardada correctamente')
  } catch (e) {
    console.error('❌ Error al guardar partida:', e)
  }
}

/** Inicio */
onMounted(async () => {
  await reiniciar()
})
</script>

<style scoped>
.btn { @apply px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700; }
.btn:disabled { @apply opacity-50 cursor-not-allowed; }
</style>
