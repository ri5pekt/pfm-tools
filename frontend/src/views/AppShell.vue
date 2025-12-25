<!-- frontend/src/views/AppShell.vue -->
<template>
    <div class="app-shell">
        <header class="app-header">
            <div class="header-left">
                <div class="logo">
                    <i class="pi pi-cog"></i>
                </div>
                <div class="app-title-wrapper">
                    <span class="app-title">PFM Tools</span>
                    <span class="app-version">v{{ version }}</span>
                </div>
            </div>
            <div class="header-right">
                <div class="user-info" v-if="auth.state.user">
                    <div class="user-avatar">
                        <i class="pi pi-user"></i>
                    </div>
                    <div class="user-details">
                        <span class="user-email">{{ auth.state.user.email }}</span>
                        <span class="user-role" v-if="auth.isAdmin">Administrator</span>
                    </div>
                </div>
                <Button
                    label="Logout"
                    icon="pi pi-sign-out"
                    severity="secondary"
                    size="small"
                    outlined
                    @click="handleLogout"
                />
            </div>
        </header>

        <div class="app-body">
            <aside class="app-sidebar">
                <nav class="sidebar-nav">
                    <RouterLink
                        to="/app/dashboard"
                        class="nav-item"
                        active-class="nav-item-active"
                    >
                        <i class="pi pi-home"></i>
                        <span>Dashboard</span>
                    </RouterLink>
                    <RouterLink
                        to="/app/sales-tax-processor"
                        class="nav-item nav-item-child"
                        active-class="nav-item-active"
                    >
                        <i class="pi pi-file-export"></i>
                        <span>Sales Tax</span>
                    </RouterLink>
                    <RouterLink
                        to="/app/order-comparison"
                        class="nav-item nav-item-child"
                        active-class="nav-item-active"
                    >
                        <i class="pi pi-sync"></i>
                        <span>Order Comparison</span>
                    </RouterLink>
                    <RouterLink
                        to="/app/ulta-marketplace"
                        class="nav-item nav-item-child"
                        active-class="nav-item-active"
                    >
                        <i class="pi pi-shopping-cart"></i>
                        <span>Ulta Marketplace</span>
                    </RouterLink>
                    <RouterLink
                        to="/app/tiktok-marketplace"
                        class="nav-item nav-item-child"
                        active-class="nav-item-active"
                    >
                        <i class="pi pi-video"></i>
                        <span>TikTok Marketplace</span>
                    </RouterLink>
                    <RouterLink
                        to="/app/inventory-data"
                        class="nav-item nav-item-child"
                        active-class="nav-item-active"
                    >
                        <i class="pi pi-box"></i>
                        <span>Inventory Data</span>
                    </RouterLink>
                    <RouterLink
                        to="/app/daily-orders-data"
                        class="nav-item nav-item-child"
                        active-class="nav-item-active"
                    >
                        <i class="pi pi-calendar"></i>
                        <span>Daily Orders Data</span>
                    </RouterLink>
                    <RouterLink
                        to="/app/daily-product-sales"
                        class="nav-item nav-item-child"
                        active-class="nav-item-active"
                    >
                        <i class="pi pi-shopping-cart"></i>
                        <span>Daily Product Sales</span>
                    </RouterLink>
                </nav>
            </aside>

            <main class="app-main">
                <RouterView />
            </main>
        </div>
    </div>
</template>

<script setup>
import { useRouter } from "vue-router";
import { useAuthStore } from "../store/authStore";
import Button from "primevue/button";
import { APP_VERSION } from "../config/version";

const router = useRouter();
const auth = useAuthStore();
const version = APP_VERSION;

function handleLogout() {
    auth.logout();
    router.push({ name: "login" });
}
</script>

<style scoped>
.app-shell {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    background: var(--surface-ground);
}

.app-header {
    background: white;
    border-bottom: 1px solid rgba(0, 0, 0, 0.08);
    padding: 1rem 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
    position: sticky;
    top: 0;
    z-index: 100;
}

.header-left {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.logo {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
}

.logo i {
    font-size: 1.25rem;
}

.app-title-wrapper {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
}

.app-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-color);
    letter-spacing: -0.5px;
    line-height: 1.2;
}

.app-version {
    font-size: 0.7rem;
    font-weight: 500;
    color: var(--text-color-secondary);
    opacity: 0.7;
    letter-spacing: 0.5px;
}

.header-right {
    display: flex;
    align-items: center;
    gap: 1.5rem;
}

.user-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.user-avatar {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: var(--surface-100);
    display: flex;
    align-items: center;
    justify-content: center;
    border: 2px solid var(--surface-border);
}

.user-avatar i {
    color: var(--text-color-secondary);
    font-size: 0.9rem;
}

.user-details {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
}

.user-email {
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text-color);
}

.user-role {
    font-size: 0.75rem;
    color: var(--text-color-secondary);
}

.app-body {
    display: flex;
    flex: 1;
    min-height: 0;
}

.app-sidebar {
    width: 260px;
    background: var(--surface-0);
    border-right: 1px solid var(--surface-border);
    box-shadow: 2px 0 8px rgba(0, 0, 0, 0.08);
    padding: 1.5rem 0;
    overflow-y: auto;
    position: sticky;
    top: 80px;
    height: calc(100vh - 80px);
    align-self: flex-start;
}

.sidebar-nav {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0 1rem;
}

.nav-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.875rem 1rem;
    border-radius: 8px;
    color: var(--text-color-secondary);
    text-decoration: none;
    font-weight: 500;
    transition: all 0.2s;
    border: 1px solid transparent;
}

.nav-item:hover {
    background: var(--surface-hover);
    color: var(--text-color);
}

.nav-item-active {
    background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
    color: var(--primary-color);
    border-color: rgba(102, 126, 234, 0.2);
}

.nav-item i {
    font-size: 1.1rem;
}

.nav-item-child {
    padding-left: 2.5rem;
    font-size: 0.95rem;
    opacity: 0.9;
}

.app-main {
    flex: 1;
    overflow-y: auto;
    background: var(--surface-ground);
}

/* Custom scrollbar for main content - always visible */
.app-main::-webkit-scrollbar {
    width: 12px;
}

.app-main::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-left: 1px solid #e0e0e0;
}

.app-main::-webkit-scrollbar-thumb {
    background: #888;
    border-radius: 6px;
    border: 2px solid #f1f1f1;
}

.app-main::-webkit-scrollbar-thumb:hover {
    background: #555;
}

/* Custom scrollbar for sidebar */
.app-sidebar::-webkit-scrollbar {
    width: 6px;
}

.app-sidebar::-webkit-scrollbar-track {
    background: transparent;
}

.app-sidebar::-webkit-scrollbar-thumb {
    background: var(--surface-border);
    border-radius: 3px;
}

.app-sidebar::-webkit-scrollbar-thumb:hover {
    background: var(--text-color-secondary);
}

@media (max-width: 768px) {
    .app-header {
        padding: 1rem;
    }

    .app-title {
        font-size: 1.25rem;
    }

    .user-details {
        display: none;
    }

    .app-sidebar {
        width: 200px;
    }

    .nav-item span {
        font-size: 0.9rem;
    }
}
</style>
