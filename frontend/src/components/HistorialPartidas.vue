<template>
  <div class="p-4">
    <h2 class="text-2xl font-bold mb-4">Historial de Partidas</h2>

    <div v-if="error" class="text-red-500 mb-2">❌ {{ error }}</div>
    <div v-if="loading">⏳ Cargando partidas...</div>

    <table v-if="partidas.length" class="min-w-full border">
      <thead class="bg-gray-100">
        <tr>
          <th class="py-2 px-4 border text-left">Top 1</th>
          <th class="py-2 px-4 border text-left">Top 2</th>
          <th class="py-2 px-4 border text-left">Top 3</th>
          <th class="py-2 px-4 border text-center">¿Adivinado?</th>
          <th class="py-2 px-4 border text-center">Fecha</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(p, idx) in partidas" :key="idx" class="align-top">
          <td class="py-2 px-4 border">
            <span class="font-semibold">{{ p.top[0]?.nombre || '—' }}</span>
            <span v-if="p.top[0]" class="text-gray-600"> — {{ p.top[0].porc }}%</span>
          </td>
          <td class="py-2 px-4 border">
            <span>{{ p.top[1]?.nombre || '—' }}</span>
            <span v-if="p.top[1]" class="text-gray-600"> — {{ p.top[1].porc }}%</span>
          </td>
          <td class="py-2 px-4 border">
            <span>{{ p.top[2]?.nombre || '—' }}</span>
            <span v-if="p.top[2]" class="text-gray-600"> — {{ p.top[2].porc }}%</span>
          </td>
          <td class="py-2 px-4 border text-center">
            <span
              v-if="p.adivinado === true"
              class="text-green-600 font-medium"
              title="Se confirmó que era el personaje propuesto"
            >✅ Sí</span>
            <span
              v-else-if="p.adivinado === false"
              class="text-red-600 font-medium"
              title="Se confirmó que NO era el personaje propuesto"
            >❌ No</span>
            <span v-else class="text-gray-500" title="Sin confirmación">—</span>
          </td>
          <td class="py-2 px-4 border text-center">{{ p.fecha }}</td>
        </tr>
      </tbody>
    </table>

    <div v-else-if="!loading">No hay partidas registradas.</div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import api from '../api' // usa tu axios con baseURL http://localhost:8000

const partidas = ref([])
const loading = ref(false)
const error = ref('')

const toPorc = (prob) => {
  const n = Number(prob)
  if (Number.isFinite(n)) return (n * 100).toFixed(2)
  return null
}

const mapTop3 = (resultado) => {
  if (!Array.isArray(resultado)) return []
  // resultado viene como [[nombre, prob], ...]
  return resultado.slice(0, 3).map((par) => {
    const nombre = Array.isArray(par) ? par[0] : null
    const prob = Array.isArray(par) ? par[1] : null
    const porc = toPorc(prob)
    return (nombre && porc !== null) ? { nombre, porc } : null
  }).filter(Boolean)
}

const cargarPartidas = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get('/partidas?limit=50')
    const docs = res.data?.partidas ?? []
    partidas.value = docs.map((doc) => {
      const top = mapTop3(doc.resultado || [])
      const fecha = formatFecha(doc.timestamp || '')
      // acertado puede ser true/false/null -> lo dejamos tal cual,
      // el template lo pinta como ✅, ❌ o —.
      const adivinado = (doc.acertado === true) ? true : (doc.acertado === false ? false : null)
      return { top, adivinado, fecha }
    })
  } catch (e) {
    console.error('❌ Error al cargar partidas:', e)
    error.value = 'No se pudieron cargar las partidas.'
  } finally {
    loading.value = false
  }
}

const formatFecha = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '—' : d.toLocaleString()
}

onMounted(cargarPartidas)
</script>

<style scoped>
table { border-collapse: collapse; }
</style>
