import { createRouter, createWebHistory } from 'vue-router'
import Home from '../components/PantallaInicio.vue'
import Quiz from '../components/Inferencia.vue'
import CrearPregunta from '../components/CrearPregunta.vue'
import Historial from '../components/HistorialPartidas.vue'

const routes = [
  { path: '/', component: Home },
  { path: '/jugar', component: Quiz },
  { path: '/crear', component: CrearPregunta },
  { path: '/historial', component: Historial }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
