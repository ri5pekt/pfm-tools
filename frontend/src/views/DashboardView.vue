<template>
    <div class="dashboard-container">
        <div class="dashboard-header">
            <h1 class="dashboard-title">Welcome back!</h1>
            <p class="dashboard-subtitle">
                Here's what's happening with your tools today.
            </p>
        </div>

        <div class="dashboard-actions">
            <Card class="feature-card">
                <template #header>
                    <div class="card-header">
                        <div class="card-icon">
                            <i class="pi pi-file-export"></i>
                        </div>
                        <h3 class="card-title">Sales Tax Processor</h3>
                    </div>
                </template>
                <template #content>
                    <div class="card-content">
                        <p class="card-description">
                            Upload CSV files to process sales tax data. Compare tax calculations
                            from WooCommerce and Braintree, identify discrepancies, and generate
                            detailed reports for reconciliation.
                        </p>
                        <Button
                            label="Open Sales Tax Processor"
                            icon="pi pi-arrow-right"
                            class="card-button"
                            @click="$router.push({ name: 'sales-tax-processor' })"
                        />
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
.dashboard-container {
    max-width: 800px;
    margin: 0 auto;
    padding: 2rem;
}

.dashboard-header {
    margin-bottom: 3rem;
    text-align: center;
}

.dashboard-title {
    font-size: 2.5rem;
    font-weight: 700;
    margin: 0 0 0.5rem;
    color: var(--text-color);
    letter-spacing: -0.5px;
}

.dashboard-subtitle {
    font-size: 1.1rem;
    color: var(--text-color-secondary);
    margin: 0;
}

.dashboard-actions {
    display: flex;
    justify-content: center;
}

.feature-card {
    width: 100%;
    max-width: 600px;
    border-radius: 12px;
    border: 1px solid var(--surface-border);
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
    transition: transform 0.2s, box-shadow 0.2s;
}

.feature-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12);
}

.card-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1.5rem;
    border-bottom: 1px solid var(--surface-border);
    background: linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, rgba(118, 75, 162, 0.05) 100%);
}

.card-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    flex-shrink: 0;
}

.card-icon i {
    font-size: 1.5rem;
}

.card-title {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-color);
    letter-spacing: -0.3px;
}

.card-content {
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
}

.card-description {
    margin: 0;
    font-size: 1rem;
    line-height: 1.6;
    color: var(--text-color-secondary);
}

.card-button {
    width: 100%;
    height: 3rem;
    font-size: 1rem;
    font-weight: 600;
    border-radius: 8px;
}

@media (max-width: 768px) {
    .dashboard-container {
        padding: 1rem;
    }

    .dashboard-title {
        font-size: 2rem;
    }

    .card-header {
        padding: 1.25rem;
    }

    .card-content {
        padding: 1.25rem;
    }

    .card-title {
        font-size: 1.25rem;
    }

    .card-description {
        font-size: 0.95rem;
    }
}
</style>
