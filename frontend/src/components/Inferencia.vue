<template>
  <div class="p-6 max-w-2xl mx-auto">
    <h1 class="text-2xl font-bold mb-4">🔍 ¿Quién es tu personaje?</h1>

    <!-- PREGUNTAS -->
    <div v-if="preguntaActual">
      <h2 class="text-lg mb-4">Pregunta {{ indice + 1 }} de {{ preguntas.length }}</h2>
      <p class="text-xl font-semibold mb-6">{{ preguntaActual.texto }}</p>

      <div class="space-x-4">
        <button :disabled="mostrandoConfirmacion" @click="responder(1)" class="btn">Sí</button>
        <button :disabled="mostrandoConfirmacion" @click="responder(0)" class="btn">No</button>
        <button :disabled="mostrandoConfirmacion" @click="responder(null)" class="btn">No sé</button>
      </div>

      <!-- Confirmación en caliente cuando top1 >= 50% -->
      <div v-if="mostrandoConfirmacion" class="mt-6">
        <h3 class="text-lg font-semibold">
          🎯 ¿Estás pensando en <span class="text-blue-700">{{ candidato }}</span>?
        </h3>
        <div class="space-x-4 mt-3">
          <button class="btn" @click="confirmarSI">✅ Sí</button>
          <button class="btn" @click="confirmarNO">❌ No</button>
        </div>
        <p class="text-sm text-gray-600 mt-2">Si eliges “No”, terminaremos y guardaremos tu partida.</p>
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

    <!-- FINAL -->
    <div v-else class="mt-6">
      <div v-if="cargandoInferencia" class="text-gray-600">Calculando…</div>

      <!-- Si no se confirmó en caliente, pregunta al final si top1 >= 50% -->
      <template v-else-if="resultado[0] && resultado[0][1] >= 0.5 && respuestaConfirmada === null">
        <h2 class="text-xl font-bold mb-4">
          🎯 ¿Estás pensando en <span class="text-blue-700">{{ resultado[0][0] }}</span>?
        </h2>
        <div class="space-x-4 mt-4">
          <button class="btn" @click="confirmarSI">✅ Sí</button>
          <button class="btn" @click="confirmarNO">❌ No</button>
        </div>
      </template>

      <!-- Tras confirmar -->
      <template v-else-if="respuestaConfirmada !== null">
        <h2 class="text-xl font-bold mb-4">
          {{ respuestaConfirmada ? '🎉 ¡Genial, lo adivinamos!' : '😅 Vaya, parece que nos equivocamos...' }}
        </h2>
        <p v-if="!respuestaConfirmada" class="mb-2">Otros candidatos:</p>
        <ul v-if="!respuestaConfirmada">
          <li v-for="(item, i) in resultado.slice(1, 5)" :key="i">
            {{ i + 2 }}. {{ item[0] }} — {{ (item[1] * 100).toFixed(2) }}%
          </li>
        </ul>
        <!-- Sólo muestra el botón si aún no se guardó -->
        <button v-if="!yaGuardado" class="btn mt-4" @click="guardarPartida()">💾 Guardar partida</button>
      </template>

      <!-- Si no hay >= 50% -->
      <template v-else>
        <h2 class="text-xl font-bold mb-4">🎯 Resultado Final</h2>
        <p class="text-base mb-2">No hay certeza suficiente. Los más probables:</p>
        <ul>
          <li v-for="(item, i) in resultado.slice(0, 5)" :key="i" class="mb-1">
            {{ i + 1 }}. {{ item[0] }} — {{ (item[1] * 100).toFixed(2) }}%
          </li>
        </ul>
        <!-- Aquí permite guardar manualmente (acertado quedará null) -->
        <button v-if="!yaGuardado" class="btn mt-4" @click="guardarPartida()">💾 Guardar partida</button>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import api from '../api'

const preguntas = ref([])
const indice = ref(0)
const respuestas = ref({})
const resultado = ref([])
const cargandoInferencia = ref(false)

const respuestaConfirmada = ref(null)     // true/false al confirmar
const mostrandoConfirmacion = ref(false)  // bloquea botones y muestra confirmación
const candidato = ref('')                 // nombre top1 cuando ≥ 50%
const yaGuardado = ref(false)             // evita doble guardado

const preguntaActual = computed(() => preguntas.value[indice.value] ?? null)

function nombreTopLocal () {
  // usa 'candidato' si está en confirmación; si no, el top1 de 'resultado'
  return candidato.value || (resultado.value?.[0]?.[0] ?? null)
}

function terminarYGuardar(acertado) {
  respuestaConfirmada.value = acertado
  const propuesto = nombreTopLocal()
  indice.value = preguntas.value.length   // terminar partida
  mostrandoConfirmacion.value = false
  if (!yaGuardado.value) {
    guardarPartida(acertado, propuesto)  // guarda con estado y propuesto
  }
}

function confirmarSI() { terminarYGuardar(true) }
function confirmarNO() { terminarYGuardar(false) }

function shuffleArray(arr) {
  return arr
    .map(value => ({ value, sort: Math.random() }))
    .sort((a, b) => a.sort - b.sort)
    .map(({ value }) => value)
}

async function cargarPreguntas() {
  try {
    const { data } = await api.get('/preguntas/activas')
    preguntas.value = shuffleArray(data.preguntas) // 🔹 ahora baraja
    indice.value = 0
    respuestas.value = {}
    resultado.value = []
    respuestaConfirmada.value = null
    mostrandoConfirmacion.value = false
    candidato.value = ''
  } catch (e) {
    console.error('❌ Error cargando preguntas:', e)
  }
}

async function responder(valor) {
  if (!preguntaActual.value || mostrandoConfirmacion.value) return
  const clave = preguntaActual.value.atributo
  respuestas.value[clave] = valor

  const esUltima = indice.value + 1 >= preguntas.value.length
  if (esUltima) {
    await inferir()
    indice.value++ // dispara la vista final
    return
  }

  indice.value++
  await inferir() // top 3 en vivo + posible confirmación
}

async function inferir() {
  try {
    cargandoInferencia.value = true
    const { data } = await api.post('/inferir', { respuestas: respuestas.value })
    // data.resultado = [[nombre, prob], ...], data.umbral = bool, data.candidato = str
    resultado.value = data.resultado || []

    if (data.umbral === true && preguntaActual.value && respuestaConfirmada.value === null) {
      candidato.value = data.candidato || (resultado.value[0]?.[0] ?? '')
      mostrandoConfirmacion.value = true
    }
  } catch (e) {
    console.error('❌ Error en inferencia:', e)
  } finally {
    cargandoInferencia.value = false
  }
}

async function guardarPartida(acertado = null, propuesto = null) {
  try {
    // si no llegan params, toma del estado actual (evita nulls innecesarios)
    const acertadoFinal = (acertado !== null) ? acertado : respuestaConfirmada.value
    const propuestoFinal = propuesto || nombreTopLocal()

    await api.post('/guardar_partida', {
      respuestas: respuestas.value,
      resultado: resultado.value,
      acertado: acertadoFinal ?? null,
      propuesto: propuestoFinal ?? null
    })
    yaGuardado.value = true
    console.log('✅ Partida guardada correctamente')
  } catch (e) {
    console.error('❌ Error al guardar partida:', e)
  }
}

onMounted(cargarPreguntas)
</script>

<style scoped>
.btn {
  @apply px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700;
}
.btn:disabled { @apply opacity-50 cursor-not-allowed; }
</style>
