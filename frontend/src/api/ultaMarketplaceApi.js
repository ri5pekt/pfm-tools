// frontend/src/api/ultaMarketplaceApi.js
import { http } from "./http";

export async function createExport(startDate, endDate, isManual = true, startDateDisplay = null, endDateDisplay = null) {
    const body = {
        start_date: startDate,
        end_date: endDate,
        is_manual: isManual,
    };

    // Include display dates if provided (for showing correct dates in UI)
    if (startDateDisplay && endDateDisplay) {
        body.start_date_display = startDateDisplay;
        body.end_date_display = endDateDisplay;
    }

    return http("/app/ulta-marketplace/export", {
        method: "POST",
        body: body,
    });
}

export async function getJobs() {
    return http("/app/ulta-marketplace/jobs");
}

export async function getJob(jobId) {
    return http(`/app/ulta-marketplace/jobs/${jobId}`);
}

export async function downloadJob(jobId) {
    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
    const token = localStorage.getItem("pfm_token");

    return fetch(`${API_BASE_URL}/app/ulta-marketplace/jobs/${jobId}/download`, {
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
            filename: filename,
        };
    });
}

export async function deleteJob(jobId) {
    return http(`/app/ulta-marketplace/jobs/${jobId}`, {
        method: "DELETE",
    });
}

export async function getSchedulerStatus() {
    return http("/app/ulta-marketplace/scheduler/status");
}
