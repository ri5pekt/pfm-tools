// src/main.js
import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";

// PrimeVue core
import PrimeVue from "primevue/config";
import ToastService from "primevue/toastservice";
import ConfirmationService from "primevue/confirmationservice";

// PrimeVue v4 theme (Aura)
import Aura from "@primeuix/themes/aura";

// Utilities
import "primeicons/primeicons.css";
import "primeflex/primeflex.css";

const app = createApp(App);

app.use(router);

app.use(PrimeVue, {
    theme: {
        preset: Aura,
    },
});

app.use(ToastService);
app.use(ConfirmationService);

app.mount("#app");
