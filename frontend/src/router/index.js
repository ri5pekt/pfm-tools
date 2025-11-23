// frontend/src/router/index.js
import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../store/authStore";

import LoginView from "../views/LoginView.vue";
import DashboardView from "../views/DashboardView.vue";
import SalesTaxProcessorView from "../views/SalesTaxProcessorView.vue";
import OrderComparisonView from "../views/OrderComparisonView.vue";
import UltaMarketplaceView from "../views/UltaMarketplaceView.vue";

const routes = [
    {
        path: "/login",
        name: "login",
        component: LoginView,
    },
    {
        path: "/app",
        component: () => import("../views/AppShell.vue"), // small layout shell
        children: [
            {
                path: "dashboard",
                name: "dashboard",
                component: DashboardView,
            },
            {
                path: "sales-tax-processor",
                name: "sales-tax-processor",
                component: SalesTaxProcessorView,
            },
            {
                path: "order-comparison",
                name: "order-comparison",
                component: OrderComparisonView,
            },
            {
                path: "ulta-marketplace",
                name: "ulta-marketplace",
                component: UltaMarketplaceView,
            },
            {
                path: "",
                redirect: { name: "dashboard" },
            },
        ],
    },
    {
        path: "/:pathMatch(.*)*",
        redirect: "/app",
    },
];

const router = createRouter({
    history: createWebHistory(),
    routes,
});

// Simple guard
router.beforeEach(async (to, from, next) => {
    const publicRoutes = ["login"];
    const authStore = useAuthStore();

    if (!authStore.state.user && authStore.state.token) {
        // try to load user once if we have a token but no user
        try {
            await authStore.fetchMe();
        } catch {
            authStore.logout();
        }
    }

    if (!publicRoutes.includes(to.name) && !authStore.isAuthenticated.value) {
        return next({ name: "login" });
    }

    if (to.name === "login" && authStore.isAuthenticated.value) {
        return next({ name: "dashboard" });
    }

    return next();
});

export default router;
