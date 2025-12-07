import { http, API_BASE_URL } from "./http";

export async function createExport(date, isManual = true, dateDisplay = null, exportToFile = true, exportToGoogleSheets = true) {
    const body = {
        date: date,
        is_manual: isManual,
        export_to_file: exportToFile,
        export_to_google_sheets: exportToGoogleSheets,
    };

    // Include display date if provided (for showing correct date in UI)
    if (dateDisplay) {
        body.date_display = dateDisplay;
    }

    return http("/app/daily-orders-data/export", {
        method: "POST",
        body: body,
    });
}

export async function getJobs() {
    return http("/app/daily-orders-data/jobs");
}

export async function getJob(jobId) {
    return http(`/app/daily-orders-data/jobs/${jobId}`);
}

export async function downloadJob(jobId) {
    const token = localStorage.getItem("pfm_token");

    return fetch(`${API_BASE_URL}/app/daily-orders-data/jobs/${jobId}/download`, {
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
    return http(`/app/daily-orders-data/jobs/${jobId}`, {
        method: "DELETE",
    });
}

export async function getSchedulerStatus() {
    return http("/app/daily-orders-data/scheduler/status");
}

// Scheduled Export CRUD
export async function createScheduledExport(data) {
    return http("/app/daily-orders-data/scheduled-exports", {
        method: "POST",
        body: data,
    });
}

export async function getScheduledExports() {
    return http("/app/daily-orders-data/scheduled-exports");
}

export async function getScheduledExport(id) {
    return http(`/app/daily-orders-data/scheduled-exports/${id}`);
}

export async function updateScheduledExport(id, data) {
    return http(`/app/daily-orders-data/scheduled-exports/${id}`, {
        method: "PUT",
        body: data,
    });
}

export async function deleteScheduledExport(id) {
    return http(`/app/daily-orders-data/scheduled-exports/${id}`, {
        method: "DELETE",
    });
}

