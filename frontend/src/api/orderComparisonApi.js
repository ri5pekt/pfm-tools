// frontend/src/api/orderComparisonApi.js
import { http } from "./http";

export function uploadComparison(file, orderIdHeader, dateFrom, dateTo, usaOnly = true, excludeStates = [], excludeComplytStates = []) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("order_id_header", orderIdHeader);

    // Format dates using local timezone (not UTC) to preserve the selected date
    // toISOString() converts to UTC which can shift the date by one day
    function formatDateLocal(date) {
        if (date instanceof Date) {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            return `${year}-${month}-${day}`;
        } else if (typeof date === 'string') {
            // If it's already a string in YYYY-MM-DD format, use it as-is
            return date.split('T')[0];
        } else {
            return new Date(date).toISOString().split("T")[0];
        }
    }

    formData.append("date_from", formatDateLocal(dateFrom));
    formData.append("date_to", formatDateLocal(dateTo));
    formData.append("usa_only", usaOnly ? "true" : "false");

    // Convert excludeStates array to comma-separated string
    if (excludeStates && excludeStates.length > 0) {
        const statesString = Array.isArray(excludeStates) ? excludeStates.join(",") : excludeStates;
        formData.append("exclude_states", statesString);
    }

    // Convert excludeComplytStates array to comma-separated string
    if (excludeComplytStates && excludeComplytStates.length > 0) {
        const statesString = Array.isArray(excludeComplytStates) ? excludeComplytStates.join(",") : excludeComplytStates;
        formData.append("exclude_complyt_states", statesString);
    }

    return http("/app/order-comparison/upload", {
        method: "POST",
        body: formData,
    });
}

export function listJobs() {
    return http("/app/order-comparison/jobs", {
        method: "GET",
    });
}

export function getJob(jobId) {
    return http(`/app/order-comparison/job/${jobId}`, {
        method: "GET",
    });
}

export function downloadJob(jobId) {
    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
    const token = localStorage.getItem("pfm_token");

    return fetch(`${API_BASE_URL}/app/order-comparison/job/${jobId}/download`, {
        method: "GET",
        headers: {
            Authorization: `Bearer ${token}`,
        },
    }).then(async (res) => {
        if (!res.ok) throw new Error("Download failed");

        // Get content type and filename from response headers
        const contentType = res.headers.get("content-type") || "";
        const contentDisposition = res.headers.get("content-disposition") || "";

        // Extract filename from Content-Disposition header if available
        let filename = null;
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
            if (filenameMatch) {
                filename = filenameMatch[1];
            }
        }

        const blob = await res.blob();

        // Return object with blob and metadata
        return {
            blob: blob,
            contentType: contentType,
            filename: filename
        };
    });
}

export function deleteJob(jobId) {
    return http(`/app/order-comparison/job/${jobId}`, {
        method: "DELETE",
    });
}

