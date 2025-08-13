<template>
  <div class="min-h-screen bg-gray-100 text-gray-800">
    <header class="bg-white shadow p-4 flex gap-4">
      <router-link to="/" class="hover:underline">Inicio</router-link>
      <router-link to="/jugar" class="hover:underline">Jugar</router-link>
      <router-link to="/crear" class="hover:underline">Crear Pregunta</router-link>
      <router-link to="/historial" class="hover:underline">Historial</router-link>
    </header>
    <main class="p-6">
      <router-view />
    </main>
  </div>
</template>

<script setup>
// Nada necesario aquí
</script>
