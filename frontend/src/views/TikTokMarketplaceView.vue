<template>
    <div class="service-container">
        <ConfirmDialog />
        <div class="service-page-header">
            <h1 class="service-page-title">
                <span class="tiktok-logo-text">TikTok Marketplace</span>
            </h1>
            <p class="service-page-subtitle">Export TikTok marketplace orders to CSV and Google Sheets</p>
        </div>

        <!-- Google Sheets Link -->
        <Card class="google-sheets-link-card">
            <template #content>
                <div class="google-sheets-link-content">
                    <img src="@/assets/images/logo-google-sheets.svg" alt="Google Sheets" class="google-sheets-icon" />
                    <div class="google-sheets-link-info">
                        <span class="google-sheets-link-label">View Live Google Sheets</span>
                        <span class="google-sheets-link-desc">Access the real-time TikTok orders spreadsheet</span>
                    </div>
                    <Button
                        label="Open Google Sheets"
                        icon="pi pi-external-link"
                        severity="secondary"
                        outlined
                        @click="openGoogleSheets(googleSheetsUrl)"
                    />
                </div>
            </template>
        </Card>

        <!-- Scheduled Exports Section -->
        <Card class="scheduler-card">
            <template #header>
                <div class="card-header">
                    <i class="pi pi-clock"></i>
                    <h3>Scheduled Exports</h3>
                    <Button
                        label="New Scheduled Export"
                        icon="pi pi-plus"
                        class="p-button-sm"
                        @click="showCreateDialog = true"
                    />
                </div>
            </template>
            <template #content>
                <!-- Scheduled Exports List -->
                <div class="scheduled-exports-list">
                    <div v-if="scheduledExports.length === 0" class="empty-scheduled">
                        <i class="pi pi-calendar-times"></i>
                        <p>No scheduled exports</p>
                        <p class="text-sm text-color-secondary">Create a new scheduled export to automate your exports</p>
                    </div>
                    <div v-for="scheduled in scheduledExports" :key="scheduled.id" class="scheduled-item">
                        <div class="scheduled-header">
                            <div class="scheduled-info">
                                <div class="scheduled-name">
                                    <i class="pi pi-clock"></i>
                                    <span>{{ scheduled.name }}</span>
                                </div>
                                <div class="scheduled-details">
                                    <Tag
                                        :value="getPeriodLabel(scheduled.period)"
                                        severity="info"
                                        class="period-tag"
                                    />
                                    <span class="scheduled-schedule">{{ getScheduleDescription(scheduled) }}</span>
                                    <Tag
                                        :value="scheduled.enabled ? 'Enabled' : 'Disabled'"
                                        :severity="scheduled.enabled ? 'success' : 'secondary'"
                                        class="status-tag"
                                    />
                                </div>
                            </div>
                            <div class="scheduled-actions">
                                <Button
                                    icon="pi pi-pencil"
                                    severity="secondary"
                                    text
                                    rounded
                                    :aria-label="'Edit scheduled export'"
                                    @click="editScheduledExport(scheduled)"
                                />
                                <Button
                                    icon="pi pi-trash"
                                    severity="danger"
                                    text
                                    rounded
                                    :aria-label="'Delete scheduled export'"
                                    @click="confirmDeleteScheduled(scheduled)"
                                />
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Scheduler Status -->
                <div class="scheduler-status-section" v-if="schedulerStatus">
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
                </div>
            </template>
        </Card>

        <!-- Create/Edit Scheduled Export Dialog -->
        <Dialog
            v-model:visible="showCreateDialog"
            :header="editingScheduled ? 'Edit Scheduled Export' : 'Create Scheduled Export'"
            :modal="true"
            :style="{ width: '600px' }"
            @hide="resetScheduledForm"
        >
            <form @submit.prevent="saveScheduledExport">
                <div class="form-field">
                    <label for="name">Name *</label>
                    <InputText
                        id="name"
                        v-model="scheduledForm.name"
                        placeholder="e.g., Daily Morning Export"
                        :class="{ 'p-invalid': scheduledFormErrors.name }"
                    />
                    <small v-if="scheduledFormErrors.name" class="p-error">{{ scheduledFormErrors.name }}</small>
                </div>

                <div class="form-field">
                    <label for="period">Period *</label>
                    <Select
                        id="period"
                        v-model="scheduledForm.period"
                        :options="periodOptions"
                        optionLabel="label"
                        optionValue="value"
                        placeholder="Select period"
                        :class="{ 'p-invalid': scheduledFormErrors.period }"
                        @change="onPeriodChange"
                    />
                    <small v-if="scheduledFormErrors.period" class="p-error">{{ scheduledFormErrors.period }}</small>
                </div>

                <div class="form-field">
                    <label for="frequency">Frequency *</label>
                    <InputNumber
                        id="frequency"
                        v-model="scheduledForm.frequency"
                        :min="1"
                        placeholder="Every X"
                        :class="{ 'p-invalid': scheduledFormErrors.frequency }"
                    />
                    <small v-if="scheduledFormErrors.frequency" class="p-error">{{ scheduledFormErrors.frequency }}</small>
                    <small class="p-text-secondary">
                        <span v-if="scheduledForm.period === 'minute'">Every X minute(s)</span>
                        <span v-else-if="scheduledForm.period === 'daily'">Every X day(s)</span>
                        <span v-else-if="scheduledForm.period === 'weekly'">Every X week(s)</span>
                        <span v-else-if="scheduledForm.period === 'monthly'">Every X month(s)</span>
                        <span v-else>Frequency</span>
                    </small>
                </div>

                <div class="form-field" v-if="scheduledForm.period === 'daily' || scheduledForm.period === 'weekly' || scheduledForm.period === 'monthly'">
                    <label for="time">Time *</label>
                    <InputText
                        id="time"
                        v-model="scheduledForm.time"
                        placeholder="HH:MM (24-hour format, e.g., 09:00)"
                        :class="{ 'p-invalid': scheduledFormErrors.time }"
                    />
                    <small v-if="scheduledFormErrors.time" class="p-error">{{ scheduledFormErrors.time }}</small>
                    <small class="p-text-secondary">Time in 24-hour format (e.g., 09:00 for 9 AM, 14:30 for 2:30 PM)</small>
                </div>

                <div class="form-field" v-if="scheduledForm.period === 'weekly'">
                    <label for="day_of_week">Day of Week *</label>
                    <Select
                        id="day_of_week"
                        v-model="scheduledForm.day_of_week"
                        :options="dayOfWeekOptions"
                        optionLabel="label"
                        optionValue="value"
                        placeholder="Select day"
                        :class="{ 'p-invalid': scheduledFormErrors.day_of_week }"
                    />
                    <small v-if="scheduledFormErrors.day_of_week" class="p-error">{{ scheduledFormErrors.day_of_week }}</small>
                </div>

                <div class="form-field" v-if="scheduledForm.period === 'monthly'">
                    <label for="day_of_month">Day of Month *</label>
                    <InputNumber
                        id="day_of_month"
                        v-model="scheduledForm.day_of_month"
                        :min="1"
                        :max="31"
                        placeholder="1-31"
                        :class="{ 'p-invalid': scheduledFormErrors.day_of_month }"
                    />
                    <small v-if="scheduledFormErrors.day_of_month" class="p-error">{{ scheduledFormErrors.day_of_month }}</small>
                </div>

                <div class="form-field">
                    <label for="timezone">Timezone *</label>
                    <Select
                        id="timezone"
                        v-model="scheduledForm.timezone"
                        :options="timezoneOptions"
                        placeholder="Select timezone"
                        :class="{ 'p-invalid': scheduledFormErrors.timezone }"
                    />
                    <small v-if="scheduledFormErrors.timezone" class="p-error">{{ scheduledFormErrors.timezone }}</small>
                </div>

                <div class="form-field">
                    <div class="flex align-items-center gap-2">
                        <Checkbox
                            id="enabled"
                            v-model="scheduledForm.enabled"
                            :binary="true"
                        />
                        <label for="enabled">Enabled</label>
                    </div>
                </div>
            </form>

            <template #footer>
                <Button
                    label="Cancel"
                    icon="pi pi-times"
                    severity="secondary"
                    @click="showCreateDialog = false"
                />
                <Button
                    :label="editingScheduled ? 'Update' : 'Create'"
                    icon="pi pi-check"
                    @click="saveScheduledExport"
                    :loading="savingScheduled"
                />
            </template>
        </Dialog>

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

                    <div class="export-options">
                        <div class="export-option-item">
                            <Checkbox
                                id="export-to-file"
                                v-model="exportToFile"
                                :binary="true"
                            />
                            <label for="export-to-file">Export to File (CSV)</label>
                        </div>
                        <div class="export-option-item">
                            <Checkbox
                                id="export-to-google-sheets"
                                v-model="exportToGoogleSheets"
                                :binary="true"
                            />
                            <label for="export-to-google-sheets">Export to Google Sheets</label>
                        </div>
                    </div>

                    <div v-if="!exportToFile && !exportToGoogleSheets" class="export-warning">
                        <i class="pi pi-exclamation-triangle"></i>
                        <span>Please select at least one export option</span>
                    </div>

                    <Button
                        label="Run Export"
                        icon="pi pi-play"
                        class="process-button"
                        :disabled="!dateRange || !Array.isArray(dateRange) || dateRange.length !== 2 || processing || (!exportToFile && !exportToGoogleSheets)"
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
                                    v-if="job.status === 'done' && hasFileOutput(job)"
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
import Dialog from "primevue/dialog";
import InputText from "primevue/inputtext";
import InputNumber from "primevue/inputnumber";
import Select from "primevue/select";
import Checkbox from "primevue/checkbox";
import {
    createExport,
    getJobs,
    downloadJob,
    deleteJob,
    getSchedulerStatus,
    createScheduledExport,
    getScheduledExports,
    updateScheduledExport,
    deleteScheduledExport,
} from "../api/tiktokMarketplaceApi.js";

const confirm = useConfirm();
const toast = useToast();

const dateRange = ref(null);
const processing = ref(false);
const jobs = ref([]);
const schedulerStatus = ref(null);
const scheduledExports = ref([]);
const showCreateDialog = ref(false);
const editingScheduled = ref(false);
const savingScheduled = ref(false);
const exportToFile = ref(true);
const exportToGoogleSheets = ref(true);
const googleSheetsUrl = ref("https://docs.google.com/spreadsheets/d/13yEqBq3Ac3joFVwRUSFbEBMMsrbS3ncvDiPxaMba8ZQ/edit?usp=sharing");

const scheduledForm = ref({
    name: "",
    period: null,
    frequency: 1,
    time: null,
    day_of_week: null,
    day_of_month: null,
    timezone: "UTC",
    enabled: true,
});

const scheduledFormErrors = ref({});

const periodOptions = [
    { label: "Minute", value: "minute" },
    { label: "Daily", value: "daily" },
    { label: "Weekly", value: "weekly" },
    { label: "Monthly", value: "monthly" },
];

const dayOfWeekOptions = [
    { label: "Monday", value: 0 },
    { label: "Tuesday", value: 1 },
    { label: "Wednesday", value: 2 },
    { label: "Thursday", value: 3 },
    { label: "Friday", value: 4 },
    { label: "Saturday", value: 5 },
    { label: "Sunday", value: 6 },
];

const timezoneOptions = [
    "UTC",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Paris",
    "Asia/Jerusalem",
    "Asia/Tokyo",
    "Australia/Sydney",
];

const loadingJobs = ref(false);
let refreshInterval = null;

const formatDateTime = (dateString) => {
    if (!dateString) return "N/A";
    const date = new Date(dateString);
    if (isNaN(date.getTime())) {
        return "Invalid date";
    }
    const options = {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZoneName: "short",
        hour12: true,
    };
    return date.toLocaleString("en-US", options);
};

const openGoogleSheets = (url) => {
    if (url) {
        window.open(url, "_blank", "noopener,noreferrer");
    } else {
        toast.add({
            severity: "warn",
            summary: "Google Sheets URL Not Configured",
            detail: "Please configure the Google Sheets URL in the settings",
            life: 3000,
        });
    }
};

const formatDate = (dateString) => {
    if (!dateString) return "-";
    const date = new Date(dateString);
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
    let startDateOnly, endDateOnly;

    if (typeof startDateStr === "object" && startDateStr.start_date_display) {
        startDateOnly = startDateStr.start_date_display;
        endDateOnly = startDateStr.end_date_display;
    } else {
        startDateOnly = startDateStr.split("T")[0];
        endDateOnly = endDateStr.split("T")[0];
    }

    const startParts = startDateOnly.split("-");
    const endParts = endDateOnly.split("-");
    const start = new Date(parseInt(startParts[0]), parseInt(startParts[1]) - 1, parseInt(startParts[2]));
    const end = new Date(parseInt(endParts[0]), parseInt(endParts[1]) - 1, parseInt(endParts[2]));

    const startFormatted = start.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    const endFormatted = end.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    return `${startFormatted} - ${endFormatted}`;
};

// Helper function to get Chicago timezone offset for a specific date
const getChicagoOffset = (year, month, day) => {
    const noonUTC = new Date(`${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}T12:00:00Z`);
    const chicagoFormatter = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/Chicago",
        hour: "2-digit",
        hour12: false,
    });
    const chicagoHour = parseInt(chicagoFormatter.format(noonUTC));
    const offsetHours = chicagoHour - 12;
    return offsetHours;
};

const formatDateForAPI = (date, isStartDate = true) => {
    if (!date) return null;
    const d = new Date(date);
    const year = d.getFullYear();
    const month = d.getMonth();
    const day = d.getDate();
    const offsetHours = getChicagoOffset(year, month, day);
    const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;

    if (isStartDate) {
        const utcHour = Math.abs(offsetHours);
        const utcStart = new Date(`${dateStr}T${String(utcHour).padStart(2, "0")}:00:00.000Z`);
        return utcStart.toISOString();
    } else {
        const nextDay = new Date(year, month, day + 1);
        const nextDayStr = `${nextDay.getFullYear()}-${String(nextDay.getMonth() + 1).padStart(2, "0")}-${String(
            nextDay.getDate()
        ).padStart(2, "0")}`;
        const utcHour = Math.abs(offsetHours) - 1;
        const utcEnd = new Date(`${nextDayStr}T${String(utcHour).padStart(2, "0")}:59:59.999Z`);
        return utcEnd.toISOString();
    }
};

const getJobDisplayName = (job) => {
    if (job.options?.start_date_display && job.options?.end_date_display) {
        const startParts = job.options.start_date_display.split("-");
        const endParts = job.options.end_date_display.split("-");
        const start = new Date(parseInt(startParts[0]), parseInt(startParts[1]) - 1, parseInt(startParts[2]));
        const end = new Date(parseInt(endParts[0]), parseInt(endParts[1]) - 1, parseInt(endParts[2]));
        const startFormatted = start.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
        const endFormatted = end.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
        return `Export: ${startFormatted} - ${endFormatted}`;
    } else if (job.options?.start_date && job.options?.end_date) {
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

const hasFileOutput = (job) => {
    return !!job.output_filename;
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

    const startDateISO = formatDateForAPI(dateRange.value[0], true);
    const endDateISO = formatDateForAPI(dateRange.value[1], false);

    if (!startDateISO || !endDateISO) {
        toast.add({
            severity: "error",
            summary: "Error",
            detail: "Invalid date format",
            life: 3000,
        });
        return;
    }

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
        const response = await createExport(startDateISO, endDateISO, true, startDateDisplay, endDateDisplay, exportToFile.value, exportToGoogleSheets.value);
        toast.add({
            severity: "success",
            summary: "Export Started",
            detail: `Job ${response.job_id} has been queued`,
            life: 3000,
        });

        dateRange.value = null;
        await loadJobs();
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
    }, 2000);

    setTimeout(() => clearInterval(interval), 5 * 60 * 1000);
};

const handleDownload = async (jobId) => {
    try {
        const response = await downloadJob(jobId);
        const blob = response.blob;
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        const filename = response.filename || `tiktok_export_${jobId}.csv`;
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

async function loadScheduledExports() {
    try {
        scheduledExports.value = await getScheduledExports();
    } catch (error) {
        console.error("Failed to load scheduled exports:", error);
        toast.add({
            severity: "error",
            summary: "Error",
            detail: "Failed to load scheduled exports",
            life: 3000,
        });
    }
}

function getPeriodLabel(period) {
    const option = periodOptions.find((p) => p.value === period);
    return option ? option.label : period;
}

function getScheduleDescription(scheduled) {
    const frequency = scheduled.frequency || 1;
    let desc = "";

    if (scheduled.period === "minute") {
        desc = `Every ${frequency} minute${frequency !== 1 ? "s" : ""}`;
    } else if (scheduled.period === "daily") {
        desc = `Every ${frequency} day${frequency !== 1 ? "s" : ""}`;
        if (scheduled.time) {
            desc += ` at ${scheduled.time}`;
        }
    } else if (scheduled.period === "weekly") {
        desc = `Every ${frequency} week${frequency !== 1 ? "s" : ""}`;
        if (scheduled.day_of_week !== null) {
            const dayOption = dayOfWeekOptions.find((d) => d.value === scheduled.day_of_week);
            desc = `${dayOption ? dayOption.label : ""} ${desc}`;
        }
        if (scheduled.time) {
            desc += ` at ${scheduled.time}`;
        }
    } else if (scheduled.period === "monthly") {
        desc = `Every ${frequency} month${frequency !== 1 ? "s" : ""}`;
        if (scheduled.day_of_month !== null) {
            desc += ` on day ${scheduled.day_of_month}`;
        }
        if (scheduled.time) {
            desc += ` at ${scheduled.time}`;
        }
    }

    if (scheduled.timezone && scheduled.timezone !== "UTC") {
        desc += ` (${scheduled.timezone})`;
    }
    return desc || "Not configured";
}

function resetScheduledForm() {
    scheduledForm.value = {
        name: "",
        period: null,
        frequency: 1,
        time: null,
        day_of_week: null,
        day_of_month: null,
        timezone: "UTC",
        enabled: true,
    };
    scheduledFormErrors.value = {};
    editingScheduled.value = false;
}

function onPeriodChange() {
    scheduledForm.value.day_of_week = null;
    scheduledForm.value.day_of_month = null;
}

function editScheduledExport(scheduled) {
    scheduledForm.value = {
        name: scheduled.name,
        period: scheduled.period,
        frequency: scheduled.frequency || 1,
        time: scheduled.time,
        day_of_week: scheduled.day_of_week,
        day_of_month: scheduled.day_of_month,
        timezone: scheduled.timezone,
        enabled: scheduled.enabled,
    };
    editingScheduled.value = scheduled;
    showCreateDialog.value = true;
}

function validateScheduledForm() {
    scheduledFormErrors.value = {};

    if (!scheduledForm.value.name || scheduledForm.value.name.trim() === "") {
        scheduledFormErrors.value.name = "Name is required";
    }

    if (!scheduledForm.value.period) {
        scheduledFormErrors.value.period = "Period is required";
    }

    if (!scheduledForm.value.frequency || scheduledForm.value.frequency < 1) {
        scheduledFormErrors.value.frequency = "Frequency must be at least 1";
    }

    if (scheduledForm.value.period === "minute") {
        // Minute period doesn't need time, day_of_week, or day_of_month
    } else if (scheduledForm.value.period === "daily") {
        if (!scheduledForm.value.time) {
            scheduledFormErrors.value.time = "Time is required for daily period";
        } else {
            const timeRegex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/;
            if (!timeRegex.test(scheduledForm.value.time)) {
                scheduledFormErrors.value.time = "Time must be in HH:MM format (24-hour)";
            }
        }
    } else if (scheduledForm.value.period === "weekly") {
        if (!scheduledForm.value.time) {
            scheduledFormErrors.value.time = "Time is required for weekly period";
        } else {
            const timeRegex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/;
            if (!timeRegex.test(scheduledForm.value.time)) {
                scheduledFormErrors.value.time = "Time must be in HH:MM format (24-hour)";
            }
        }
        if (scheduledForm.value.day_of_week === null) {
            scheduledFormErrors.value.day_of_week = "Day of week is required for weekly period";
        }
    } else if (scheduledForm.value.period === "monthly") {
        if (!scheduledForm.value.time) {
            scheduledFormErrors.value.time = "Time is required for monthly period";
        } else {
            const timeRegex = /^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$/;
            if (!timeRegex.test(scheduledForm.value.time)) {
                scheduledFormErrors.value.time = "Time must be in HH:MM format (24-hour)";
            }
        }
        if (scheduledForm.value.day_of_month === null) {
            scheduledFormErrors.value.day_of_month = "Day of month is required for monthly period";
        } else if (scheduledForm.value.day_of_month < 1 || scheduledForm.value.day_of_month > 31) {
            scheduledFormErrors.value.day_of_month = "Day of month must be between 1 and 31";
        }
    }

    if (!scheduledForm.value.timezone) {
        scheduledFormErrors.value.timezone = "Timezone is required";
    }

    return Object.keys(scheduledFormErrors.value).length === 0;
}

async function saveScheduledExport() {
    if (!validateScheduledForm()) {
        return;
    }

    savingScheduled.value = true;
    try {
        const data = {
            name: scheduledForm.value.name,
            period: scheduledForm.value.period,
            frequency: scheduledForm.value.frequency || 1,
            time: scheduledForm.value.time,
            day_of_week: scheduledForm.value.day_of_week,
            day_of_month: scheduledForm.value.day_of_month,
            timezone: scheduledForm.value.timezone,
            enabled: scheduledForm.value.enabled,
        };

        if (editingScheduled.value) {
            await updateScheduledExport(editingScheduled.value.id, data);
            toast.add({
                severity: "success",
                summary: "Scheduled Export Updated",
                detail: "Scheduled export has been updated successfully",
                life: 3000,
            });
        } else {
            await createScheduledExport(data);
            toast.add({
                severity: "success",
                summary: "Scheduled Export Created",
                detail: "Scheduled export has been created successfully",
                life: 3000,
            });
        }

        showCreateDialog.value = false;
        await loadScheduledExports();
        await loadSchedulerStatus();
    } catch (error) {
        console.error("Error saving scheduled export:", error);
        toast.add({
            severity: "error",
            summary: "Error",
            detail: error.message || "Failed to save scheduled export",
            life: 5000,
        });
    } finally {
        savingScheduled.value = false;
    }
}

function confirmDeleteScheduled(scheduled) {
    confirm.require({
        message: `Are you sure you want to delete the scheduled export "${scheduled.name}"? This will permanently remove the schedule and stop all future automated exports.`,
        header: "Delete Scheduled Export",
        icon: "pi pi-exclamation-triangle",
        rejectClass: "p-button-secondary p-button-outlined",
        rejectLabel: "Cancel",
        acceptLabel: "Delete",
        accept: async () => {
            await handleDeleteScheduled(scheduled.id);
        },
    });
}

async function handleDeleteScheduled(id) {
    try {
        await deleteScheduledExport(id);
        toast.add({
            severity: "success",
            summary: "Scheduled Export Deleted",
            detail: "Scheduled export has been deleted",
            life: 3000,
        });
        await loadScheduledExports();
        await loadSchedulerStatus();
    } catch (error) {
        console.error("Delete error:", error);
        toast.add({
            severity: "error",
            summary: "Delete Failed",
            detail: error.message || "Failed to delete scheduled export",
            life: 4000,
        });
    }
}

onMounted(async () => {
    await loadJobs();
    await loadScheduledExports();
    await loadSchedulerStatus();
    refreshInterval = setInterval(loadJobs, 2000);
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

.tiktok-logo-text {
    font-size: 2rem;
    font-weight: 700;
    color: var(--text-color);
}

.upload-card,
.jobs-card {
    margin-bottom: 2rem;
    border-radius: 12px;
    border: 1px solid var(--surface-border);
}

.card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
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

.google-sheets-link-card {
    margin-bottom: 2rem;
    border-radius: 12px;
    border: 1px solid var(--surface-border);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.google-sheets-link-content {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
}

.google-sheets-icon {
    width: 2rem;
    height: 2rem;
    object-fit: contain;
}

.google-sheets-link-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}

.google-sheets-link-label {
    font-weight: 600;
    color: var(--text-color);
    font-size: 1rem;
}

.google-sheets-link-desc {
    font-size: 0.85rem;
    color: var(--text-color-secondary);
}

.scheduler-card {
    margin-bottom: 2rem;
}

.scheduler-status-section {
    margin-top: 1.5rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--surface-border);
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

.scheduled-exports-list {
    padding: 1.5rem;
}

.empty-scheduled {
    text-align: center;
    padding: 3rem 1rem;
    color: var(--text-color-secondary);
}

.empty-scheduled i {
    font-size: 3rem;
    margin-bottom: 1rem;
    opacity: 0.5;
}

.empty-scheduled p {
    margin: 0.5rem 0;
}

.scheduled-item {
    border: 1px solid var(--surface-border);
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 1rem;
    background: var(--surface-0);
    transition: all 0.2s;
}

.scheduled-item:hover {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.scheduled-item:last-child {
    margin-bottom: 0;
}

.scheduled-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
}

.scheduled-info {
    flex: 1;
    min-width: 0;
}

.scheduled-name {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 600;
    color: var(--text-color);
    font-size: 1rem;
    margin-bottom: 0.5rem;
}

.scheduled-name i {
    color: var(--primary-color);
}

.scheduled-details {
    display: flex;
    align-items: center;
    gap: 1rem;
    font-size: 0.85rem;
    flex-wrap: wrap;
}

.scheduled-schedule {
    color: var(--text-color-secondary);
}

.period-tag,
.status-tag {
    font-size: 0.75rem;
}

.scheduled-actions {
    display: flex;
    gap: 0.5rem;
    flex-shrink: 0;
}

.form-field {
    margin-bottom: 1.5rem;
}

.form-field label {
    display: block;
    margin-bottom: 0.5rem;
    font-weight: 500;
    color: var(--text-color);
}

.form-field small {
    display: block;
    margin-top: 0.25rem;
}

.export-options {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    margin: 1.5rem 0;
    padding: 1rem;
    background: var(--surface-50);
    border-radius: 8px;
}

.export-option-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.export-option-item label {
    font-weight: 500;
    color: var(--text-color);
    cursor: pointer;
    user-select: none;
}

.export-warning {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem;
    background: var(--orange-50);
    border: 1px solid var(--orange-200);
    border-radius: 8px;
    color: var(--orange-700);
    font-size: 0.9rem;
    margin-bottom: 1rem;
}

.export-warning i {
    font-size: 1.1rem;
}
</style>

