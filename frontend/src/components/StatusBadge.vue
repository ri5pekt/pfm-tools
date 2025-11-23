<template>
    <Tag
        :value="status"
        :severity="getSeverity(status)"
        :icon="getIcon(status)"
    />
</template>

<script setup>
import Tag from 'primevue/tag'

const props = defineProps({
    status: {
        type: String,
        required: true
    }
})

const getSeverity = (status) => {
    switch (status?.toLowerCase()) {
        case 'done':
        case 'completed':
        case 'success':
            return 'success'
        case 'running':
        case 'processing':
        case 'pending':
            return 'info'
        case 'error':
        case 'failed':
            return 'danger'
        default:
            return 'secondary'
    }
}

const getIcon = (status) => {
    switch (status?.toLowerCase()) {
        case 'done':
        case 'completed':
        case 'success':
            return 'pi pi-check-circle'
        case 'running':
        case 'processing':
            return 'pi pi-spin pi-spinner'
        case 'error':
        case 'failed':
            return 'pi pi-times-circle'
        case 'pending':
            return 'pi pi-clock'
        default:
            return null
    }
}
</script>

<style scoped>
/* Component styles if needed */
</style>

