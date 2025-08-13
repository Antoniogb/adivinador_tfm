<template>
  <div class="p-6 max-w-2xl mx-auto">
    <h1 class="text-2xl font-bold mb-4">🔍 ¿Quién es tu personaje?</h1>

    <div v-if="preguntaActual">
      <h2 class="text-lg mb-4">Pregunta {{ indice + 1 }} de {{ preguntas.length }}</h2>
      <p class="text-xl font-semibold mb-6">{{ preguntaActual.texto }}</p>

      <div class="space-x-4">
        <button @click="responder(1)" class="btn">Sí</button>
        <button @click="responder(0)" class="btn">No</button>
        <button @click="responder(null)" class="btn">No sé</button>
      </div>
    </div>

    <div v-else class="mt-6">
      <h2 class="text-xl font-bold mb-4">🎯 ¡Resultado Final!</h2>
      <ul>
        <li v-for="(item, index) in resultado" :key="index" class="mb-1">
          {{ index + 1 }}. {{ item[0] }} — {{ (item[1] * 100).toFixed(2) }}%
        </li>
      </ul>
      <button class="btn mt-4" @click="guardarPartida">💾 Guardar partida</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const preguntas = ref([])
const indice = ref(0)
const respuestas = ref({})
const resultado = ref([])

const preguntaActual = computed(() => preguntas.value[indice.value])

async function cargarPreguntas() {
  try {
    const { data } = await axios.get('http://localhost:8000/preguntas_activas')
    preguntas.value = data.preguntas
    console.log('📋 Preguntas cargadas:', preguntas.value)
  } catch (error) {
    console.error('❌ Error cargando preguntas:', error)
  }
}

async function responder(valor) {
  const clave = preguntaActual.value.clave
  respuestas.value[clave] = valor
  indice.value++

  if (indice.value >= preguntas.value.length) {
    await inferir()
  }
}

async function inferir() {
  try {
    const { data } = await axios.post('http://localhost:8000/inferir', {
      respuestas: respuestas.value
    })
    resultado.value = data.resultado
    console.log('📊 Resultado:', resultado.value)
  } catch (error) {
    console.error('❌ Error en inferencia:', error)
  }
}

async function guardarPartida() {
  try {
    await axios.post('http://localhost:8000/guardar_partida', {
      respuestas: respuestas.value,
      resultado: resultado.value
    })
    alert('✅ Partida guardada correctamente')
  } catch (error) {
    console.error('❌ Error al guardar partida:', error)
  }
}

onMounted(() => {
  cargarPreguntas()
})
</script>

<style scoped>
.btn {
  @apply px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700;
}
</style>
