import { http, API_BASE_URL } from "./http";

export async function createExport(dateFrom, dateTo, isManual = true, dateFromDisplay = null, dateToDisplay = null, exportToFile = true, exportToGoogleSheets = true) {
    const body = {
        date_from: dateFrom,
        date_to: dateTo,
        is_manual: isManual,
        export_to_file: exportToFile,
        export_to_google_sheets: exportToGoogleSheets,
    };

    if (dateFromDisplay) {
        body.date_from_display = dateFromDisplay;
    }
    if (dateToDisplay) {
        body.date_to_display = dateToDisplay;
    }

    return http("/app/one-time-vs-subscription/export", {
        method: "POST",
        body: body,
    });
}

export async function getJobs() {
    return http("/app/one-time-vs-subscription/jobs");
}

export async function getJob(jobId) {
    return http(`/app/one-time-vs-subscription/jobs/${jobId}`);
}

export async function downloadJob(jobId) {
    const token = localStorage.getItem("pfm_token");

    return fetch(`${API_BASE_URL}/app/one-time-vs-subscription/jobs/${jobId}/download`, {
        method: "GET",
        headers: {
            Authorization: `Bearer ${token}`,
        },
    }).then(async (res) => {
        if (!res.ok) throw new Error("Download failed");

        const contentType = res.headers.get("content-type") || "";
        const contentDisposition = res.headers.get("content-disposition") || "";

        let filename = null;
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
            if (filenameMatch) {
                filename = filenameMatch[1];
            }
        }

        const blob = await res.blob();

        return {
            blob: blob,
            contentType: contentType,
            filename: filename,
        };
    });
}

export async function deleteJob(jobId) {
    return http(`/app/one-time-vs-subscription/jobs/${jobId}`, {
        method: "DELETE",
    });
}

export async function getSchedulerStatus() {
    return http("/app/one-time-vs-subscription/scheduler/status");
}

// Scheduled Export CRUD
export async function createScheduledExport(data) {
    return http("/app/one-time-vs-subscription/scheduled-exports", {
        method: "POST",
        body: data,
    });
}

export async function getScheduledExports() {
    return http("/app/one-time-vs-subscription/scheduled-exports");
}

export async function getScheduledExport(id) {
    return http(`/app/one-time-vs-subscription/scheduled-exports/${id}`);
}

export async function updateScheduledExport(id, data) {
    return http(`/app/one-time-vs-subscription/scheduled-exports/${id}`, {
        method: "PUT",
        body: data,
    });
}

export async function deleteScheduledExport(id) {
    return http(`/app/one-time-vs-subscription/scheduled-exports/${id}`, {
        method: "DELETE",
    });
}
