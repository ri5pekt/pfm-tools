<template>
    <div class="dashboard-container">
        <div class="dashboard-background">
            <div class="dashboard-background-gradient"></div>
            <div class="dashboard-background-pattern"></div>
        </div>
        <div class="dashboard-content">
            <div class="dashboard-header">
                <h1 class="dashboard-title">Welcome back!</h1>
                <p class="dashboard-subtitle">
                    Select a service to get started.
                </p>
            </div>

        <div class="dashboard-sections">
            <!-- Sales Tax Service -->
            <Card class="section-card" @click="$router.push({ name: 'sales-tax-processor' })">
                <template #content>
                    <div class="section-card-content">
                        <div class="section-icon-wrapper">
                            <i class="pi pi-file-export section-icon"></i>
                        </div>
                        <h2 class="section-card-title">Sales Tax</h2>
                        <p class="section-card-description">
                            Process sales tax data from CSV files with integration to WooCommerce, Braintree, and AfterShip.
                        </p>
                        <div class="section-card-footer">
                            <span class="section-card-link">Open Service</span>
                            <i class="pi pi-arrow-right"></i>
                        </div>
                    </div>
                </template>
            </Card>

            <!-- Order Comparison Service -->
            <Card class="section-card" @click="$router.push({ name: 'order-comparison' })">
                <template #content>
                    <div class="section-card-content">
                        <div class="section-icon-wrapper">
                            <i class="pi pi-sync section-icon"></i>
                        </div>
                        <h2 class="section-card-title">Order Comparison</h2>
                        <p class="section-card-description">
                            Compare Complyt CSV data with WooCommerce orders and refunds, generating detailed PDF reports.
                        </p>
                        <div class="section-card-footer">
                            <span class="section-card-link">Open Service</span>
                            <i class="pi pi-arrow-right"></i>
                        </div>
                    </div>
                </template>
            </Card>

            <!-- Ulta Marketplace Service -->
            <Card class="section-card" @click="$router.push({ name: 'ulta-marketplace' })">
                <template #content>
                    <div class="section-card-content">
                        <div class="section-icon-wrapper ulta-logo-wrapper">
                            <img src="@/assets/images/logo-ulta.svg" alt="Ulta" class="ulta-logo" />
                        </div>
                        <h2 class="section-card-title">Ulta Marketplace</h2>
                        <p class="section-card-description">
                            Manage and process Ulta marketplace orders and data.
                        </p>
                        <div class="section-card-footer">
                            <span class="section-card-link">Open Service</span>
                            <i class="pi pi-arrow-right"></i>
                        </div>
                    </div>
                </template>
            </Card>
        </div>
        </div>
    </div>
</template>

<script setup>
import Card from "primevue/card";
import Button from "primevue/button";
</script>

<style scoped>
.dashboard-container {
    min-height: 100vh;
    position: relative;
    padding: 2rem;
    overflow: hidden;
}

.dashboard-background {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 0;
}

.dashboard-background-gradient {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
    opacity: 0.9;
}

.dashboard-background-pattern {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-image: radial-gradient(circle at 20% 50%, rgba(255, 255, 255, 0.1) 0%, transparent 50%),
        radial-gradient(circle at 80% 80%, rgba(255, 255, 255, 0.1) 0%, transparent 50%),
        radial-gradient(circle at 40% 20%, rgba(255, 255, 255, 0.05) 0%, transparent 50%);
    animation: float 20s ease-in-out infinite;
}

@keyframes float {
    0%,
    100% {
        transform: translateY(0px);
    }
    50% {
        transform: translateY(-20px);
    }
}

.dashboard-content {
    position: relative;
    z-index: 1;
    max-width: 1200px;
    margin: 0 auto;
}

.dashboard-header {
    margin-bottom: 3rem;
    text-align: center;
}

.dashboard-title {
    font-size: 2.5rem;
    font-weight: 700;
    margin: 0 0 0.5rem;
    color: white;
    letter-spacing: -0.5px;
    text-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
}

.dashboard-subtitle {
    font-size: 1.1rem;
    color: rgba(255, 255, 255, 0.9);
    margin: 0;
    text-shadow: 0 1px 5px rgba(0, 0, 0, 0.1);
}

.dashboard-sections {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 2rem;
    max-width: 1200px;
    margin: 0 auto;
}

.section-card {
    border-radius: 16px;
    border: 1px solid var(--surface-border);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    transition: transform 0.2s, box-shadow 0.2s;
    cursor: pointer;
    backdrop-filter: blur(10px);
    background: rgba(255, 255, 255, 0.95);
    overflow: hidden;
}

.section-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 24px 70px rgba(0, 0, 0, 0.4);
}

.section-card-content {
    padding: 2.5rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 1.5rem;
}

.section-icon-wrapper {
    width: 80px;
    height: 80px;
    border-radius: 16px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 0.5rem;
}

.section-icon {
    font-size: 2.5rem;
    color: white;
}

.ulta-logo-wrapper {
    background: transparent !important;
    border: none;
}

.ulta-logo {
    max-width: 150px;
    width: auto;
    height: auto;
    object-fit: contain;
}

.section-card-title {
    margin: 0;
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--text-color);
    letter-spacing: -0.3px;
}

.section-card-description {
    margin: 0;
    font-size: 1rem;
    line-height: 1.6;
    color: var(--text-color-secondary);
    max-width: 300px;
}

.section-card-footer {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--primary-color);
    font-weight: 600;
    margin-top: 0.5rem;
}

.section-card-link {
    font-size: 1rem;
}

.section-card-footer i {
    font-size: 0.9rem;
    transition: transform 0.2s;
}

.section-card:hover .section-card-footer i {
    transform: translateX(4px);
}

@media (max-width: 768px) {
    .dashboard-container {
        padding: 1rem;
    }

    .dashboard-title {
        font-size: 2rem;
    }

    .dashboard-sections {
        grid-template-columns: 1fr;
        gap: 1.5rem;
    }

    .section-card-content {
        padding: 2rem 1.5rem;
    }

    .section-icon-wrapper {
        width: 64px;
        height: 64px;
    }

    .section-icon {
        font-size: 2rem;
    }

    .section-card-title {
        font-size: 1.5rem;
    }

    .section-card-description {
        font-size: 0.95rem;
    }
}
</style>
