/* Javascript UI Control Logic: index.js */

document.addEventListener("DOMContentLoaded", () => {
    // Upload & Staging Elements
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("file-input");
    const uploadFilesList = document.getElementById("upload-files-list");
    const btnSimulate = document.getElementById("btn-simulate");

    // Ingestion execution state
    let stagedFiles = [];
    let activeFileIndex = -1;
    let currentResult = null; // Cache the current simulation run results

    // Operational Control Elements
    const btnRefreshLogs = document.getElementById("btn-refresh-logs");
    const btnExportLogs = document.getElementById("btn-export-logs");
    const btnExportUnder50k = document.getElementById("btn-export-under-50k");

    // Human Override Panel Elements
    const humanOverridePanel = document.getElementById("human-override-panel");
    const overrideViewMode = document.getElementById("override-view-mode");
    const overrideEditMode = document.getElementById("override-edit-mode");
    const overrideStatusBadge = document.getElementById("override-status-badge");
    const btnAdjustFields = document.getElementById("btn-adjust-fields");
    const btnCancelEdit = document.getElementById("btn-cancel-edit");
    const btnConfirmOverride = document.getElementById("btn-confirm-override");
    const editVendor = document.getElementById("edit-vendor");
    const editInvnumber = document.getElementById("edit-invnumber");
    const editTotal = document.getElementById("edit-total");
    const editDoctype = document.getElementById("edit-doctype");
    const editStatus = document.getElementById("edit-status");
    const editRouting = document.getElementById("edit-routing");
    const overrideWarning = document.getElementById("override-warning");

    // Timeline steps
    const steps = {
        ingest: document.getElementById("step-ingested"),
        parsing: document.getElementById("step-parsing"),
        extracting: document.getElementById("step-extracting"),
        routing: document.getElementById("step-routing"),
        notifying: document.getElementById("step-notifying")
    };

    // Results Display Elements
    const simDisplay = document.getElementById("sim-display");
    const displayPlaceholder = document.getElementById("display-placeholder");
    const displayResults = document.getElementById("display-results");
    const resFilename = document.getElementById("result-filename");
    const resDoctypeBadge = document.getElementById("result-doctype-badge");
    const resConfidence = document.getElementById("result-confidence");
    const resVendor = document.getElementById("result-vendor");
    const resInvnumber = document.getElementById("result-invnumber");
    const resDate = document.getElementById("result-date");
    const resTotal = document.getElementById("result-total");
    const resReasoning = document.getElementById("result-reasoning");

    // Previews
    const previewSlack = document.getElementById("preview-slack");
    const slackVendor = document.getElementById("slack-vendor");
    const slackInv = document.getElementById("slack-inv");
    const slackTotal = document.getElementById("slack-total");
    const slackDate = document.getElementById("slack-date");
    const slackReason = document.getElementById("slack-reason");

    const previewEmail = document.getElementById("preview-email");
    const emailTo = document.getElementById("email-to");
    const emailSubject = document.getElementById("email-subject");
    const emailBody = document.getElementById("email-body");

    // Stats
    const statTotal = document.getElementById("stat-total");
    const statSuccessRate = document.getElementById("stat-success-rate");
    const statSlack = document.getElementById("stat-slack");
    const statCsv = document.getElementById("stat-csv");
    const statReview = document.getElementById("stat-review");

    // Logs Table
    const logsTableBody = document.getElementById("logs-table-body");

    // Modal
    const detailsModal = document.getElementById("details-modal");
    const jsonViewer = document.getElementById("json-viewer");
    const btnCloseModal = document.getElementById("btn-close-modal");
    const modalCloseBackdrop = document.getElementById("modal-close-backdrop");

    // API URL Base (relative)
    const API_BASE = "";

    // Load Initial Data
    loadDashboardLogs();

    // --- Drag & Drop File Upload Events ---
    dropzone.addEventListener("click", () => {
        fileInput.click();
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleMultipleFiles(e.target.files);
        }
    });

    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("drag-over");
    });

    dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("drag-over");
    });

    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("drag-over");
        if (e.dataTransfer.files.length > 0) {
            handleMultipleFiles(e.dataTransfer.files);
        }
    });

    // Handle multiple selected/dropped files
    function handleMultipleFiles(files) {
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            
            // Check if file is already staged
            if (stagedFiles.some(f => f.name === file.name)) {
                showToast(`File ${file.name} is already staged.`, false);
                continue;
            }
            
            const fileEntry = {
                file: file,
                name: file.name,
                size: file.size,
                uploadedName: null,
                status: "uploading",
                result: null,
                error: null
            };
            
            stagedFiles.push(fileEntry);
            const index = stagedFiles.length - 1;
            
            // Start upload immediately
            uploadStagedFile(fileEntry, index);
        }
        
        // Render the list
        renderStagedFilesList();
        
        // Select the newly added file as active
        if (stagedFiles.length > 0) {
            selectActiveFile(stagedFiles.length - 1);
        }
    }

    // File Upload API Post Dispatch
    async function uploadStagedFile(fileEntry, index) {
        const formData = new FormData();
        formData.append("file", fileEntry.file);

        try {
            const response = await fetch(`${API_BASE}/api/upload`, {
                method: "POST",
                body: formData
            });

            if (!response.ok) throw new Error("File upload failed on the server.");
            const data = await response.json();
            
            // Check if the file still exists in stagedFiles (user might have removed it during upload)
            const currentIdx = stagedFiles.indexOf(fileEntry);
            if (currentIdx !== -1) {
                fileEntry.uploadedName = data.filename;
                fileEntry.status = "staged";
                renderStagedFilesList();
                updateExecuteButtonState();
                
                // If it's the active file, update placeholder display description
                if (currentIdx === activeFileIndex) {
                    selectActiveFile(currentIdx);
                }
            }
        } catch (err) {
            console.error("Upload error for file:", fileEntry.name, err);
            const currentIdx = stagedFiles.indexOf(fileEntry);
            if (currentIdx !== -1) {
                fileEntry.status = "failed";
                fileEntry.error = err.message;
                renderStagedFilesList();
                updateExecuteButtonState();
                
                if (currentIdx === activeFileIndex) {
                    selectActiveFile(currentIdx);
                }
                showToast(`Upload failed for ${fileEntry.name}: ${err.message}`, false);
            }
        }
    }

    // Render the list of staged files in the left sidebar
    function renderStagedFilesList() {
        if (!uploadFilesList) return;
        
        if (stagedFiles.length === 0) {
            uploadFilesList.innerHTML = `
                <div style="text-align: center; color: var(--text-gray); font-style: italic; padding: 1.5rem 0; font-size: 0.85rem;">
                    No documents staged. Browse or drop files to begin.
                </div>
            `;
            return;
        }
        
        uploadFilesList.innerHTML = "";
        stagedFiles.forEach((fileEntry, index) => {
            const isProcessing = fileEntry.status === "processing";
            const isSuccess = fileEntry.status === "success";
            const isFailed = fileEntry.status === "failed";
            
            let cardClass = "uploader-file-card";
            if (isProcessing) cardClass += " processing";
            if (isSuccess) cardClass += " success";
            if (isFailed) cardClass += " failed";
            
            const badgeClass = `file-status-badge ${fileEntry.status}`;
            
            // Icon based on type
            const extension = fileEntry.name.split('.').pop().toLowerCase();
            const icon = (extension === "pdf") ? "📄" : "🖼️";
            
            const isActive = index === activeFileIndex;
            const activeStyle = isActive ? "border: 1px solid var(--clr-primary); box-shadow: 0 0 10px rgba(95, 90, 246, 0.2);" : "";
            
            const itemElement = document.createElement("div");
            itemElement.className = cardClass;
            itemElement.style = activeStyle + " cursor: pointer;";
            
            itemElement.innerHTML = `
                <div class="file-card-info">
                    <div style="font-size: 1.5rem;">${icon}</div>
                    <div class="file-card-meta">
                        <span class="file-card-name" title="${fileEntry.name}">${fileEntry.name}</span>
                        <span class="file-card-size">${formatBytes(fileEntry.size)}</span>
                    </div>
                </div>
                <div class="file-card-right-area">
                    <span class="${badgeClass}">${fileEntry.status}</span>
                    ${!isProcessing ? `<button class="file-card-remove" data-index="${index}">&times;</button>` : ''}
                </div>
            `;
            
            // Clicking the card selects it to view in the results monitor
            itemElement.addEventListener("click", (e) => {
                if (e.target.classList.contains("file-card-remove")) return;
                selectActiveFile(index);
            });
            
            // Clicking remove button deletes it from staged list
            const removeBtn = itemElement.querySelector(".file-card-remove");
            if (removeBtn) {
                removeBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    removeStagedFile(index);
                });
            }
            
            uploadFilesList.appendChild(itemElement);
        });
    }

    // Select active file to show details on monitor
    function selectActiveFile(index) {
        if (index < 0 || index >= stagedFiles.length) return;
        activeFileIndex = index;
        renderStagedFilesList();
        
        const fileEntry = stagedFiles[index];
        if (fileEntry.result) {
            // Render the results in the right panel
            renderSimulationResults(fileEntry.result);
        } else {
            // Show placeholder or staging status, and reset steps/timeline
            displayResults.classList.add("hidden");
            displayPlaceholder.classList.remove("hidden");
            
            const placeholderTitle = displayPlaceholder.querySelector("h3");
            const placeholderDesc = displayPlaceholder.querySelector("p");
            
            if (fileEntry.status === "uploading") {
                placeholderTitle.textContent = "Uploading Document...";
                placeholderDesc.textContent = `Please wait while ${fileEntry.name} is uploaded to the server.`;
            } else if (fileEntry.status === "processing") {
                placeholderTitle.textContent = "Processing Document...";
                placeholderDesc.textContent = `AI Agent is currently parsing, extracting and routing ${fileEntry.name}.`;
            } else if (fileEntry.status === "failed") {
                placeholderTitle.textContent = "Upload/Process Failed";
                placeholderDesc.textContent = `Error: ${fileEntry.error || "Unknown processing error"}.`;
            } else {
                placeholderTitle.textContent = "Document Staged";
                placeholderDesc.textContent = `"${fileEntry.name}" is ready for execution. Click "Execute Agent Pipeline" to run.`;
            }
            
            // Reset timeline stepper in UI
            Object.values(steps).forEach(s => {
                s.classList.remove("active", "completed");
            });
        }
    }

    // Remove file from staging
    function removeStagedFile(index) {
        stagedFiles.splice(index, 1);
        if (activeFileIndex >= stagedFiles.length) {
            activeFileIndex = stagedFiles.length - 1;
        }
        renderStagedFilesList();
        updateExecuteButtonState();
        if (stagedFiles.length > 0) {
            selectActiveFile(activeFileIndex);
        } else {
            // Reset right panel to default empty state
            displayResults.classList.add("hidden");
            displayPlaceholder.classList.remove("hidden");
            const placeholderTitle = displayPlaceholder.querySelector("h3");
            const placeholderDesc = displayPlaceholder.querySelector("p");
            placeholderTitle.textContent = "Agent Monitor Sandbox";
            placeholderDesc.textContent = "Select a payload event or upload a custom invoice, then click 'Execute Agent Pipeline' to view extraction and routing outcomes.";
            
            // Reset stepper
            Object.values(steps).forEach(s => {
                s.classList.remove("active", "completed");
            });
        }
    }

    // Controls the Execute button enabling rules
    function updateExecuteButtonState() {
        const hasStaged = stagedFiles.some(f => (f.status === "staged" || f.status === "failed") && f.uploadedName);
        const isRunning = stagedFiles.some(f => f.status === "processing");
        btnSimulate.disabled = !hasStaged || isRunning;
    }

    // --- Action Listeners ---
    btnSimulate.addEventListener("click", runIngestionSimulation);
    btnRefreshLogs.addEventListener("click", loadDashboardLogs);
    btnCloseModal.addEventListener("click", closeModal);
    modalCloseBackdrop.addEventListener("click", closeModal);
    btnExportLogs.addEventListener("click", exportLogsToCSV);
    btnExportUnder50k.addEventListener("click", exportUnder50kCSV);

    btnAdjustFields.addEventListener("click", () => {
        overrideViewMode.classList.add("hidden");
        overrideEditMode.classList.remove("hidden");
    });

    btnCancelEdit.addEventListener("click", () => {
        overrideEditMode.classList.add("hidden");
        overrideViewMode.classList.remove("hidden");
    });

    btnConfirmOverride.addEventListener("click", submitManualOverride);

    // Load global routing run log and update table/stats
    async function loadDashboardLogs() {
        try {
            const response = await fetch(`${API_BASE}/api/logs`);
            if (!response.ok) throw new Error("Failed to load routing logs");
            const logs = await response.json();
            
            updateStatsBanner(logs);
            populateLogsTable(logs);
        } catch (err) {
            console.error("Error loading logs:", err);
        }
    }

    // Populate stats elements
    function updateStatsBanner(logs) {
        const total = logs.length;
        if (total === 0) {
            statTotal.textContent = "0";
            statSuccessRate.textContent = "0%";
            statSlack.textContent = "0";
            statCsv.textContent = "0";
            statReview.textContent = "0";
            return;
        }

        const successes = logs.filter(l => l.status === "success").length;
        const rate = Math.round((successes / total) * 100);
        const slack = logs.filter(l => l.routed_to === "slack_notification").length;
        const csv = logs.filter(l => l.routed_to === "processed_invoices_csv").length;
        const review = logs.filter(l => l.routed_to === "human_review_log" || l.status === "failed" || l.document_type === "unknown").length;

        statTotal.textContent = total;
        statSuccessRate.textContent = `${rate}%`;
        statSlack.textContent = slack;
        statCsv.textContent = csv;
        statReview.textContent = review;
    }

    // Render log grid row elements
    function populateLogsTable(logs) {
        if (logs.length === 0) {
            logsTableBody.innerHTML = `
                <tr>
                    <td colspan="7" class="table-empty">No records found. Click 'Execute Agent Pipeline' above or run the pipeline to populate.</td>
                </tr>
            `;
            return;
        }

        logsTableBody.innerHTML = "";
        
        // Reverse array to show latest runs first
        const reverseLogs = [...logs].reverse();
        
        reverseLogs.forEach(log => {
            const tr = document.createElement("tr");
            
            const totalStr = log.total_amount !== null ? `Rs. ${log.total_amount.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : "-";
            const docBadge = `<span class="doc-badge ${log.document_type}">${log.document_type.replace('_', ' ')}</span>`;
            const statusClass = `status-${log.status}`;
            const routedToClean = log.routed_to ? log.routed_to.replace(/_/g, ' ') : "unknown";
            
            tr.innerHTML = `
                <td><code>${log.event_id}</code></td>
                <td><strong>${log.filename}</strong></td>
                <td>${docBadge}</td>
                <td><strong>${totalStr}</strong></td>
                <td><span class="${statusClass}">${log.status.toUpperCase()}</span></td>
                <td><code>${routedToClean}</code></td>
                <td style="white-space: nowrap;">
                    <button class="btn-refresh btn-review-log" data-file="${log.filename}" style="margin-right: 0.4rem; background: rgba(95, 90, 246, 0.08); border-color: rgba(95, 90, 246, 0.25); color: var(--clr-primary-light);">Review 🧑‍✈️</button>
                    <button class="btn-refresh btn-view-json" data-file="${log.filename}">JSON</button>
                </td>
            `;
            
            tr.querySelector(".btn-review-log").addEventListener("click", () => {
                loadLogForReview(log.filename);
            });

            tr.querySelector(".btn-view-json").addEventListener("click", () => {
                showExtractionJSON(log.filename);
            });
            
            logsTableBody.appendChild(tr);
        });
    }

    // Load a historic log document into staging and open it in Results Monitor for Human Intervention
    async function loadLogForReview(filename) {
        showToast(`Loading review data for ${filename}...`, true);
        try {
            const response = await fetch(`${API_BASE}/api/review/${encodeURIComponent(filename)}`);
            if (!response.ok) throw new Error("Failed to load review data");
            const data = await response.json();
            
            // Check if this file is in our stagedFiles list
            let fileIndex = stagedFiles.findIndex(f => f.uploadedName === filename);
            if (fileIndex === -1) {
                // Add to stagedFiles list as a mock staged file
                stagedFiles.push({
                    file: null,
                    name: filename,
                    size: 0,
                    uploadedName: filename,
                    status: "success",
                    result: data,
                    error: null
                });
                fileIndex = stagedFiles.length - 1;
            } else {
                // If it is in stagedFiles, update its result cache
                stagedFiles[fileIndex].result = data;
                stagedFiles[fileIndex].status = "success";
            }
            
            // Render list and select this active file
            renderStagedFilesList();
            selectActiveFile(fileIndex);
            
            // Highlight Results Monitor
            const simDisplay = document.getElementById("sim-display");
            simDisplay.scrollIntoView({ behavior: "smooth", block: "center" });
            
            showToast(`Loaded details for ${filename}! Ready for review.`, true);
        } catch (err) {
            console.error("Error loading review:", err);
            showToast(`Review load failed: ${err.message}`, false);
        }
    }

    // Modal popup helper
    async function showExtractionJSON(filename) {
        jsonViewer.textContent = "Loading JSON schema output...";
        detailsModal.classList.remove("hidden");
        
        try {
            const response = await fetch(`${API_BASE}/api/extraction/${encodeURIComponent(filename)}`);
            if (!response.ok) throw new Error("JSON file not found for this extraction");
            const data = await response.json();
            
            jsonViewer.textContent = JSON.stringify(data, null, 2);
        } catch (err) {
            jsonViewer.textContent = `Error: ${err.message}\nThis document may have failed parsing and did not generate structured JSON. Check human_review.log.`;
        }
    }

    function closeModal() {
        detailsModal.classList.add("hidden");
    }

    // Helper functions for timeline animation delays
    const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

    // Batch sequential execution of all staged files
    async function runIngestionSimulation() {
        btnSimulate.disabled = true;
        
        // Temporarily disable delete buttons during execution
        const removeBtns = uploadFilesList.querySelectorAll(".file-card-remove");
        removeBtns.forEach(btn => btn.style.display = "none");
        
        // Find files that are ready to be processed
        const filesToProcess = stagedFiles.filter(f => (f.status === "staged" || f.status === "failed") && f.uploadedName);
        if (filesToProcess.length === 0) {
            updateExecuteButtonState();
            return;
        }

        for (let fileEntry of filesToProcess) {
            const idx = stagedFiles.indexOf(fileEntry);
            if (idx === -1) continue;
            
            // Set active file
            selectActiveFile(idx);
            
            // Set status to processing
            fileEntry.status = "processing";
            renderStagedFilesList();
            
            // Reset timeline steps
            Object.values(steps).forEach(s => {
                s.classList.remove("active", "completed");
            });

            try {
                // Step 1: Ingest Email
                steps.ingest.classList.add("active");
                await delay(200);
                steps.ingest.classList.remove("active");
                steps.ingest.classList.add("completed");

                // Step 2: OCR & PDF Parsing
                steps.parsing.classList.add("active");
                await delay(250);
                steps.parsing.classList.remove("active");
                steps.parsing.classList.add("completed");

                // Step 3: Gemini AI Field Extraction
                steps.extracting.classList.add("active");
                
                // Dispatch API process call
                const response = await fetch(`${API_BASE}/api/process`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ filename: fileEntry.uploadedName })
                });

                if (!response.ok) throw new Error("AI agent extraction failed on the server.");
                const responseData = await response.json();

                steps.extracting.classList.remove("active");
                steps.extracting.classList.add("completed");

                // Step 4: Applying Routing Rules
                steps.routing.classList.add("active");
                await delay(200);
                steps.routing.classList.remove("active");
                steps.routing.classList.add("completed");

                // Step 5: Executing Integrations
                steps.notifying.classList.add("active");
                await delay(200);
                steps.notifying.classList.remove("active");
                steps.notifying.classList.add("completed");

                // Success! Save results
                fileEntry.status = "success";
                fileEntry.result = responseData;
                
                // Refresh Logs and update Monitor
                selectActiveFile(idx);
                await loadDashboardLogs();
                
                showToast(`Successfully processed document ${fileEntry.name}!`, true);
                highlightLogRow(fileEntry.uploadedName);

            } catch (err) {
                console.error("Simulation run error for", fileEntry.name, err);
                fileEntry.status = "failed";
                fileEntry.error = err.message;
                
                // Refresh list and select file to show failure context
                renderStagedFilesList();
                selectActiveFile(idx);
                showToast(`Simulation Failed for ${fileEntry.name}: ${err.message}`, false);
            }
        }
        
        // Restore delete buttons
        renderStagedFilesList();
        updateExecuteButtonState();
    }

    // Populate visual previews (Slack block & Email content)
    function renderSimulationResults(data) {
        currentResult = data; // Cache the current result data for override adjustments
        const ext = data.extraction;
        const outcome = data.outcome;
        const ev = data.event;

        displayPlaceholder.classList.add("hidden");
        displayResults.classList.remove("hidden");

        // Header Status
        resFilename.textContent = outcome.filename;
        resDoctypeBadge.textContent = ext.document_type.replace('_', ' ');
        resDoctypeBadge.className = `doc-badge ${ext.document_type}`;
        
        const confidence = ext.confidence_score !== undefined ? ext.confidence_score : 1.0;
        resConfidence.textContent = `${Math.round(confidence * 100)}%`;
        
        // Extracted Fields Grid
        resVendor.textContent = ext.vendor_name || "N/A";
        resInvnumber.textContent = ext.invoice_number || "N/A";
        resDate.textContent = ext.date || "N/A";
        
        const totalAmountNum = ext.total_amount;
        resTotal.textContent = totalAmountNum !== null ? `Rs. ${totalAmountNum.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : "N/A";
        resReasoning.textContent = ext.reasoning || "None provided.";

        // Pre-fill the human intervention fields
        editVendor.value = ext.vendor_name || "";
        editInvnumber.value = ext.invoice_number || "";
        editTotal.value = ext.total_amount !== null ? ext.total_amount : "";
        editDoctype.value = ext.document_type || "standard_invoice";
        editStatus.value = outcome.status || "success";
        
        // Handle dropdown select value mapping for manual routing override
        let mappedRoute = "auto";
        if (outcome.routed_to === "slack_notification") mappedRoute = "slack";
        else if (outcome.routed_to === "processed_invoices_csv") mappedRoute = "csv";
        else if (outcome.routed_to === "human_review_log") mappedRoute = "human";
        editRouting.value = mappedRoute;

        // Trigger warning & styling pulse if AI confidence score is low (<80%) or document is unclassified
        const isLowConfidence = confidence < 0.8 || ext.document_type === "unknown";
        if (isLowConfidence) {
            overrideWarning.classList.remove("hidden");
            humanOverridePanel.classList.add("attention-pulse");
        } else {
            overrideWarning.classList.add("hidden");
            humanOverridePanel.classList.remove("attention-pulse");
        }

        // Initialize override status badge
        if (ext.reasoning && ext.reasoning.includes("Manually verified")) {
            overrideStatusBadge.textContent = "Human Approved";
            overrideStatusBadge.style.color = "var(--state-success)";
            overrideStatusBadge.style.borderColor = "rgba(16, 185, 129, 0.2)";
            overrideStatusBadge.style.backgroundColor = "rgba(16, 185, 129, 0.1)";
        } else {
            overrideStatusBadge.textContent = "AI Suggested";
            overrideStatusBadge.style.color = "var(--clr-primary)";
            overrideStatusBadge.style.borderColor = "rgba(95, 90, 246, 0.2)";
            overrideStatusBadge.style.backgroundColor = "rgba(95, 90, 246, 0.1)";
        }

        overrideViewMode.classList.remove("hidden");
        overrideEditMode.classList.add("hidden");

        // Render Slack/Email previews
        renderPreviews(ext, outcome, ev);
    }

    function renderPreviews(ext, outcome, ev) {
        const totalAmountNum = ext.total_amount;
        const eventData = ev || { from: "manual_review@acme.com" };
        
        // Slack Card logic
        if (outcome.routed_to === "slack_notification") {
            previewSlack.classList.remove("hidden");
            
            slackVendor.textContent = ext.vendor_name || "N/A";
            slackInv.textContent = ext.invoice_number || "N/A";
            slackTotal.textContent = totalAmountNum !== null ? `Rs. ${totalAmountNum.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : "N/A";
            slackDate.textContent = ext.date || "N/A";
            slackReason.textContent = ext.reasoning || "";
        } else {
            previewSlack.classList.add("hidden");
        }

        // Email Preview logic
        emailTo.textContent = eventData.from || "onboarding@resend.dev";
        
        const emailStatusText = outcome.status === "failed" ? "FAILED" : (outcome.status === "partial" ? "PARTIAL" : "SUCCESS");
        emailSubject.textContent = `Acknowledgement: Invoice Processing Status [${emailStatusText}]`;

        // Render mock email body content
        const cleanDate = ext.date || "N/A";
        const cleanVendor = ext.vendor_name || "Unknown Vendor";
        const cleanInv = ext.invoice_number || "N/A";
        const cleanTotal = totalAmountNum !== null ? `Rs. ${totalAmountNum.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : "N/A";
        
        let statusColor = "#38a169"; // green
        if (emailStatusText === "PARTIAL") statusColor = "#dd6b20"; // orange
        if (emailStatusText === "FAILED") statusColor = "#e53e3e"; // red

        emailBody.innerHTML = `
            <p>Dear Valued Vendor Team,</p>
            <p>This is an automated notification regarding the invoice/document received from your address.</p>
            <table style="width: 100%; font-size: 0.8rem; margin: 10px 0; border-collapse: collapse;">
                <tr style="background:#f7fafc;"><td style="padding:4px; font-weight:bold; width:120px;">Vendor Name</td><td>${cleanVendor}</td></tr>
                <tr><td style="padding:4px; font-weight:bold;">Invoice Number</td><td>${cleanInv}</td></tr>
                <tr style="background:#f7fafc;"><td style="padding:4px; font-weight:bold;">Date</td><td>${cleanDate}</td></tr>
                <tr><td style="padding:4px; font-weight:bold;">Total Amount</td><td>${cleanTotal}</td></tr>
                <tr style="background:#f7fafc;"><td style="padding:4px; font-weight:bold;">Status</td><td style="color:${statusColor}; font-weight:bold;">${emailStatusText}</td></tr>
            </table>
            <p style="font-size:0.75rem; color:#718096; margin-top:10px;">${ext.reasoning}</p>
            <hr style="border:0; border-top:1px solid #e2e8f0; margin:10px 0;" />
            <p style="font-size:0.7rem; color:#a0aec0; text-align:center;">This is an automated operational response.</p>
        `;
    }

    // Submit manual override routing data
    async function submitManualOverride() {
        if (!currentResult) return;
        
        const filename = currentResult.outcome.filename;
        const vendor = editVendor.value.trim();
        const invnumber = editInvnumber.value.trim();
        const total = parseFloat(editTotal.value);
        const doctype = editDoctype.value;
        const status = editStatus.value;
        const routeTo = editRouting.value;
        
        if (!vendor) {
            alert("Vendor Name is required.");
            return;
        }
        if (isNaN(total) || total < 0) {
            alert("Please enter a valid non-negative Total Amount.");
            return;
        }

        btnConfirmOverride.disabled = true;
        btnConfirmOverride.textContent = "Routing... 🚀";
        
        try {
            const response = await fetch(`${API_BASE}/api/manual_route`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    filename: filename,
                    vendor_name: vendor,
                    invoice_number: invnumber,
                    total_amount: total,
                    document_type: doctype,
                    status: status,
                    event: currentResult.event,
                    route_to: routeTo
                })
            });

            if (!response.ok) throw new Error("Manual routing request failed on server.");
            const responseData = await response.json();

            showToast(`Manual route applied successfully for ${filename}!`, true);
            
            // Update UI results view with new override info
            currentResult = responseData;
            renderSimulationResults(responseData);
            
            // Sync with stagedFiles entry results cache so selection works correctly
            const stagedFile = stagedFiles.find(f => f.uploadedName === filename);
            if (stagedFile) {
                stagedFile.result = responseData;
            }

            // Mark status badge as approved
            overrideStatusBadge.textContent = "Human Approved";
            overrideStatusBadge.style.color = "var(--state-success)";
            overrideStatusBadge.style.borderColor = "rgba(16, 185, 129, 0.2)";
            overrideStatusBadge.style.backgroundColor = "rgba(16, 185, 129, 0.1)";
            
            // Reload logs and highlight the row
            await loadDashboardLogs();
            highlightLogRow(filename);

        } catch (err) {
            console.error("Manual routing error:", err);
            showToast(`Override Failed: ${err.message}`, false);
        } finally {
            btnConfirmOverride.disabled = false;
            btnConfirmOverride.textContent = "Confirm & Route 🚀";
        }
    }

    // Build and download CSV file containing all logs
    async function exportLogsToCSV() {
        try {
            const response = await fetch(`${API_BASE}/api/logs`);
            if (!response.ok) throw new Error("Failed to load logs to export");
            const logs = await response.json();
            
            if (logs.length === 0) {
                showToast("No logs available to export.", false);
                return;
            }
            
            const headers = ["Event ID", "Filename", "Document Type", "Total Amount", "Status", "Routed Target", "Reason"];
            const csvRows = [headers.join(",")];
            
            logs.forEach(log => {
                const row = [
                    `"${log.event_id}"`,
                    `"${log.filename}"`,
                    `"${log.document_type}"`,
                    log.total_amount !== null ? log.total_amount : "",
                    `"${log.status}"`,
                    `"${log.routed_to || 'unknown'}"`,
                    `"${(log.reason || '').replace(/"/g, '""')}"`
                ];
                csvRows.push(row.join(","));
            });
            
            const csvString = csvRows.join("\n");
            const blob = new Blob([csvString], { type: "text/csv;charset=utf-8;" });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.setAttribute("href", url);
            link.setAttribute("download", `pipeline_operational_logs_${new Date().toISOString().split('T')[0]}.csv`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            showToast("Operational logs exported successfully!", true);
        } catch (err) {
            console.error("Export failed:", err);
            showToast(`Export failed: ${err.message}`, false);
        }
    }

    // Export invoices less than or equal to 50000
    function exportUnder50kCSV() {
        window.location.href = `${API_BASE}/api/export/processed`;
        showToast("Invoices (<= 50k) exported successfully!", true);
    }

    // Interactive toast messages sliding indicator
    function showToast(message, isSuccess = true) {
        const toast = document.getElementById("notification-toast");
        const toastIcon = document.getElementById("toast-icon");
        const toastMessage = document.getElementById("toast-message");
        
        toastMessage.textContent = message;
        if (isSuccess) {
            toastIcon.textContent = "✓";
            toast.style.borderColor = "var(--clr-primary)";
            toastIcon.style.backgroundColor = "var(--clr-primary)";
        } else {
            toastIcon.textContent = "✗";
            toast.style.borderColor = "var(--state-danger)";
            toastIcon.style.backgroundColor = "var(--state-danger)";
        }
        
        toast.classList.remove("hidden");
        
        if (window.toastTimeout) {
            clearTimeout(window.toastTimeout);
        }
        window.toastTimeout = setTimeout(() => {
            toast.classList.add("hidden");
        }, 4000);
    }

    // Highlight row matching filename in logs table
    function highlightLogRow(filename) {
        const rows = logsTableBody.querySelectorAll("tr");
        rows.forEach(row => {
            row.classList.remove("highlighted-row");
            const filenameCell = row.querySelector("td:nth-child(2)");
            if (filenameCell && filenameCell.textContent.trim() === filename) {
                row.classList.add("highlighted-row");
                row.scrollIntoView({ behavior: "smooth", block: "center" });
                
                setTimeout(() => {
                    row.classList.remove("highlighted-row");
                }, 5000);
            }
        });
    }

    // Helper to format file sizes
    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }
});
