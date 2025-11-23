<template>
    <div class="service-container">
        <ConfirmDialog />
        <div class="service-page-header">
            <h1 class="service-page-title">
                <img src="@/assets/images/logo-ulta.svg" alt="Ulta" class="ulta-logo-header" />
            </h1>
            <p class="service-page-subtitle">Export Ulta marketplace orders to CSV and Google Sheets</p>
        </div>

        <!-- Scheduler Status Widget -->
        <Card class="scheduler-card">
            <template #header>
                <div class="card-header">
                    <i class="pi pi-clock"></i>
                    <h3>Scheduled Exports</h3>
                </div>
            </template>
            <template #content>
                <div class="scheduler-status" v-if="schedulerStatus">
                    <div class="scheduler-info-item">
                        <div class="scheduler-label">
                            <i class="pi pi-calendar-plus"></i>
                            <span>Next Scheduled Export:</span>
                        </div>
                        <div class="scheduler-value">
                            <span v-if="schedulerStatus.next_run" class="text-primary font-semibold">
                                {{ formatDateTime(schedulerStatus.next_run) }}
                            </span>
                            <span v-else class="text-color-secondary">Not scheduled</span>
                        </div>
                    </div>
                    <div class="scheduler-info-item">
                        <div class="scheduler-label">
                            <i class="pi pi-history"></i>
                            <span>Last Scheduled Export:</span>
                        </div>
                        <div class="scheduler-value">
                            <span v-if="schedulerStatus.last_run" class="text-color-secondary">
                                {{ formatDateTime(schedulerStatus.last_run) }}
                            </span>
                            <span v-else class="text-color-secondary">Never</span>
                        </div>
                    </div>
                    <div class="scheduler-status-badge">
                        <Tag
                            :value="schedulerStatus.scheduler_running ? 'Active' : 'Inactive'"
                            :severity="schedulerStatus.scheduler_running ? 'success' : 'warning'"
                            :icon="schedulerStatus.scheduler_running ? 'pi pi-check-circle' : 'pi pi-exclamation-triangle'"
                        />
                    </div>
                </div>
                <div v-else class="scheduler-loading">
                    <i class="pi pi-spin pi-spinner"></i>
                    <span>Loading scheduler status...</span>
                </div>
            </template>
        </Card>

        <!-- Manual Export Section -->
        <Card class="upload-card">
            <template #header>
                <div class="card-header">
                    <i class="pi pi-calendar"></i>
                    <h3>Manual Export</h3>
                </div>
            </template>
            <template #content>
                <form class="upload-section" @submit.prevent="handleManualExport">
                    <div class="option-group">
                        <label for="date-range" class="option-label"> Date Range </label>
                        <DatePicker
                            id="date-range"
                            v-model="dateRange"
                            selectionMode="range"
                            :manualInput="false"
                            iconDisplay="input"
                            class="w-full"
                            :maxDate="new Date()"
                            placeholder="Select date range"
                        />
                    </div>

                    <Button
                        label="Run Export"
                        icon="pi pi-play"
                        class="process-button"
                        :disabled="!dateRange || !Array.isArray(dateRange) || dateRange.length !== 2 || processing"
                        :loading="processing"
                        type="submit"
                    />
                </form>
            </template>
        </Card>

        <!-- Jobs List -->
        <Card class="jobs-card">
            <template #header>
                <div class="card-header">
                    <i class="pi pi-list"></i>
                    <h3>Export History</h3>
                </div>
            </template>
            <template #content>
                <div class="jobs-list">
                    <div v-if="jobs.length === 0" class="empty-jobs">
                        <i class="pi pi-inbox"></i>
                        <p>No exports yet</p>
                        <p class="text-sm text-color-secondary">Run a manual export to get started</p>
                    </div>
                    <div v-for="job in jobs" :key="job.id" class="job-item">
                        <div class="job-header">
                            <div class="job-info">
                                <div class="job-icon">
                                    <i
                                        :class="
                                            job.status === 'done'
                                                ? 'pi pi-check-circle text-green-500'
                                                : job.status === 'error'
                                                ? 'pi pi-times-circle text-red-500'
                                                : job.status === 'running'
                                                ? 'pi pi-spin pi-spinner text-blue-500'
                                                : 'pi pi-clock text-orange-500'
                                        "
                                    ></i>
                                </div>
                                <div class="job-details">
                                    <div class="job-filename">
                                        {{ getJobDisplayName(job) }}
                                    </div>
                                    <div class="job-meta">
                                        <span class="status-badge" :class="`status-${job.status}`">
                                            {{ job.status }}
                                        </span>
                                        <Tag
                                            :value="job.options?.is_manual ? 'Manual' : 'Scheduled'"
                                            :severity="job.options?.is_manual ? 'info' : 'success'"
                                            :icon="job.options?.is_manual ? 'pi pi-user' : 'pi pi-clock'"
                                            class="job-type-tag"
                                        />
                                        <span class="job-date">
                                            {{ formatDate(job.created_at) }}
                                        </span>
                                    </div>
                                </div>
                            </div>
                            <div class="job-actions">
                                <Button
                                    v-if="job.status === 'done'"
                                    icon="pi pi-download"
                                    severity="success"
                                    text
                                    rounded
                                    :aria-label="'Download CSV'"
                                    @click="handleDownload(job.id)"
                                />
                                <Button
                                    icon="pi pi-trash"
                                    severity="danger"
                                    text
                                    rounded
                                    :aria-label="'Delete job'"
                                    @click="confirmDelete(job)"
                                />
                            </div>
                        </div>
                        <div v-if="job.status === 'running' || job.status === 'pending'" class="job-progress">
                            <ProgressBar
                                :key="`progress-${job.id}-${job.options?.progress || 0}`"
                                :value="getProgress(job)"
                                :showValue="false"
                                class="progress-bar"
                            />
                            <span class="progress-text">{{ getProgressText(job) }}</span>
                        </div>
                        <div v-if="job.status === 'error' && job.error_message" class="job-error">
                            <i class="pi pi-exclamation-triangle"></i>
                            <span>{{ job.error_message }}</span>
                        </div>
                    </div>
                </div>
            </template>
        </Card>
    </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from "vue";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";
import Card from "primevue/card";
import Button from "primevue/button";
import DatePicker from "primevue/datepicker";
import Tag from "primevue/tag";
import ProgressBar from "primevue/progressbar";
import ConfirmDialog from "primevue/confirmdialog";
import { createExport, getJobs, downloadJob, deleteJob, getSchedulerStatus } from "../api/ultaMarketplaceApi.js";

const confirm = useConfirm();
const toast = useToast();

const dateRange = ref(null);
const processing = ref(false);
const jobs = ref([]);
const schedulerStatus = ref(null);

// Times are set automatically in formatDateForAPI when sending to the API
// No need to modify the date picker values

const loadingJobs = ref(false);
let refreshInterval = null;

const formatDateTime = (dateString) => {
    if (!dateString) return "N/A";
    // Parse the date string - it should be in ISO format with timezone
    const date = new Date(dateString);

    // Check if date is valid
    if (isNaN(date.getTime())) {
        return "Invalid date";
    }

    // Use the browser's local timezone for display
    // This will automatically use the user's system timezone
    const options = {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZoneName: "short",
        hour12: true, // Use 12-hour format with AM/PM
    };

    return date.toLocaleString("en-US", options);
};

const formatDate = (dateString) => {
    if (!dateString) return "-";
    const date = new Date(dateString);
    // Use the browser's local timezone for display
    return date.toLocaleString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
    });
};

const formatDateRange = (startDateStr, endDateStr) => {
    if (!startDateStr || !endDateStr) return "-";

    // If we have display dates stored, use those (they're the original selected dates)
    // Otherwise, parse from the API date strings
    let startDateOnly, endDateOnly;

    if (typeof startDateStr === "object" && startDateStr.start_date_display) {
        // Use stored display dates
        startDateOnly = startDateStr.start_date_display;
        endDateOnly = startDateStr.end_date_display;
    } else {
        // Parse from API date strings
        startDateOnly = startDateStr.split("T")[0];
        endDateOnly = endDateStr.split("T")[0];
    }

    // Parse as local date to avoid timezone shifts
    const startParts = startDateOnly.split("-");
    const endParts = endDateOnly.split("-");
    const start = new Date(parseInt(startParts[0]), parseInt(startParts[1]) - 1, parseInt(startParts[2]));
    const end = new Date(parseInt(endParts[0]), parseInt(endParts[1]) - 1, parseInt(endParts[2]));

    const startFormatted = start.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    const endFormatted = end.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    return `${startFormatted} - ${endFormatted}`;
};

// Helper function to get Chicago timezone offset for a specific date
// Returns offset in hours (CDT: -5, CST: -6)
const getChicagoOffset = (year, month, day) => {
    // Create a date at a known UTC time (noon) and check what time it is in Chicago
    // This tells us the offset
    const noonUTC = new Date(`${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}T12:00:00Z`);

    const chicagoFormatter = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/Chicago",
        hour: "2-digit",
        hour12: false,
    });

    const chicagoHour = parseInt(chicagoFormatter.format(noonUTC));

    // At noon UTC (12:00):
    // - If it's 7 AM Chicago, offset is -5 (CDT)
    // - If it's 6 AM Chicago, offset is -6 (CST)
    const offsetHours = chicagoHour - 12;

    return offsetHours;
};

const formatDateForAPI = (date, isStartDate = true) => {
    if (!date) return null;
    const d = new Date(date);

    // Match Ulta dashboard behavior: use timezone active at midnight of the date
    // Extract date components (these are in user's local timezone, but we only need the date part)
    const year = d.getFullYear();
    const month = d.getMonth();
    const day = d.getDate();

    // Get Chicago timezone offset for this specific date
    const offsetHours = getChicagoOffset(year, month, day);

    // Create date string
    const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;

    if (isStartDate) {
        // Start date: midnight in Chicago time
        // If Chicago is UTC-5, then Chicago 00:00:00 = UTC 05:00:00
        // If Chicago is UTC-6, then Chicago 00:00:00 = UTC 06:00:00
        // UTC time = Chicago time - offset (offset is negative, so we add hours)
        const utcHour = Math.abs(offsetHours); // offset is -5 or -6, so abs gives 5 or 6
        const utcStart = new Date(`${dateStr}T${String(utcHour).padStart(2, "0")}:00:00.000Z`);
        return utcStart.toISOString();
    } else {
        // End date: 23:59:59.999 in Chicago time
        // If Chicago is UTC-5, then Chicago 23:59:59.999 = UTC 04:59:59.999 (next day)
        // If Chicago is UTC-6, then Chicago 23:59:59.999 = UTC 05:59:59.999 (next day)
        // We need to add 1 day and subtract offset hours
        const nextDay = new Date(year, month, day + 1);
        const nextDayStr = `${nextDay.getFullYear()}-${String(nextDay.getMonth() + 1).padStart(2, "0")}-${String(
            nextDay.getDate()
        ).padStart(2, "0")}`;
        const utcHour = Math.abs(offsetHours) - 1; // 23:59 becomes 04:59 or 05:59 (next day)
        const utcEnd = new Date(`${nextDayStr}T${String(utcHour).padStart(2, "0")}:59:59.999Z`);
        return utcEnd.toISOString();
    }
};

const getJobDisplayName = (job) => {
    // Use stored display dates if available (original selected dates)
    if (job.options?.start_date_display && job.options?.end_date_display) {
        const startParts = job.options.start_date_display.split("-");
        const endParts = job.options.end_date_display.split("-");
        const start = new Date(parseInt(startParts[0]), parseInt(startParts[1]) - 1, parseInt(startParts[2]));
        const end = new Date(parseInt(endParts[0]), parseInt(endParts[1]) - 1, parseInt(endParts[2]));
        const startFormatted = start.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
        const endFormatted = end.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
        return `Export: ${startFormatted} - ${endFormatted}`;
    } else if (job.options?.start_date && job.options?.end_date) {
        // Fallback to API dates
        return `Export: ${formatDateRange(job.options.start_date, job.options.end_date)}`;
    }
    return `Export #${job.id}`;
};

const getProgress = (job) => {
    return job.options?.progress || 0;
};

const getProgressText = (job) => {
    const progress = getProgress(job);
    const message = job.options?.status_message || "Processing...";
    return `${message} (${progress}%)`;
};

const handleManualExport = async () => {
    if (!dateRange.value || !Array.isArray(dateRange.value) || dateRange.value.length !== 2) {
        toast.add({
            severity: "warn",
            summary: "Validation Error",
            detail: "Please select a date range",
            life: 3000,
        });
        return;
    }

    const startDateISO = formatDateForAPI(dateRange.value[0], true); // Start date: 00:00:00
    const endDateISO = formatDateForAPI(dateRange.value[1], false); // End date: 23:59:59

    if (!startDateISO || !endDateISO) {
        toast.add({
            severity: "error",
            summary: "Error",
            detail: "Invalid date format",
            life: 3000,
        });
        return;
    }

    // Store original selected dates for display (as date strings YYYY-MM-DD)
    const startDateDisplay = `${dateRange.value[0].getFullYear()}-${String(dateRange.value[0].getMonth() + 1).padStart(
        2,
        "0"
    )}-${String(dateRange.value[0].getDate()).padStart(2, "0")}`;
    const endDateDisplay = `${dateRange.value[1].getFullYear()}-${String(dateRange.value[1].getMonth() + 1).padStart(
        2,
        "0"
    )}-${String(dateRange.value[1].getDate()).padStart(2, "0")}`;

    processing.value = true;
    try {
        const response = await createExport(startDateISO, endDateISO, true, startDateDisplay, endDateDisplay);
        toast.add({
            severity: "success",
            summary: "Export Started",
            detail: `Job ${response.job_id} has been queued`,
            life: 3000,
        });

        // Reset form
        dateRange.value = null;

        // Reload jobs list
        await loadJobs();

        // Poll for updates
        pollJobStatus(response.job_id);
    } catch (error) {
        console.error("Export error:", error);
        toast.add({
            severity: "error",
            summary: "Export Failed",
            detail: error.message || "Failed to start export",
            life: 5000,
        });
    } finally {
        processing.value = false;
    }
};

const loadJobs = async () => {
    loadingJobs.value = true;
    try {
        const response = await getJobs();
        jobs.value = response;
    } catch (error) {
        console.error("Error loading jobs:", error);
        toast.add({
            severity: "error",
            summary: "Error",
            detail: "Failed to load jobs",
            life: 3000,
        });
    } finally {
        loadingJobs.value = false;
    }
};

const pollJobStatus = (jobId) => {
    const interval = setInterval(async () => {
        try {
            await loadJobs();
            const job = jobs.value.find((j) => j.id === jobId);
            if (job && (job.status === "done" || job.status === "error")) {
                clearInterval(interval);
            }
        } catch (error) {
            console.error("Error polling job status:", error);
            clearInterval(interval);
        }
    }, 2000); // Poll every 2 seconds

    // Stop polling after 5 minutes
    setTimeout(() => clearInterval(interval), 5 * 60 * 1000);
};

const handleDownload = async (jobId) => {
    try {
        const response = await downloadJob(jobId);
        const blob = response.blob;
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;

        // Use filename from response or default
        const filename = response.filename || `ulta_export_${jobId}.csv`;

        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);

        toast.add({
            severity: "success",
            summary: "Download Started",
            detail: "CSV file download started",
            life: 3000,
        });
    } catch (error) {
        console.error("Download error:", error);
        toast.add({
            severity: "error",
            summary: "Download Failed",
            detail: error.message || "Failed to download file",
            life: 5000,
        });
    }
};

const confirmDelete = (job) => {
    const isActive = job.status === "pending" || job.status === "running";
    const message = isActive
        ? `Are you sure you want to delete this export? This will stop the processing and permanently delete the job and all associated files.`
        : `Are you sure you want to delete this export? This will permanently delete the job and all associated files.`;

    confirm.require({
        message: message,
        header: isActive ? "Stop and Delete Export" : "Delete Export",
        icon: "pi pi-exclamation-triangle",
        rejectClass: "p-button-secondary p-button-outlined",
        rejectLabel: "Cancel",
        acceptLabel: isActive ? "Stop & Delete" : "Delete",
        accept: async () => {
            await handleDelete(job.id);
        },
    });
};

const handleDelete = async (jobId) => {
    try {
        await deleteJob(jobId);
        toast.add({
            severity: "success",
            summary: "Export Deleted",
            detail: "Export and associated files have been deleted",
            life: 3000,
        });
        await loadJobs();
    } catch (error) {
        console.error("Delete error:", error);
        toast.add({
            severity: "error",
            summary: "Delete Failed",
            detail: error.message || "Failed to delete export",
            life: 4000,
        });
    }
};

async function loadSchedulerStatus() {
    try {
        schedulerStatus.value = await getSchedulerStatus();
    } catch (error) {
        console.error("Failed to load scheduler status:", error);
    }
}

onMounted(async () => {
    await loadJobs();
    await loadSchedulerStatus();
    refreshInterval = setInterval(loadJobs, 2000);
    // Refresh scheduler status every 30 seconds
    setInterval(loadSchedulerStatus, 30000);
});

onUnmounted(() => {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
});
</script>

<style scoped>
.service-page-title {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.ulta-logo-header {
    height: 2.5rem;
    width: auto;
    object-fit: contain;
}

.upload-card,
.jobs-card {
    margin-bottom: 2rem;
    border-radius: 12px;
    border: 1px solid var(--surface-border);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.card-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1.5rem;
    border-bottom: 1px solid var(--surface-border);
}

.card-header i {
    font-size: 1.25rem;
    color: var(--primary-color);
}

.card-header h3 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-color);
}

.upload-section {
    padding: 1.5rem;
}

.option-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.option-label {
    font-weight: 600;
    font-size: 0.95rem;
    color: var(--text-color);
}

.process-button {
    width: 100%;
    height: 3rem;
    font-size: 1rem;
    font-weight: 600;
    margin-top: 1.5rem;
    border-radius: 8px;
}

.jobs-list {
    padding: 1.5rem;
}

.empty-jobs {
    text-align: center;
    padding: 3rem 1rem;
    color: var(--text-color-secondary);
}

.empty-jobs i {
    font-size: 3rem;
    margin-bottom: 1rem;
    opacity: 0.5;
}

.empty-jobs p {
    margin: 0.5rem 0;
}

.job-item {
    border: 1px solid var(--surface-border);
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 1rem;
    background: var(--surface-0);
    transition: all 0.2s;
}

.job-item:hover {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.job-item:last-child {
    margin-bottom: 0;
}

.job-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
}

.job-info {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex: 1;
}

.job-icon {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    background: var(--surface-100);
    flex-shrink: 0;
}

.job-icon i {
    font-size: 1.25rem;
}

.job-details {
    flex: 1;
    min-width: 0;
}

.job-filename {
    font-weight: 600;
    color: var(--text-color);
    font-size: 0.95rem;
    margin-bottom: 0.5rem;
    word-break: break-word;
}

.job-meta {
    display: flex;
    align-items: center;
    gap: 1rem;
    font-size: 0.85rem;
}

.status-badge {
    padding: 0.25rem 0.75rem;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.status-done {
    background: var(--green-100);
    color: var(--green-700);
}

.status-error {
    background: var(--red-100);
    color: var(--red-700);
}

.status-running {
    background: var(--blue-100);
    color: var(--blue-700);
}

.status-pending {
    background: var(--orange-100);
    color: var(--orange-700);
}

.job-type-tag {
    font-size: 0.75rem;
}

.job-date {
    color: var(--text-color-secondary);
    font-size: 0.85rem;
}

.job-actions {
    display: flex;
    gap: 0.5rem;
    flex-shrink: 0;
}

.job-progress {
    margin-top: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.progress-bar {
    height: 0.5rem;
}

.progress-text {
    font-size: 0.85rem;
    color: var(--text-color-secondary);
}

.job-error {
    margin-top: 1rem;
    padding: 0.75rem;
    background: var(--red-50);
    border: 1px solid var(--red-200);
    border-radius: 8px;
    color: var(--red-700);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
}

.job-error i {
    font-size: 1rem;
}

.scheduler-card {
    margin-bottom: 2rem;
}

.scheduler-status {
    padding: 1.5rem;
}

.scheduler-info-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 0;
    border-bottom: 1px solid var(--surface-border);
}

.scheduler-info-item:last-child {
    border-bottom: none;
}

.scheduler-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 500;
    color: var(--text-color-secondary);
}

.scheduler-label i {
    font-size: 1rem;
}

.scheduler-value {
    font-size: 0.95rem;
}

.scheduler-status-badge {
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--surface-border);
}

.scheduler-loading {
    padding: 2rem;
    text-align: center;
    color: var(--text-color-secondary);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
}
</style>
