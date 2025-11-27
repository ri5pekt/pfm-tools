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

html {
    height: 100%;
    overflow-y: auto;
    scroll-behavior: smooth;
}

body {
    height: 100%;
    margin: 0;
    padding: 0;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
        'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11';
}

#app {
    height: 100%;
}

/* Better focus styles */
*:focus-visible {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
}

/* Custom scrollbar - always visible */
::-webkit-scrollbar {
    width: 12px;
    height: 12px;
    -webkit-appearance: none;
}

::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-left: 1px solid #e0e0e0;
}

::-webkit-scrollbar-thumb {
    background: #888;
    border-radius: 6px;
    border: 2px solid #f1f1f1;
}

::-webkit-scrollbar-thumb:hover {
    background: #555;
}

/* Firefox scrollbar */
* {
    scrollbar-width: thin;
    scrollbar-color: #888 #f1f1f1;
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

/* Global card styling with noticeable shadow */
.p-card {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12) !important;
    transition: box-shadow 0.2s ease;
}

.p-card:hover {
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.15) !important;
}
</style>
