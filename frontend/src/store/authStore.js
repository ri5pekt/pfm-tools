// frontend/src/store/authStore.js
import { reactive, computed } from "vue";
import { loginApi, meApi } from "../api/authApi";

const state = reactive({
    token: localStorage.getItem("pfm_token") || null,
    user: null,
    loadingUser: false,
});

export function useAuthStore() {
    const isAuthenticated = computed(() => !!state.token);
    const isAdmin = computed(() => state.user?.is_admin === true);

    async function login(email, password) {
        const data = await loginApi(email, password);
        state.token = data.access_token;
        localStorage.setItem("pfm_token", state.token);
        await fetchMe();
    }

    async function fetchMe() {
        if (!state.token) {
            state.user = null;
            return;
        }
        state.loadingUser = true;
        try {
            state.user = await meApi();
        } finally {
            state.loadingUser = false;
        }
    }

    function logout() {
        state.token = null;
        state.user = null;
        localStorage.removeItem("pfm_token");
    }

    return {
        // state
        state,
        isAuthenticated,
        isAdmin,
        // actions
        login,
        fetchMe,
        logout,
    };
}
