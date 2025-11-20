<template>
    <div class="tools-list-container">
        <div class="page-header">
            <Button
                icon="pi pi-arrow-left"
                label="Back to Dashboard"
                text
                @click="$router.push({ name: 'dashboard' })"
                class="back-button"
            />
            <h1 class="page-title">
                <i class="pi pi-wrench page-icon"></i>
                Tools
            </h1>
            <p class="page-subtitle">
                Manage and access your available tools
            </p>
        </div>

        <div class="tools-grid">
            <Card class="tool-card">
                <template #header>
                    <div class="card-header">
                        <div class="card-icon">
                            <i class="pi pi-file-export"></i>
                        </div>
                        <h3 class="card-title">Sales Tax</h3>
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
                            label="Open Sales Tax"
                            icon="pi pi-arrow-right"
                            class="card-button"
                            @click="$router.push({ name: 'sales-tax-processor' })"
                        />
                    </div>
                </template>
            </Card>

            <Card class="tool-card">
                <template #header>
                    <div class="card-header">
                        <div class="card-icon">
                            <i class="pi pi-sync"></i>
                        </div>
                        <h3 class="card-title">Order Comparison</h3>
                    </div>
                </template>
                <template #content>
                    <div class="card-content">
                        <p class="card-description">
                            Compare Complyt invoice reports with WooCommerce orders and refunds.
                            Upload a CSV file, select a date range, and generate a detailed
                            comparison report showing discrepancies.
                        </p>
                        <Button
                            label="Open Order Comparison"
                            icon="pi pi-arrow-right"
                            class="card-button"
                            @click="$router.push({ name: 'order-comparison' })"
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
.tools-list-container {
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

.tools-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
    gap: 1.5rem;
}

.tool-card {
    border-radius: 12px;
    border: 1px solid var(--surface-border);
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
    transition: transform 0.2s, box-shadow 0.2s;
}

.tool-card:hover {
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
    .tools-list-container {
        padding: 1rem;
    }

    .page-title {
        font-size: 2rem;
    }

    .tools-grid {
        grid-template-columns: 1fr;
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

