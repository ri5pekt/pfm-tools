<template>
    <div class="tasks-list-container">
        <div class="page-header">
            <Button
                icon="pi pi-arrow-left"
                label="Back to Dashboard"
                text
                @click="$router.push({ name: 'dashboard' })"
                class="back-button"
            />
            <h1 class="page-title">
                <i class="pi pi-clock page-icon"></i>
                Scheduled Tasks
            </h1>
            <p class="page-subtitle">
                Manage automated tasks and workflows
            </p>
        </div>

        <div class="tasks-content">
            <Card class="empty-section">
                <template #content>
                    <div class="empty-content">
                        <i class="pi pi-inbox empty-icon"></i>
                        <p class="empty-message">
                            No scheduled tasks configured yet.
                        </p>
                        <p class="empty-description">
                            <!-- TODO: Add scheduled tasks functionality
                            - Daily stats pull and export to Google Sheets
                            - Replace Zapier workflows with automated tasks
                            - Each task will have:
                              * Report logs page
                              * Manual run button
                              * Schedule configuration
                            -->
                        </p>
                    </div>
                </template>
            </Card>
        </div>
    </div>
</template>

<script setup>
import Card from "primevue/card";
import Button from "primevue/button";
</script>

<style scoped>
.tasks-list-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
}

.page-header {
    margin-bottom: 2.5rem;
}

.back-button {
    margin-bottom: 1rem;
}

.page-title {
    font-size: 2.5rem;
    font-weight: 700;
    margin: 0 0 0.5rem;
    color: var(--text-color);
    letter-spacing: -0.5px;
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.page-icon {
    font-size: 2rem;
    color: var(--primary-color);
}

.page-subtitle {
    font-size: 1.1rem;
    color: var(--text-color-secondary);
    margin: 0;
}

.tasks-content {
    display: flex;
    justify-content: center;
}

.empty-section {
    width: 100%;
    max-width: 600px;
    opacity: 0.7;
    border-style: dashed;
    border-radius: 12px;
}

.empty-content {
    text-align: center;
    padding: 3rem 1.5rem;
    min-height: 200px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1rem;
}

.empty-icon {
    font-size: 3rem;
    color: var(--text-color-secondary);
    opacity: 0.5;
}

.empty-message {
    margin: 0;
    font-size: 1.1rem;
    font-weight: 500;
    color: var(--text-color-secondary);
}

.empty-description {
    margin: 0;
    font-size: 0.9rem;
    color: var(--text-color-secondary);
    opacity: 0.7;
    max-width: 500px;
    line-height: 1.5;
}

@media (max-width: 768px) {
    .tasks-list-container {
        padding: 1rem;
    }

    .page-title {
        font-size: 2rem;
    }

    .empty-content {
        padding: 2rem 1rem;
        min-height: 150px;
    }
}
</style>

