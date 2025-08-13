<template>
  <div class="bg-white p-6 rounded-xl shadow-lg max-w-xl mx-auto">
    <h2 class="text-xl font-semibold mb-4">Crear nueva pregunta</h2>

    <form @submit.prevent="crearPregunta" class="space-y-4">
      <div>
        <label class="block mb-1 font-medium">Texto de la pregunta</label>
        <input
          v-model="nuevaPregunta.texto"
          type="text"
          class="w-full border border-gray-300 rounded-lg p-2"
          required
        />
      </div>

      <div>
        <label class="block mb-1 font-medium">Campo (atributo)</label>
        <input
          v-model="nuevaPregunta.campo"
          type="text"
          class="w-full border border-gray-300 rounded-lg p-2"
          required
        />
      </div>

      <div>
        <label class="block mb-1 font-medium">Red temática</label>
        <input
          v-model="nuevaPregunta.red"
          type="text"
          class="w-full border border-gray-300 rounded-lg p-2"
        />
      </div>

      <button
        type="submit"
        class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"
      >
        Guardar pregunta
      </button>

      <div v-if="mensaje" class="mt-4 text-green-700 font-medium">
        {{ mensaje }}
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'

const nuevaPregunta = ref({
  texto: '',
  campo: '',
  red: '',
})

const mensaje = ref('')

const crearPregunta = async () => {
  try {
    const res = await axios.post('http://localhost:8000/preguntas', nuevaPregunta.value)
    mensaje.value = '✅ Pregunta guardada con éxito'
    nuevaPregunta.value = { texto: '', campo: '', red: '' }
  } catch (err) {
    mensaje.value = '❌ Error al guardar la pregunta'
    console.error(err)
  }
}
</script>
