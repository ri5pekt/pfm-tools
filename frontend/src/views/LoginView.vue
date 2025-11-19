<!-- frontend/src/views/LoginView.vue -->
<template>
    <div class="login-container">
        <div class="login-background">
            <div class="login-background-gradient"></div>
            <div class="login-background-pattern"></div>
        </div>

        <div class="login-card-wrapper">
            <Card class="login-card">
                <template #header>
                    <div class="login-header">
                        <h1 class="login-title">PFM Tools</h1>
                        <p class="login-subtitle">Sign in to your account</p>
                    </div>
                </template>

                <template #content>
                    <Toast />
                    <form @submit.prevent="onSubmit" class="login-form">
                        <div class="login-field">
                            <label for="email" class="login-label">
                                <i class="pi pi-envelope"></i>
                                Email Address
                            </label>
                            <InputText
                                id="email"
                                v-model="email"
                                type="email"
                                placeholder="Enter your email"
                                class="w-full"
                                :class="{ 'p-invalid': error && !email }"
                                autocomplete="email"
                                autofocus
                            />
                        </div>

                        <div class="login-field">
                            <label for="password" class="login-label">
                                <i class="pi pi-lock"></i>
                                Password
                            </label>
                            <Password
                                id="password"
                                v-model="password"
                                placeholder="Enter your password"
                                :feedback="false"
                                toggleMask
                                inputClass="w-full"
                                :class="{ 'p-invalid': error && !password }"
                                autocomplete="current-password"
                            />
                        </div>

                        <Button
                            type="submit"
                            label="Sign In"
                            icon="pi pi-sign-in"
                            class="w-full login-button"
                            :loading="submitting"
                            :disabled="!email || !password"
                        />
                    </form>
                </template>
            </Card>
        </div>
    </div>
</template>

<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useToast } from "primevue/usetoast";
import { useAuthStore } from "../store/authStore";
import Card from "primevue/card";
import InputText from "primevue/inputtext";
import Password from "primevue/password";
import Button from "primevue/button";
import Toast from "primevue/toast";

const email = ref("");
const password = ref("");
const submitting = ref(false);
const error = ref(false);

const toast = useToast();
const router = useRouter();
const auth = useAuthStore();

async function onSubmit() {
    if (!email.value || !password.value) {
        error.value = true;
        return;
    }

    submitting.value = true;
    error.value = false;

    try {
        await auth.login(email.value, password.value);
        toast.add({
            severity: "success",
            summary: "Welcome back!",
            detail: "You have been successfully logged in.",
            life: 3000,
        });
        router.push({ name: "dashboard" });
    } catch (err) {
        console.error(err);
        error.value = true;
        toast.add({
            severity: "error",
            summary: "Login Failed",
            detail: err.message || "Invalid email or password. Please try again.",
            life: 4000,
        });
    } finally {
        submitting.value = false;
    }
}
</script>

<style scoped>
.login-container {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    padding: 2rem;
    overflow: hidden;
}

.login-background {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 0;
}

.login-background-gradient {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
    opacity: 0.9;
}

.login-background-pattern {
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

.login-card-wrapper {
    position: relative;
    z-index: 1;
    width: 100%;
    max-width: 440px;
}

.login-card {
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    border-radius: 16px;
    overflow: hidden;
    backdrop-filter: blur(10px);
    background: rgba(255, 255, 255, 0.95);
}

.login-header {
    text-align: center;
    padding: 2rem 2rem 1rem;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
}

.login-logo {
    width: 64px;
    height: 64px;
    margin: 0 auto 1rem;
    background: rgba(255, 255, 255, 0.2);
    border-radius: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(10px);
}

.login-logo i {
    font-size: 2rem;
}

.login-title {
    font-size: 2rem;
    font-weight: 700;
    margin: 0 0 0.5rem;
    letter-spacing: -0.5px;
}

.login-subtitle {
    font-size: 0.95rem;
    opacity: 0.9;
    margin: 0;
    font-weight: 400;
}

.login-form {
    padding: 2rem;
}

.login-field {
    margin-bottom: 1.5rem;
}

.login-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 600;
    font-size: 0.9rem;
    color: var(--text-color);
    margin-bottom: 0.5rem;
}

.login-label i {
    font-size: 0.85rem;
    opacity: 0.7;
}

.login-button {
    margin-top: 1.5rem;
    height: 3rem;
    font-size: 1rem;
    font-weight: 600;
    border-radius: 8px;
}

:deep(.p-password) {
    width: 100%;
}

:deep(.p-password-input) {
    width: 100%;
}

:deep(.p-invalid) {
    border-color: var(--red-500);
}

@media (max-width: 640px) {
    .login-container {
        padding: 1rem;
    }

    .login-card-wrapper {
        max-width: 100%;
    }

    .login-header {
        padding: 1.5rem 1.5rem 1rem;
    }

    .login-title {
        font-size: 1.75rem;
    }

    .login-form {
        padding: 1.5rem;
    }
}
</style>
