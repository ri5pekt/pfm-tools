// frontend/src/api/salesTaxApi.js
import { http } from "./http";

export function uploadCsv(file, orderIdHeader, options) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("order_id_header", orderIdHeader);
    formData.append("woo", options.woo || true);
    formData.append("braintree", options.braintree || true);
    formData.append("tax_diff", options.tax_diff || true);
    formData.append("totals_diff", options.totals_diff || true);

    return http("/app/sales-tax-processor/upload", {
        method: "POST",
        body: formData,
    });
}

export function listJobs() {
    return http("/app/sales-tax-processor/jobs", {
        method: "GET",
    });
}

export function getJob(jobId) {
    return http(`/app/sales-tax-processor/job/${jobId}`, {
        method: "GET",
    });
}

export function downloadJob(jobId) {
    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
    const token = localStorage.getItem("pfm_token");

    return fetch(`${API_BASE_URL}/app/sales-tax-processor/job/${jobId}/download`, {
        method: "GET",
        headers: {
            Authorization: `Bearer ${token}`,
        },
    }).then((res) => {
        if (!res.ok) throw new Error("Download failed");
        return res.blob();
    });
}

export function deleteJob(jobId) {
    return http(`/app/sales-tax-processor/job/${jobId}`, {
        method: "DELETE",
    });
}

