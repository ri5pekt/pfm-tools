<!-- frontend/src/App.vue -->
<template>
    <RouterView />
</template>

<script setup>
// nothing fancy here for now – routing handles layout/login split
</script>

<style>
/* Import Inter font from Google Fonts - must be first */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* Global font and base styles */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
        'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11';
}

/* Smooth scrolling */
html {
    scroll-behavior: smooth;
}

/* Better focus styles */
*:focus-visible {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
}

/* Custom scrollbar */
::-webkit-scrollbar {
    width: 10px;
    height: 10px;
}

::-webkit-scrollbar-track {
    background: var(--surface-ground);
}

::-webkit-scrollbar-thumb {
    background: var(--surface-border);
    border-radius: 5px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--text-color-secondary);
}

/* PrimeVue ConfirmDialog styling */
.p-dialog-mask > .p-dialog {
    max-width: 400px;
}

.p-confirm-dialog .p-dialog-content {
    padding: 1.5rem;
}

.p-confirm-dialog .p-dialog-message {
    margin: 0;
    line-height: 1.6;
}

/* Shared service container styles */
.service-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
}

.service-page-header {
    margin-bottom: 2rem;
}

.service-page-title {
    font-size: 2rem;
    font-weight: 700;
    margin: 0 0 0.5rem;
    color: var(--text-color);
    letter-spacing: -0.5px;
}

.service-page-subtitle {
    font-size: 1rem;
    color: var(--text-color-secondary);
    margin: 0;
}
</style>
