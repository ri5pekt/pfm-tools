// frontend/src/api/http.js

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

async function http(path, { method = "GET", body, headers = {} } = {}) {
    const token = localStorage.getItem("pfm_token");

    const finalHeaders = {
        "Content-Type": body instanceof FormData ? undefined : "application/json",
        ...headers,
    };

    if (token) {
        finalHeaders["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(`${API_BASE_URL}${path}`, {
        method,
        headers: Object.fromEntries(Object.entries(finalHeaders).filter(([, v]) => v !== undefined)),
        body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    });

    if (!res.ok) {
        let detail = "Request failed";
        try {
            const data = await res.json();
            detail = data.detail || JSON.stringify(data);
        } catch (_) {}
        throw new Error(detail);
    }

    // 204 no content
    if (res.status === 204) return null;

    return res.json();
}

export { http, API_BASE_URL };
