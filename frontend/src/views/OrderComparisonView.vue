<template>
    <div class="service-container">
        <ConfirmDialog />
        <div class="service-page-header">
            <h1 class="service-page-title">Order Comparison Tool</h1>
            <p class="service-page-subtitle">
                Compare Complyt invoice reports with WooCommerce orders and refunds
            </p>
        </div>

        <!-- Upload Section -->
        <Card class="upload-card">
            <template #header>
                <div class="card-header">
                    <i class="pi pi-upload"></i>
                    <h3>Upload Complyt CSV File</h3>
                </div>
            </template>
            <template #content>
                <form class="upload-section" @submit.prevent="handleUpload">
                    <div class="file-upload-area" @click="fileInput?.click()" @dragover.prevent @drop.prevent="handleDrop">
                        <input
                            ref="fileInput"
                            type="file"
                            accept=".csv"
                            @change="handleFileSelect"
                            class="file-input"
                        />
                        <div v-if="!selectedFile" class="upload-placeholder">
                            <i class="pi pi-cloud-upload"></i>
                            <p class="upload-text">Click to upload or drag and drop</p>
                            <p class="upload-hint">CSV files only</p>
                        </div>
                        <div v-else class="file-selected">
                            <i class="pi pi-file"></i>
                            <div class="file-info">
                                <span class="file-name">{{ selectedFile.name }}</span>
                                <span class="file-size">{{ formatFileSize(selectedFile.size) }}</span>
                            </div>
                            <Button
                                icon="pi pi-times"
                                severity="secondary"
                                text
                                rounded
                                @click.stop="selectedFile = null"
                            />
                        </div>
                    </div>

                    <div class="upload-options">
                        <div class="option-group">
                            <label for="order-id-header" class="option-label">
                                Order ID Column Header
                            </label>
                            <InputText
                                id="order-id-header"
                                v-model="orderIdHeader"
                                placeholder="e.g., externalId"
                                class="w-full"
                            />
                        </div>

                        <div class="option-group">
                            <label for="date-range" class="option-label">
                                Date Range
                            </label>
                            <Calendar
                                id="date-range"
                                v-model="dateRange"
                                selectionMode="range"
                                dateFormat="yy-mm-dd"
                                showIcon
                                class="w-full"
                                :maxDate="new Date()"
                                placeholder="Select date range"
                            />
                        </div>
                    </div>

                    <Button
                        label="Process Comparison"
                        icon="pi pi-play"
                        class="process-button"
                        :disabled="!selectedFile || !orderIdHeader || !dateRange || !Array.isArray(dateRange) || dateRange.length !== 2 || processing"
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
                    <h3>Comparison Jobs</h3>
                </div>
            </template>
            <template #content>
                <div class="jobs-list">
                    <div v-if="jobs.length === 0" class="empty-jobs">
                        <i class="pi pi-inbox"></i>
                        <p>No jobs yet</p>
                        <p class="text-sm text-color-secondary">
                            Upload a file to start comparison
                        </p>
                    </div>
                    <div
                        v-for="job in jobs"
                        :key="job.id"
                        class="job-item"
                    >
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
                                        {{ job.options?.original_filename || getFileName(job.status === 'done' && job.output_filename ? job.output_filename : job.input_filename) }}
                                    </div>
                                    <div class="job-meta">
                                        <span class="status-badge" :class="`status-${job.status}`">
                                            {{ job.status }}
                                        </span>
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
                                    :aria-label="'Download report'"
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
import { ref, onMounted, onUnmounted } from "vue";
import { useToast } from "primevue/usetoast";
import { useConfirm } from "primevue/useconfirm";
import Card from "primevue/card";
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Calendar from "primevue/calendar";
import ProgressBar from "primevue/progressbar";
import ConfirmDialog from "primevue/confirmdialog";
import { uploadComparison, listJobs, downloadJob, deleteJob } from "../api/orderComparisonApi";

const toast = useToast();
const confirm = useConfirm();
const fileInput = ref(null);
const selectedFile = ref(null);
const orderIdHeader = ref("externalId");
const dateRange = ref(null);
const processing = ref(false);
const jobs = ref([]);
let refreshInterval = null;

function handleFileSelect(event) {
    const file = event.target.files?.[0];
    if (file) {
        if (!file.name.endsWith(".csv")) {
            toast.add({
                severity: "error",
                summary: "Invalid File",
                detail: "Please upload a CSV file",
                life: 3000,
            });
            return;
        }
        selectedFile.value = file;
    }
}

function handleDrop(event) {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file && file.name.endsWith(".csv")) {
        selectedFile.value = file;
    } else {
        toast.add({
            severity: "error",
            summary: "Invalid File",
            detail: "Please drop a CSV file",
            life: 3000,
        });
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + " " + sizes[i];
}

async function handleUpload() {
    if (!selectedFile.value || !orderIdHeader.value || !dateRange.value || !Array.isArray(dateRange.value) || dateRange.value.length !== 2) {
        toast.add({
            severity: "error",
            summary: "Validation Error",
            detail: "Please select a valid date range",
            life: 3000,
        });
        return;
    }

    processing.value = true;
    try {
        const [dateFrom, dateTo] = dateRange.value;
        const result = await uploadComparison(
            selectedFile.value,
            orderIdHeader.value,
            dateFrom,
            dateTo
        );
        toast.add({
            severity: "success",
            summary: "File Uploaded",
            detail: "Comparison has started",
            life: 3000,
        });
        selectedFile.value = null;
        orderIdHeader.value = "externalId";
        dateRange.value = null;
        if (fileInput.value) {
            fileInput.value.value = "";
        }
        await loadJobs();
    } catch (error) {
        toast.add({
            severity: "error",
            summary: "Upload Failed",
            detail: error.message || "Failed to upload file",
            life: 4000,
        });
    } finally {
        processing.value = false;
    }
}

async function loadJobs() {
    try {
        jobs.value = await listJobs();
    } catch (error) {
        console.error("Failed to load jobs:", error);
    }
}

function getFileName(path) {
    if (!path) return "Unknown";
    return path.split("/").pop() || path.split("\\").pop() || path;
}

function formatDate(dateString) {
    if (!dateString) return "N/A";
    const date = new Date(dateString);
    return date.toLocaleString();
}

function getProgress(job) {
    if (job.status === "done") return 100;
    if (job.status === "error") return 0;
    if (job.status === "running" || job.status === "pending") {
        if (job.options) {
            let progressValue = job.options.progress;
            if (typeof progressValue === "string") {
                progressValue = parseFloat(progressValue);
            }
            if (typeof progressValue === "number" && !isNaN(progressValue)) {
                return Math.max(0, Math.min(100, progressValue));
            }
        }
        return job.status === "pending" ? 5 : 10;
    }
    return 0;
}

function getProgressText(job) {
    if (job.status === "done") return "Completed";
    if (job.status === "error") return "Failed";
    if (job.status === "running" || job.status === "pending") {
        if (job.options && job.options.status_message) {
            const percent = job.options.progress || 0;
            return `${job.options.status_message} (${percent}%)`;
        }
        return job.status === "running" ? "Processing..." : "Queued...";
    }
    return "Unknown";
}

async function handleDownload(jobId) {
    try {
        const result = await downloadJob(jobId);
        const blob = result.blob;
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;

        // Use filename from response header if available, otherwise determine from content type
        let downloadFilename;
        if (result.filename) {
            downloadFilename = result.filename;
            console.log('Using filename from header:', downloadFilename);
        } else {
            // Determine file extension from content type
            const contentType = result.contentType || blob.type || '';
            console.log('Content-Type:', contentType, 'Blob type:', blob.type);
            const extension = contentType.includes('application/pdf') ? '.pdf' : '.txt';
            downloadFilename = `comparison_report_${jobId}${extension}`;
            console.log('Generated filename:', downloadFilename);
        }

        a.download = downloadFilename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        toast.add({
            severity: "success",
            summary: "Download Started",
            detail: "Report download has started",
            life: 3000,
        });
    } catch (error) {
        toast.add({
            severity: "error",
            summary: "Download Failed",
            detail: error.message || "Failed to download report",
            life: 4000,
        });
    }
}

function confirmDelete(job) {
    const isActive = job.status === "pending" || job.status === "running";
    const message = isActive
        ? `Are you sure you want to delete this job? This will stop the processing and permanently delete the job and all associated files (${job.options?.original_filename || getFileName(job.input_filename)}).`
        : `Are you sure you want to delete this job? This will permanently delete the job and all associated files (${job.options?.original_filename || getFileName(job.input_filename)}).`;

    confirm.require({
        message: message,
        header: isActive ? "Stop and Delete Job" : "Delete Job",
        icon: "pi pi-exclamation-triangle",
        rejectClass: "p-button-secondary p-button-outlined",
        rejectLabel: "Cancel",
        acceptLabel: isActive ? "Stop & Delete" : "Delete",
        accept: () => {
            handleDelete(job.id);
        },
    });
}

async function handleDelete(jobId) {
    try {
        await deleteJob(jobId);
        toast.add({
            severity: "success",
            summary: "Job Deleted",
            detail: "Job and associated files have been deleted",
            life: 3000,
        });
        await loadJobs();
    } catch (error) {
        toast.add({
            severity: "error",
            summary: "Delete Failed",
            detail: error.message || "Failed to delete job",
            life: 4000,
        });
    }
}

onMounted(async () => {
    await loadJobs();
    refreshInterval = setInterval(loadJobs, 2000);
});

onUnmounted(() => {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
});
</script>

<style scoped>
.order-comparison-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
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

.file-upload-area {
    border: 2px dashed #dee2e6;
    border-radius: 12px;
    padding: 1.5rem 1rem;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
    background: var(--surface-50);
    position: relative;
}

.file-upload-area:hover {
    border-color: var(--primary-color);
    background: var(--surface-100);
}

.file-input {
    position: absolute;
    opacity: 0;
    width: 0;
    height: 0;
}

.upload-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
}

.upload-placeholder i {
    font-size: 3rem;
    color: var(--text-color-secondary);
    opacity: 0.5;
}

.upload-text {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--text-color);
    margin: 0;
}

.upload-hint {
    font-size: 0.9rem;
    color: var(--text-color-secondary);
    margin: 0;
}

.file-selected {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
    background: var(--surface-0);
    border-radius: 8px;
    border: 1px solid var(--surface-border);
}

.file-selected i {
    font-size: 2rem;
    color: var(--primary-color);
}

.file-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}

.file-name {
    font-weight: 600;
    color: var(--text-color);
}

.file-size {
    font-size: 0.85rem;
    color: var(--text-color-secondary);
}

.upload-options {
    margin-top: 2rem;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
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

.status-pending,
.status-running {
    background: var(--orange-100);
    color: var(--orange-700);
}

.job-date {
    color: var(--text-color-secondary);
}

.job-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.job-progress {
    margin-top: 1rem;
    display: flex;
    align-items: center;
    gap: 1rem;
}

.progress-bar {
    flex: 1;
    height: 8px;
}

.progress-text {
    font-size: 0.85rem;
    color: var(--text-color-secondary);
    font-weight: 500;
    min-width: 100px;
    text-align: right;
}

.job-error {
    margin-top: 1rem;
    padding: 0.75rem;
    background: var(--red-50);
    border: 1px solid var(--red-200);
    border-radius: 8px;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--red-700);
    font-size: 0.9rem;
}

.job-error i {
    font-size: 1rem;
    flex-shrink: 0;
}

@media (max-width: 768px) {
    .order-comparison-container {
        padding: 1rem;
    }

    .page-title {
        font-size: 1.75rem;
    }

    .card-header {
        padding: 1.25rem;
    }

    .upload-section {
        padding: 1.25rem;
    }

    .file-upload-area {
        padding: 2rem 1rem;
    }

    .job-header {
        flex-direction: column;
        align-items: flex-start;
    }

    .job-meta {
        flex-direction: column;
        align-items: flex-start;
        gap: 0.5rem;
    }
}
</style>

