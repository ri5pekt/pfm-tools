// frontend/src/api/authApi.js
import { http } from "./http";

export function loginApi(email, password) {
    return http("/auth/login", {
        method: "POST",
        body: { email, password },
    });
}

export function meApi() {
    return http("/auth/me", {
        method: "GET",
    });
}
