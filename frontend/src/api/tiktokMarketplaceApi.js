// frontend/src/api/tiktokMarketplaceApi.js
import { http, API_BASE_URL } from "./http";

export async function createExport(startDate, endDate, isManual = true, startDateDisplay = null, endDateDisplay = null, exportToFile = true, exportToGoogleSheets = true) {
    const body = {
        start_date: startDate,
        end_date: endDate,
        is_manual: isManual,
        export_to_file: exportToFile,
        export_to_google_sheets: exportToGoogleSheets,
    };

    // Include display dates if provided (for showing correct dates in UI)
    if (startDateDisplay && endDateDisplay) {
        body.start_date_display = startDateDisplay;
        body.end_date_display = endDateDisplay;
    }

    return http("/app/tiktok-marketplace/export", {
        method: "POST",
        body: body,
    });
}

export async function getJobs() {
    return http("/app/tiktok-marketplace/jobs");
}

export async function getJob(jobId) {
    return http(`/app/tiktok-marketplace/jobs/${jobId}`);
}

export async function downloadJob(jobId) {
    const token = localStorage.getItem("pfm_token");

    return fetch(`${API_BASE_URL}/app/tiktok-marketplace/jobs/${jobId}/download`, {
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
    return http(`/app/tiktok-marketplace/jobs/${jobId}`, {
        method: "DELETE",
    });
}

export async function getSchedulerStatus() {
    return http("/app/tiktok-marketplace/scheduler/status");
}

// Scheduled Export CRUD
export async function createScheduledExport(data) {
    return http("/app/tiktok-marketplace/scheduled-exports", {
        method: "POST",
        body: data,
    });
}

export async function getScheduledExports() {
    return http("/app/tiktok-marketplace/scheduled-exports");
}

export async function getScheduledExport(id) {
    return http(`/app/tiktok-marketplace/scheduled-exports/${id}`);
}

export async function updateScheduledExport(id, data) {
    return http(`/app/tiktok-marketplace/scheduled-exports/${id}`, {
        method: "PUT",
        body: data,
    });
}

export async function deleteScheduledExport(id) {
    return http(`/app/tiktok-marketplace/scheduled-exports/${id}`, {
        method: "DELETE",
    });
}

