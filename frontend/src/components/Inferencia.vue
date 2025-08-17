<template>
  <div class="p-6 max-w-3xl mx-auto">
    <h1 class="text-2xl font-bold mb-4">🔍 ¿Quién es tu personaje?</h1>

    <!-- 1) Confirmación en caliente -->
    <section v-if="estado === 'confirmacion'" class="space-y-4">
      <h3 class="text-xl font-semibold">
        🎯 ¿Estás pensando en <span class="text-blue-700">{{ candidato }}</span>?
      </h3>
      <div class="flex gap-3">
        <button class="btn" @click="confirmarSI" :disabled="bloqueado">✅ Sí</button>
        <button class="btn" @click="confirmarNO" :disabled="bloqueado">❌ No</button>
      </div>
      <p class="text-sm text-gray-600">
        Si eliges “No”, podrás <strong>seguir con las preguntas</strong> descartando ese candidato
        o <strong>decirme quién era</strong>. Si no está en BD, completaremos las preguntas que falten para añadirlo.
      </p>

      <div v-if="top3.length" class="mt-6">
        <h3 class="font-semibold mb-2">🔎 Más probables por ahora:</h3>
        <ul>
          <li v-for="(item, i) in top3" :key="i" class="text-gray-700">
            {{ i + 1 }}. {{ item[0] }} — {{ (item[1] * 100).toFixed(2) }}%
          </li>
        </ul>
      </div>
    </section>

    <!-- 2) Menú tras fallo -->
    <section v-else-if="estado === 'menu_fallo'" class="space-y-4">
      <h3 class="text-lg font-semibold">😅 No acerté. ¿Qué prefieres?</h3>
      <div class="flex flex-wrap gap-3">
        <button class="btn" @click="seguirPreguntando" :disabled="bloqueado">🧭 Seguir con preguntas</button>
        <button class="btn" @click="solicitarNombre" :disabled="bloqueado">✍️ Decir quién era</button>
      </div>

      <div v-if="top3.length" class="mt-6">
        <h3 class="font-semibold mb-2">🔎 Más probables por ahora:</h3>
        <ul>
          <li v-for="(item, i) in top3" :key="i" class="text-gray-700">
            {{ i + 1 }}. {{ item[0] }} — {{ (item[1] * 100).toFixed(2) }}%
          </li>
        </ul>
      </div>
    </section>

    <!-- 3) Pedir nombre -->
    <section v-else-if="estado === 'pedir_nombre'" class="space-y-4">
      <h3 class="text-lg font-semibold">❓ Entonces… ¿quién era el personaje?</h3>
      <div class="flex items-center gap-3">
        <input
          v-model="nombrePersonaje"
          type="text"
          placeholder="Escribe el nombre (ej. Venom)"
          class="border rounded px-3 py-2 w-full"
          @keyup.enter="comprobarPersonaje"
        />
        <button class="btn" @click="comprobarPersonaje" :disabled="!nombrePersonaje.trim() || loading">
          {{ loading ? 'Comprobando…' : 'Continuar' }}
        </button>
      </div>
      <p v-if="existePersonaje === true" class="text-green-700 text-sm">
        ✅ Ya existe en la BD. Guardaremos esta partida como fallida.
      </p>
      <p v-else-if="existePersonaje === false" class="text-amber-700 text-sm">
        🧩 No está en la BD. Vamos a completar las preguntas que falten para añadirlo bien.
      </p>

      <div v-if="top3.length" class="mt-6">
        <h3 class="font-semibold mb-2">🔎 Más probables por ahora:</h3>
        <ul>
          <li v-for="(item, i) in top3" :key="i" class="text-gray-700">
            {{ i + 1 }}. {{ item[0] }} — {{ (item[1] * 100).toFixed(2) }}%
          </li>
        </ul>
      </div>
    </section>

    <!-- 4) Completar faltantes -->
    <section v-else-if="estado === 'completar_faltantes' && preguntaActual" class="space-y-4">
      <div class="rounded border p-4 bg-white shadow-sm">
        <h3 class="text-lg font-semibold mb-1">
          Añadiendo <span class="text-blue-700">{{ nombrePersonaje }}</span> — preguntas faltantes
        </h3>
        <p class="text-sm text-gray-600 mb-4">
          {{ faltanteIndex + 1 }} / {{ totalFaltantes }} restantes
        </p>

        <p class="text-xl font-semibold mb-6">{{ preguntaActual.texto }}</p>
        <div class="space-x-3">
          <button class="btn" @click="responder(1)" :disabled="bloqueado">Sí</button>
          <button class="btn" @click="responder(0)" :disabled="bloqueado">No</button>
          <button class="btn" @click="responder(null)" :disabled="bloqueado">No sé</button>
        </div>
      </div>

      <div v-if="top3.length" class="mt-6">
        <h3 class="font-semibold mb-2">🔎 Más probables por ahora:</h3>
        <ul>
          <li v-for="(item, i) in top3" :key="i" class="text-gray-700">
            {{ i + 1 }}. {{ item[0] }} — {{ (item[1] * 100).toFixed(2) }}%
          </li>
        </ul>
      </div>
    </section>

    <!-- 5) Preguntas normales -->
    <section v-else-if="estado === 'preguntando' && preguntaActual" class="space-y-4">
      <div class="rounded border p-4 bg-white shadow-sm">
        <h3 class="text-sm text-gray-600 mb-1">Pregunta {{ respondidas + 1 }} de {{ preguntas.length }}</h3>
        <p class="text-xl font-semibold mb-6">{{ preguntaActual.texto }}</p>
        <div class="space-x-3">
          <button class="btn" @click="responder(1)" :disabled="bloqueado">Sí</button>
          <button class="btn" @click="responder(0)" :disabled="bloqueado">No</button>
          <button class="btn" @click="responder(null)" :disabled="bloqueado">No sé</button>
        </div>
      </div>

      <div v-if="top3.length" class="mt-6">
        <h3 class="font-semibold mb-2">🔎 Más probables por ahora:</h3>
        <ul>
          <li v-for="(item, i) in top3" :key="i" class="text-gray-700">
            {{ i + 1 }}. {{ item[0] }} — {{ (item[1] * 100).toFixed(2) }}%
          </li>
        </ul>
      </div>
    </section>

    <!-- 6) Final -->
    <section v-else-if="estado === 'final'" class="space-y-4">
      <div v-if="cargandoInferencia" class="text-gray-600">Calculando…</div>

      <template v-else>
        <div class="rounded border p-4 bg-white shadow-sm">
          <h2 class="text-xl font-bold mb-4">🎯 Resultado final</h2>

          <template v-if="top1 && top1[1] >= 0.5 && respuestaConfirmada === null">
            <p class="mb-4">
              ¿Estás pensando en <span class="text-blue-700 font-semibold">{{ top1[0] }}</span>?
            </p>
            <div class="space-x-3">
              <button class="btn" @click="confirmarSI" :disabled="bloqueado">✅ Sí</button>
              <button class="btn" @click="confirmarNO" :disabled="bloqueado">❌ No</button>
            </div>
          </template>

          <template v-else>
            <p class="text-base mb-2">No hay certeza suficiente. Los más probables:</p>
            <ul class="list-disc ps-6">
              <li v-for="(item, i) in top5" :key="i" class="mb-1">
                {{ i + 1 }}. {{ item[0] }} — {{ (item[1] * 100).toFixed(2) }}%
              </li>
            </ul>
            <div class="mt-4 flex gap-3">
              <button class="btn" @click="seguirPreguntando" :disabled="bloqueado">🧭 Seguir con preguntas</button>
              <button class="btn" @click="solicitarNombre" :disabled="bloqueado">✍️ Decir quién era</button>
            </div>
          </template>
        </div>
      </template>
    </section>

    <!-- 7) Terminado -->
    <section v-else-if="estado === 'terminado'" class="space-y-3">
      <h2 class="text-xl font-bold">
        {{ respuestaConfirmada ? '🎉 ¡Acierto!' : '✅ Guardado' }}
      </h2>
      <p class="text-gray-700">La partida se ha guardado correctamente.</p>
      <button class="btn" @click="nuevaPartida">🔄 Nueva partida</button>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api' // axios.create({ baseURL: 'http://localhost:8000' })

/* ===== STATE PRINCIPAL ===== */
const preguntas = ref([])
const respuestas = ref({})
const resultado = ref([])
const cargandoInferencia = ref(false)
const loading = ref(false)
const bloqueado = ref(false)

// Flujo / modo
// 'preguntando' | 'confirmacion' | 'menu_fallo' | 'pedir_nombre' | 'completar_faltantes' | 'final' | 'terminado'
const estado = ref('preguntando')

// Confirmaciones y nombre
const respuestaConfirmada = ref(null)
const candidato = ref('')
const nombrePersonaje = ref('')
const existePersonaje = ref(null)

// Aleatorización y exclusiones
const orden = ref([])
const exclusiones = ref(new Set())

/* ===== CONFIG LOCAL ===== */
const UMBRAL = 0.5 // umbral de confirmación

/* ===== COMPUTEDS ===== */
const respondidas = computed(() => Object.keys(respuestas.value).length)

const preguntaActual = computed(() => {
  for (const idx of orden.value) {
    const p = preguntas.value[idx]
    if (!(p.atributo in respuestas.value)) return p
  }
  return null
})

const topFiltrado = computed(() => {
  if (!Array.isArray(resultado.value)) return []
  return resultado.value.filter(([nombre]) => !exclusiones.value.has(nombre))
})
const top1 = computed(() => topFiltrado.value[0] || null)
const top3 = computed(() => topFiltrado.value.slice(0, 3))
const top5 = computed(() => topFiltrado.value.slice(0, 5))

const faltanteIndex = computed(() => {
  let pos = 0
  for (const idx of orden.value) {
    const p = preguntas.value[idx]
    if (!(p.atributo in respuestas.value)) return pos
    pos++
  }
  return pos
})
const totalFaltantes = computed(() => {
  let count = 0
  for (const idx of orden.value) {
    const p = preguntas.value[idx]
    if (!(p.atributo in respuestas.value)) count++
  }
  return count
})

/* ===== HELPERS ===== */
function barajar(n) {
  const arr = Array.from({ length: n }, (_, i) => i)
  for (let i = n - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr
}

function nombreTopLocal() {
  return candidato.value || (top1.value?.[0] ?? null)
}

function probDe(nombre) {
  if (!nombre) return 0
  const found = resultado.value.find(([n]) => n === nombre)
  return found ? found[1] : 0
}

function primerNoExcluido() {
  const item = resultado.value.find(([n]) => !exclusiones.value.has(n))
  return item ? item[0] : null
}

function pasarAFinalSiNoQuedanPreguntas() {
  if (!preguntaActual.value && estado.value === 'preguntando') {
    estado.value = 'final'
  }
}

/* ===== CARGA DE PREGUNTAS ===== */
async function cargarPreguntas() {
  try {
    const { data } = await api.get('/preguntas/activas')
    preguntas.value = data.preguntas || []
    orden.value = barajar(preguntas.value.length)

    // Reset total
    respuestas.value = {}
    resultado.value = []
    cargandoInferencia.value = false
    loading.value = false
    bloqueado.value = false
    estado.value = 'preguntando'
    respuestaConfirmada.value = null
    candidato.value = ''
    nombrePersonaje.value = ''
    existePersonaje.value = null
    exclusiones.value = new Set()
  } catch (e) {
    console.error('❌ Error cargando preguntas:', e)
  }
}

/* ===== INFERENCIA ===== */
async function inferir() {
  try {
    cargandoInferencia.value = true
    const { data } = await api.post('/inferir', {
      respuestas: respuestas.value,
      exclusiones: Array.from(exclusiones.value)   // <── AÑADIDO
    })
    resultado.value = data.resultado || []

    if (
      estado.value === 'preguntando' &&
      data.umbral === true &&
      !exclusiones.value.has(data.candidato || resultado.value?.[0]?.[0]) &&
      respuestaConfirmada.value === null &&
      preguntaActual.value
    ) {
      candidato.value = data.candidato || (resultado.value[0]?.[0] ?? '')
      estado.value = 'confirmacion'
    } else {
      pasarAFinalSiNoQuedanPreguntas()
    }
  } catch (e) {
    console.error('❌ Error en inferencia:', e)
  } finally {
    cargandoInferencia.value = false
  }
}

/* ===== RESPUESTAS ===== */
async function responder(valor) {
  if (!preguntaActual.value || estado.value === 'terminado') return
  respuestas.value[preguntaActual.value.atributo] = valor

  if (estado.value === 'preguntando') {
    await inferir()
  } else if (estado.value === 'completar_faltantes') {
    if (!preguntaActual.value) {
      await insertarPersonajeYGuardar()
    }
  } else {
    pasarAFinalSiNoQuedanPreguntas()
  }
}

async function confirmarSI() {
  respuestaConfirmada.value = true
  bloqueado.value = true
  estado.value = 'terminado'

  await guardarPartida({
    acertado: true,
    propuesto: nombreTopLocal(),
    personaje_real: nombreTopLocal(),
    insertado_nuevo: false
  })

  bloqueado.value = false
}

function confirmarNO() {
  respuestaConfirmada.value = false
  estado.value = 'menu_fallo'
}

/* ===== OPCIONES TRAS FALLO ===== */
function seguirPreguntando() {
  // Descarta el candidato actual y vuelve a preguntar
  const descartar = nombreTopLocal()
  if (descartar) exclusiones.value.add(descartar)

  // 🔑 Clave: volvemos a "estado limpio" para poder volver a preguntar
  respuestaConfirmada.value = null
  candidato.value = ''
  estado.value = 'preguntando'

  // Si no quedan preguntas, pasamos a final; si quedan, re-evaluamos el top
  pasarAFinalSiNoQuedanPreguntas()
  // Opcional: fuerza una inferencia ahora para que dispare la confirmación
  // si el nuevo top1 ya supera el umbral:
  if (estado.value === 'preguntando' && preguntaActual.value) {
    inferir()
  }
}

function solicitarNombre() {
  estado.value = 'pedir_nombre'
  existePersonaje.value = null
}

/* ===== NOMBRE + EXISTENCIA + COMPLETAR FALTANTES ===== */
async function comprobarPersonaje() {
  const nombre = nombrePersonaje.value.trim()
  if (!nombre) return

  try {
    loading.value = true
    const { data } = await api.post('/personajes/existe', { nombre })
    existePersonaje.value = !!data.existe

    if (existePersonaje.value) {
      await guardarPartida({
        acertado: false,
        propuesto: nombreTopLocal(),
        personaje_real: nombre,
        insertado_nuevo: false
      })
      estado.value = 'terminado'
    } else {
      estado.value = 'completar_faltantes'
      // refresco visual del top (sin forzar confirmación)
      await inferir()
      if (!preguntaActual.value) {
        await insertarPersonajeYGuardar()
      }
    }
  } catch (e) {
    console.error('⚠️ /personajes/existe no disponible o falló:', e)
  } finally {
    loading.value = false
  }
}

async function insertarPersonajeYGuardar() {
  const atributosBin = {}
  for (const p of preguntas.value) {
    const v = respuestas.value[p.atributo]
    atributosBin[p.atributo] = v == null ? 0 : v
  }

  let insertado = false
  try {
    const payload = {
      personaje_real: nombrePersonaje.value.trim(),
      respuestas: respuestas.value,
      atributos: atributosBin,
      propuesto: nombreTopLocal() || ''
    }
    const { data } = await api.post('/fallo/upsert_personaje', payload)
    insertado = !!data.insertado
  } catch (e) {
    console.error('❌ Error insertando personaje:', e)
  }

  await guardarPartida({
    acertado: false,
    propuesto: nombreTopLocal(),
    personaje_real: nombrePersonaje.value.trim(),
    insertado_nuevo: insertado
  })

  estado.value = 'terminado'
}

/* ===== GUARDAR PARTIDA ===== */
async function guardarPartida(extra = {}) {
  try {
    await api.post('/guardar_partida', {
      respuestas: respuestas.value,
      resultado: resultado.value,
      ...extra
    })
    console.log('✅ Partida guardada')
  } catch (e) {
    console.error('❌ Error guardando partida:', e)
  }
}

/* ===== INIT ===== */
onMounted(async () => {
  await cargarPreguntas()
})

/* ===== CONTROLES PÚBLICOS ===== */
function nuevaPartida() {
  cargarPreguntas()
}
</script>

<style scoped>
.btn { @apply px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700; }
</style>
