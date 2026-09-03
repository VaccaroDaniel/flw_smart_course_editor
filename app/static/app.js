const state = {
  config: null,
  root: "",
  units: [],
  selectedUnit: "",
  unitDetail: null,
  openFile: "",
  openCsv: "",
  csvHeaders: [],
  csvRows: [],
  unitData: null,
  dataView: "overview",
  visualEditActive: false,
  visualPanelOpen: false,
  visualToggleDrag: null,
  visualToggleSuppressClick: false,
  visualSelection: null,
  visualOps: [],
  visualRedoOps: [],
  visualTextEdits: [],
  visualTextRedoAvailable: false,
  visualReplayPending: false,
  visualEditResolver: null,
  visualEditRejecter: null,
  visualMapShown: false,
  zipDirty: false,
  zipStatusMessage: "",
  backups: [],
  assetImportKind: "",
  copyModalSource: null,
  batchJobId: "",
  lastBatchJob: null,
  batchPollTimer: null,
  singleFlwPreviewHash: "",
  batchRebuildPreviewHash: localStorage.getItem("flw.batchRebuildPreviewHash") || ""
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const VISUAL_PANEL_TOGGLE_POS_KEY = "flw.visualPanelTogglePosition";
const LAST_BATCH_JOB_KEY = "flw.lastBatchJobId";
const BATCH_REBUILD_PREVIEW_HASH_KEY = "flw.batchRebuildPreviewHash";
const FLW_IMPORT_MODE_LABELS = {
  overwrite: "Overwrite",
  add_new: "Add New Unit",
  clear_add: "Rebuild Selected FLW Scope"
};

function flwImportModeLabel(mode) {
  return FLW_IMPORT_MODE_LABELS[mode] || mode || "Overwrite";
}

function flwImportModeDescription(mode, batch = false) {
  if (mode === "add_new") {
    return batch
      ? "Create only Units whose canonical FLW UnitID is not already deployed. Existing UnitIDs are reported as UNIT_ALREADY_EXISTS; use Copy Unit first when you need another Unit."
      : "Deploy this Unit as a new FLW Unit. The Unit must have a unique FLW Unit ID. To duplicate an existing Unit, use Copy Unit first, then import the copied Unit.";
  }
  if (mode === "clear_add") {
    return "Safely rebuild only the selected FLW scope. A package-aware dry-run preview is required first; Stage Courses, Unit Sections, manual content, learner history, grades, completion, and legacy Unit Courses are preserved.";
  }
  return batch
    ? "Resolve each World+Stage once, create/reuse one Moodle Section per FLW Unit, then create/update one current Unit SCORM activity in each section. Stage Courses are never cleared."
    : "Synchronize this FLW Unit with its canonical Moodle Stage Course and Unit Section. Existing compatible Unit SCORM content is updated safely; other Units and teacher-added content are preserved.";
}

function formatBatchUnitSelection(source) {
  if (source?.allAvailableUnits || source?.options?.batchAllUnits) {
    return "All available per language";
  }
  return (source?.units || []).join(", ");
}

function formatBatchWorldSelection(source) {
  const options = source?.options || source || {};
  if (Array.isArray(source?.languageRoots) && source.languageRoots.length) {
    return source.languageRoots.map(item => item.worldTitle || item.label || item.worldCode || item.code).join(", ");
  }
  return batchWorldScopeLabel(options.batchWorldScope, options.batchSpecificWorld);
}

function comparablePathText(value) {
  return String(value || "").trim().replaceAll("\\", "/").replace(/\/+$/, "").toLowerCase();
}

function optionText(value, fallback = "") {
  return String(value ?? fallback ?? "").trim();
}

function optionBool(source, key, fallback = false) {
  return Boolean(Object.prototype.hasOwnProperty.call(source || {}, key) ? source[key] : fallback);
}

function completedDryRunJobMatchesPayload(job, payload) {
  if (!job || job.status !== "complete") return false;
  const oldOptions = job.options || {};
  if (!optionBool(oldOptions, "flwDryRun", true) || optionBool(payload, "flwDryRun", true)) return false;
  if (comparablePathText(job.root || oldOptions.root) !== comparablePathText(payload.root || state.root)) return false;
  const boolFields = {
    batchAllUnits: true,
    includeSourceData: false,
    includeTools: false,
    includeUnitSco: false,
    keepTopNavBar: false,
    autocomplete: true
  };
  for (const [key, fallback] of Object.entries(boolFields)) {
    if (optionBool(oldOptions, key, fallback) !== optionBool(payload, key, fallback)) return false;
  }
  const textFields = {
    batchUnitStart: "",
    batchUnitEnd: "",
    batchFlwImportMode: "overwrite",
    batchProductionScope: "",
    batchWorldScope: "all",
    batchSpecificWorld: "",
    launchFile: "index.html"
  };
  for (const [key, fallback] of Object.entries(textFields)) {
    if (optionText(oldOptions[key], fallback) !== optionText(payload[key], fallback)) return false;
  }
  return Number(job.exportedCount || 0) > 0 && Number(job.exportedCount || 0) === Number(job.itemCount || 0);
}

async function reusableCompletedDryRunJobId(payload) {
  if (optionBool(payload, "flwDryRun", true)) return "";
  const jobId = state.batchJobId || localStorage.getItem(LAST_BATCH_JOB_KEY) || "";
  if (!jobId) return "";
  let job = state.lastBatchJob && state.lastBatchJob.jobId === jobId ? state.lastBatchJob : null;
  if (!job) {
    try {
      const data = await api(`/api/batch-job?jobId=${encodeURIComponent(jobId)}`);
      job = data.job;
    } catch (err) {
      job = null;
    }
  }
  if (completedDryRunJobMatchesPayload(job, payload)) return jobId;
  try {
    const data = await api("/api/promotable-batch-dry-run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    return data.job?.jobId || "";
  } catch (err) {
    return "";
  }
}

function toast(message) {
  const box = $("#toast");
  box.textContent = message;
  box.classList.add("show");
  clearTimeout(window.toastTimer);
  window.toastTimer = setTimeout(() => box.classList.remove("show"), 3200);
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (err) {
    if (err instanceof TypeError) {
      throw new Error("The Course Editor server is not reachable at http://127.0.0.1:8788. Reopen or restart the editor, then retry. The requested operation was not started.");
    }
    throw err;
  }
  let data;
  try {
    data = await response.json();
  } catch (err) {
    throw new Error(`The Course Editor server returned an invalid response (${response.status}). Check the server log and retry.`);
  }
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || response.statusText);
  }
  return data;
}

function fmtBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function normalizeResultLines(value) {
  if (Array.isArray(value)) return value.filter(line => line !== null && line !== undefined).map(line => String(line)).filter(Boolean);
  return String(value || "").split(/\r?\n/).map(line => line.trim()).filter(Boolean);
}

function resultTone(status) {
  const value = String(status || "").toLowerCase();
  if (value.includes("fail") || value.includes("error") || value.includes("denied") || value.includes("blocked")) return "error";
  if (value.includes("issue") || value.includes("warn") || value.includes("preview") || value.includes("dry run") || value.includes("canceled")) return "warn";
  if (value.includes("building") || value.includes("starting") || value.includes("running") || value.includes("previewing")) return "running";
  if (value.includes("pass") || value.includes("complete") || value.includes("unchanged") || value.includes("ready")) return "pass";
  return "running";
}

function resultSummaryItem(line) {
  if (typeof line === "object" && line !== null) {
    return {label: String(line.label || "Info"), value: String(line.value ?? "")};
  }
  const text = String(line || "");
  const match = text.match(/^([^:]{1,42}):\s*(.*)$/);
  if (match) return {label: match[1], value: match[2] || "—"};
  return {label: "Info", value: text};
}

function resultSummaryHtml(items) {
  const normalized = (items || []).map(resultSummaryItem).filter(item => item.value);
  if (!normalized.length) return "";
  return `
    <div class="result-summary-grid">
      ${normalized.map(item => `
        <div class="result-summary-item">
          <div class="result-summary-label">${escapeHtml(item.label)}</div>
          <div class="result-summary-value">${escapeHtml(item.value)}</div>
        </div>
      `).join("")}
    </div>
  `;
}

function resultSectionHtml(section) {
  if (!section) return "";
  const title = section.title || "Details";
  const key = section.key || title;
  const open = section.open === false ? "" : " open";
  const items = section.items ? resultSummaryHtml(section.items) : "";
  const lines = section.lines?.length
    ? `<ul class="result-line-list">${section.lines.map(line => `<li>${escapeHtml(line)}</li>`).join("")}</ul>`
    : "";
  const raw = section.raw ? `<pre class="result-raw">${escapeHtml(section.raw)}</pre>` : "";
  return `
    <details class="result-section" data-result-section-key="${escapeHtml(key)}"${open}>
      <summary>${escapeHtml(title)}</summary>
      <div class="result-section-content">${items}${lines}${raw}</div>
    </details>
  `;
}

function exportResultDisclosureState(box) {
  const state = new Map();
  box?.querySelectorAll("details.result-section[data-result-section-key]").forEach(section => {
    const raw = section.querySelector(".result-raw");
    state.set(section.dataset.resultSectionKey, {
      open: section.open,
      rawScrollTop: raw?.scrollTop || 0
    });
  });
  return state;
}

function setExportResultPanel({title = "Result", status = "INFO", message = "", summary = [], sections = [], raw = "", rawOpen = false, preserveDisclosureState = false} = {}) {
  const box = $("#exportResult");
  if (!box) return;
  const disclosureState = preserveDisclosureState ? exportResultDisclosureState(box) : new Map();
  const withPreservedState = section => {
    const key = section.key || section.title || "Details";
    const previous = disclosureState.get(key);
    return previous ? {...section, key, open: previous.open} : {...section, key};
  };
  const tone = resultTone(status);
  box.classList.remove("result-empty");
  const renderedSections = (sections || []).map(withPreservedState);
  const rawSection = raw ? withPreservedState({key: "raw-log", title: "Raw log", raw, open: rawOpen}) : null;
  box.innerHTML = `
    <div class="result-head">
      <span class="result-status ${tone}">${escapeHtml(status || "INFO")}</span>
      <div>
        <div class="result-title">${escapeHtml(title)}</div>
        ${message ? `<div class="result-message">${escapeHtml(message)}</div>` : ""}
      </div>
    </div>
    ${resultSummaryHtml(summary)}
    ${renderedSections.map(resultSectionHtml).join("")}
    ${rawSection ? resultSectionHtml(rawSection) : ""}
  `;
  if (preserveDisclosureState) {
    box.querySelectorAll("details.result-section[data-result-section-key]").forEach(section => {
      const previous = disclosureState.get(section.dataset.resultSectionKey);
      const rawBox = section.querySelector(".result-raw");
      if (previous && rawBox) rawBox.scrollTop = previous.rawScrollTop;
    });
  }
}

function setExportResultFromText(title, text, options = {}) {
  const lines = normalizeResultLines(text);
  const status = options.status || lines[0] || "INFO";
  const message = options.message || lines[1] || "";
  const summary = lines.slice(2, 10);
  const detailLines = lines.slice(10);
  setExportResultPanel({
    title,
    status,
    message,
    summary,
    sections: detailLines.length ? [{title: "Details", lines: detailLines, open: true}] : [],
    raw: lines.join("\n"),
    rawOpen: false,
    preserveDisclosureState: Boolean(options.preserveDisclosureState)
  });
}

function setExportResultLoading(title, message = "") {
  setExportResultPanel({title, status: "RUNNING", message, summary: []});
}

function setExportResultError(err, title = "Operation failed") {
  const message = err?.message || String(err || "Unknown error");
  setExportResultPanel({
    title,
    status: "ERROR",
    message,
    summary: [{label: "Likely next step", value: "Check the message, fix the setting or permission, then run again."}],
    raw: err?.stack || message,
    rawOpen: true
  });
}

function currentUnitSummaryValue() {
  if (!state.selectedUnit) return "No unit selected";
  const title = state.unitDetail?.meta?.title || $("#unitTitle")?.textContent || "";
  return `Unit ${state.selectedUnit}${title ? ` · ${title}` : ""}`;
}

function batchScopeText(payload) {
  const world = batchWorldScopeLabel(payload?.batchWorldScope, payload?.batchSpecificWorld);
  if (payload?.batchAllUnits) return `All available units · ${world}`;
  const start = payload?.batchUnitStart || state.selectedUnit || "001";
  const end = payload?.batchUnitEnd || start;
  const units = start === end ? `Unit ${start}` : `Units ${start} to ${end}`;
  return `${units} · ${world}`;
}

function currentTargetSummaryRows(payload = null) {
  const base = payload || (typeof scormOptionsPayload === "function" ? scormOptionsPayload() : {});
  const batch = typeof batchScormOptionsPayload === "function" ? batchScormOptionsPayload() : {};
  return [
    {label: "Moodle URL", value: base.moodleUrl || "(not set)"},
    {label: "Selected unit", value: currentUnitSummaryValue()},
    {label: "Single import mode", value: flwImportModeLabel(base.flwImportMode || "overwrite")},
    {label: "Batch import mode", value: flwImportModeLabel(batch.batchFlwImportMode || "overwrite")},
    {label: "Batch scope", value: batchScopeText(batch)},
    {label: "World selection", value: batchWorldScopeLabel(batch.batchWorldScope, batch.batchSpecificWorld)},
    {label: "Production scope", value: batchProductionScopeLabel(batch.batchProductionScope || "")},
    {label: "Resolved Moodle target", value: "Run a preview to resolve the course, unit section, and activity before import."}
  ];
}

function setMoodleTargetSummary({title = "Moodle Target Summary", message = "", rows = []} = {}) {
  const box = $("#moodleTargetSummary");
  if (!box) return;
  const normalized = (rows || []).filter(row => row && row.value !== undefined && row.value !== "");
  box.innerHTML = `
    <h3>${escapeHtml(title)}</h3>
    ${message ? `<div class="result-message">${escapeHtml(message)}</div>` : ""}
    <div class="target-summary-grid">
      ${normalized.map(row => `
        <div class="target-summary-item">
          <div class="target-summary-label">${escapeHtml(row.label)}</div>
          <div class="target-summary-value">${escapeHtml(row.value)}</div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderMoodleTargetSummary(message = "Current settings. Preview before importing to confirm the exact Moodle destination.") {
  setMoodleTargetSummary({message, rows: currentTargetSummaryRows()});
}

function renderMoodleTargetSummaryFromSingle(data, title = "Resolved Moodle target for selected unit") {
  const report = data?.flw?.report || {};
  const summary = report.summary || {};
  const first = (report.results || [])[0] || {};
  const unitFirst = (report.unitResults || [])[0] || {};
  const single = report.singleImport || {};
  const flwUnit = single.flwUnit || {};
  const destination = single.moodleDestination || {};
  const planned = single.plannedAction || {};
  const courseLabel = destination.stageCourseName
    ? `${destination.stageCourseName}${destination.stageCourseKey ? ` (${destination.stageCourseKey})` : ""}`
    : (first.courseFullname || first.courseShortname || first.courseExternalKey || "(not resolved)");
  const sectionLabel = destination.unitSectionName
    ? `${destination.unitSectionName}${destination.unitSectionNumber != null ? ` (#${destination.unitSectionNumber})` : ""}`
    : (unitFirst.expectedSectionName || unitFirst.sectionName || "(not resolved)");
  setMoodleTargetSummary({
    title,
    message: single.dryRun || report.dryRun || data?.flw?.dryRun ? "Preview only. No Moodle changes were made." : "Last resolved target from the completed import.",
    rows: [
      {label: "Moodle URL", value: data?.flw?.moodleUrl || report.moodleUrl || $("#moodleUrl")?.value || "(not set)"},
      {label: "World", value: flwUnit.worldTitle || flwUnit.worldCode || first.worldTitle || first.worldCode || "(not resolved)"},
      {label: "Stage", value: flwUnit.deploymentStageCode || first.deploymentStageCode || unitFirst.deploymentStageCode || "(not resolved)"},
      {label: "Unit", value: flwUnit.unitId || unitFirst.unitId || data?.flw?.singleImportRequest?.unitId || currentUnitSummaryValue()},
      {label: "Moodle course", value: courseLabel},
      {label: "Course image", value: first.courseImage?.status || "(not reported)"},
      {label: "Unit section", value: sectionLabel},
      {label: "Activity", value: destination.unitScormName || unitFirst.scormName || "Unit SCORM"},
      {label: "Planned action", value: `Course ${planned.course || first.courseAction || "?"} · Section ${planned.section || unitFirst.sectionAction || "?"} · SCORM ${planned.scorm || unitFirst.scormAction || "?"}`},
      {label: "Status", value: single.publicStatus || summary.publicStatus || "READY"}
    ]
  });
}

function renderMoodleTargetSummaryFromBatchPreview(data, title = "Resolved Moodle batch target") {
  const preview = data?.preview || {};
  const report = preview.report || {};
  const summary = report.summary || {};
  const languageLabels = (data?.languageRoots || []).map(item => {
    const count = item.plannedUnitCount ?? item.unitCount;
    return `${item.label}${count != null ? ` (${count})` : ""}`;
  }).join(", ");
  setMoodleTargetSummary({
    title,
    message: "Batch preview resolved the language/world course and unit-section mapping.",
    rows: [
      {label: "Moodle URL", value: preview.moodleUrl || report.moodleUrl || $("#moodleUrl")?.value || "(not set)"},
      {label: "Import mode", value: flwImportModeLabel(data?.importMode || preview.importMode || report.importMode || "overwrite")},
      {label: "Production scope", value: data?.catalogValidation ? batchProductionScopeLabel(data.catalogValidation.productionScope) : batchProductionScopeLabel($("#batchProductionScope")?.value || "")},
      {label: "World selection", value: formatBatchWorldSelection(data)},
      {label: "Languages", value: languageLabels || "(not resolved)"},
      {label: "Units selected", value: formatBatchUnitSelection(data || {})},
      {label: "Moodle courses", value: `${summary.reusedStageCourses ?? summary.mapped ?? 0} reused · ${summary.wouldCreateStageCourses ?? summary.wouldCreateCourse ?? 0} would be created`},
      {label: "Course images", value: `${summary.courseImagesWouldSet ?? 0} would be set · ${summary.courseImagesWouldUpdate ?? 0} would be updated · ${summary.courseImagesPendingExport ?? 0} pending export`},
      {label: "Unit sections", value: `${summary.unitSectionCount ?? 0} planned · ${summary.wouldCreateUnitSections ?? 0} would be created`},
      {label: "Conflicts/blockers", value: String(summary.conflictCount ?? summary.missingCourse ?? 0)}
    ]
  });
}

function renderMoodleTargetSummaryFromJob(job) {
  if (!job) return renderMoodleTargetSummary();
  setMoodleTargetSummary({
    title: "Moodle batch target / job status",
    message: job.current || "Batch job status updated.",
    rows: [
      {label: "Job", value: job.jobId || "(not reported)"},
      {label: "Status", value: `${job.status || "unknown"} · ${job.phase || "unknown"}`},
      {label: "Import mode", value: flwImportModeLabel(job.importMode || job.options?.batchFlwImportMode || job.flw?.importMode || "overwrite")},
      {label: "Progress", value: `${job.processedCount || 0}/${job.itemCount || 0} units`},
      {label: "Packages", value: `${job.exportedCount || 0} exported · ${job.exportFailedCount || 0} failed`},
      {label: "Moodle import report", value: job.flwReportPath || job.flw?.reportPath || "(not available yet)"},
      {label: "Scope", value: formatBatchUnitSelection(job)},
      {label: "World selection", value: formatBatchWorldSelection(job)}
    ]
  });
}

function currentRootQuery() {
  return `root=${encodeURIComponent(state.root)}`;
}

function hasUnsavedZipChanges() {
  return Boolean(state.zipDirty && state.unitDetail?.canSaveZip && state.selectedUnit);
}

function confirmUnsavedZipChanges(action = "continue") {
  if (!hasUnsavedZipChanges()) return true;
  const unitLabel = `Unit ${state.selectedUnit}`;
  return window.confirm([
    `${unitLabel} has changes saved only in the unpacked ZIP cache.`,
    "",
    "Use “Save back to source ZIP” if you want those edits written into the original unit ZIP.",
    "",
    `Continue to ${action} anyway?`
  ].join("\n"));
}

function unitPreviewUrl(path) {
  if (!state.selectedUnit || !path) return "";
  return `/preview/${encodeURIComponent(state.selectedUnit)}/${String(path).replace(/^\/+/, "")}?${currentRootQuery()}&t=${Date.now()}`;
}

function defaultIdentifier(unit) {
  const seed = unit ? `AEW3_U${unit.number}_SCORM12` : "AEW3_SCORM12";
  return `${seed}_${new Date().toISOString().slice(0, 10).replaceAll("-", "")}`;
}

function replaceUnitNumberInText(value, sourceUnit, targetUnit) {
  const source = String(Number(sourceUnit || 0));
  const target = String(Number(targetUnit || 0));
  return String(value || "")
    .replace(new RegExp(`\\bUnit\\s+${sourceUnit}\\b`, "gi"), `Unit ${targetUnit}`)
    .replace(new RegExp(`\\bUnit\\s+${source}\\b`, "gi"), `Unit ${target}`)
    .replace(new RegExp(`\\bU${sourceUnit}\\b`, "gi"), `U${targetUnit}`);
}

function visualId(prefix = "visual") {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function previewUrl(edit = false) {
  const base = edit ? "/edit-preview" : "/preview";
  return `${base}/${state.selectedUnit}/index.html?${currentRootQuery()}&t=${Date.now()}`;
}

async function loadConfig() {
  state.config = await api("/api/config");
  state.root = state.config.defaultRoot;
  $("#rootInput").value = state.root;
  $("#exportDir").value = state.config.defaultExportDir;
  $("#moodleUrl").value = state.config.defaultMoodleUrl || "";
  $("#moodlePhpPath").value = state.config.defaultMoodlePhpPath || "";
  $("#moodleConfigPath").value = state.config.defaultMoodleConfigPath || "";
  populateBatchWorldOptions();
  renderMoodleTargetSummary("Saved settings loaded. Preview before importing to confirm the exact Moodle destination.");
}

async function saveSettings(patch) {
  return api("/api/settings", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(patch)
  });
}

async function browseDirectory(initialDir, title) {
  return api("/api/select-directory", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({initialDir, title})
  });
}

async function loadUnits(options = {}) {
  const saveRoot = options.saveRoot ?? false;
  state.root = $("#rootInput").value.trim();
  const data = await api(`/api/units?${currentRootQuery()}`);
  state.units = data.units;
  state.root = data.root || state.root;
  $("#rootInput").value = state.root;
  if (saveRoot) await saveSettings({root: state.root});
  renderUnits();
  if (state.selectedUnit && !state.units.some(unit => unit.number === state.selectedUnit)) {
    state.selectedUnit = "";
    state.unitDetail = null;
  }
  if (!state.selectedUnit && state.units.length) {
    await selectUnit(state.units[0].number);
  } else if (state.selectedUnit) {
    await selectUnit(state.selectedUnit);
  } else {
    clearSelectedUnit("No units found");
  }
}

async function browseRootDirectory() {
  if (!confirmUnsavedZipChanges("change the course root")) return;
  const data = await browseDirectory($("#rootInput").value.trim(), "Select course or SmartCourses root");
  if (!data.path) return;
  $("#rootInput").value = data.path;
  state.selectedUnit = "";
  await loadUnits({saveRoot: true});
  toast("Course root saved.");
}

async function browseExportDirectory() {
  const data = await browseDirectory($("#exportDir").value.trim() || state.root, "Select SCORM export folder");
  if (!data.path) return;
  $("#exportDir").value = data.path;
  await saveSettings({exportDir: data.path});
  toast("Export folder saved.");
}

function clearSelectedUnit(message = "No unit selected") {
  state.selectedUnit = "";
  state.unitDetail = null;
  state.openFile = "";
  state.openCsv = "";
  state.csvHeaders = [];
  state.csvRows = [];
  state.unitData = null;
  state.visualSelection = null;
  state.visualOps = [];
  state.visualRedoOps = [];
  state.visualTextEdits = [];
  state.visualTextRedoAvailable = false;
  state.visualReplayPending = false;
  state.visualEditActive = false;
  state.zipDirty = false;
  state.zipStatusMessage = "";
  state.backups = [];
  $("#unitTitle").textContent = message;
  $("#selectedPath").textContent = state.root ? `Root: ${state.root}` : "No unit selected";
  $("#saveBackZipBtn").disabled = true;
  $("#zipSaveHint").textContent = "Select a ZIP-backed unit to update its original ZIP.";
  renderZipStatus();
  $("#previewFrame").src = "about:blank";
  $("#visualEditStatus").textContent = "Preview is read-only.";
  $("#saveVisualEditsBtn").disabled = true;
  renderVisualEditToggle();
  renderVisualHistoryButtons();
  renderVisualSelection();
  renderImageOptions();
  $("#scormTitle").value = "";
  $("#scormIdentifier").value = "";
  $("#launchFile").value = "index.html";
  $("#includeUnitSco").checked = false;
  $("#keepTopNavBar").checked = false;
  renderFiles();
  renderCsvList();
  renderValidation(null);
  renderBackupDashboard();
  renderScormStructurePreview(null);
  renderMoodleTargetSummary("No unit is selected yet. Select a unit, then preview the Moodle destination before importing.");
  setExportResultPanel({
    title: "Export / FLW Import",
    status: "READY",
    message: "No export or import has run yet.",
    summary: [{label: "Next step", value: "Select a unit or choose a batch scope, then run a preview."}]
  });
  $("#unitDataLabel").textContent = "No unit data loaded";
  $("#unitDataStatus").textContent = "";
  $("#unitDataSummary").textContent = "";
  $("#overviewFields").innerHTML = "";
  $("#vocabEditor").innerHTML = "";
  $("#lessonsEditor").innerHTML = "";
  $("#watchEditor").innerHTML = "";
  $("#rawUnitDataEditor").value = "";
  $("#textEditor").value = "";
  $("#openFileLabel").textContent = "No file open";
  $("#csvGrid").innerHTML = "";
  $("#openCsvLabel").textContent = "No CSV open";
}

function renderUnits() {
  const filter = $("#unitFilter").value.trim().toLowerCase();
  const list = $("#unitList");
  const units = state.units.filter(unit => {
    const hay = `${unit.number} ${unit.name} ${unit.title} ${unit.stage}`.toLowerCase();
    return !filter || hay.includes(filter);
  });
  $("#unitCount").textContent = String(units.length);
  if (!units.length) {
    list.innerHTML = `<div class="empty-list">${filter ? "No matching units." : "No units found in this root."}</div>`;
    return;
  }
  list.innerHTML = units.map(unit => `
    <button class="unit-item ${unit.number === state.selectedUnit ? "active" : ""}" data-unit="${unit.number}">
      <span class="unit-line">
        <span class="unit-number">U${unit.number}</span>
        <span class="meta">${unit.stage || "stage pending"}</span>
      </span>
      <span class="unit-title">${escapeHtml(unit.title)}</span>
      <span class="meta">${unit.counts.files} files · ${fmtBytes(unit.counts.bytes)}</span>
    </button>
  `).join("");
}

function suggestedCopyUnitNumber() {
  const used = new Set(state.units.map(unit => Number(unit.number)).filter(Number.isFinite));
  const selected = Number(state.selectedUnit);
  const start = Number.isFinite(selected) ? selected + 1 : 1;
  for (let number = start; number <= 999; number += 1) {
    if (!used.has(number)) return String(number).padStart(3, "0");
  }
  for (let number = 1; number <= 999; number += 1) {
    if (!used.has(number)) return String(number).padStart(3, "0");
  }
  return "";
}

function normalizePromptedUnitNumber(value) {
  const match = String(value || "").match(/\d{1,3}/);
  if (!match) return "";
  const number = Number(match[0]);
  if (!Number.isFinite(number) || number < 1 || number > 999) return "";
  return String(number).padStart(3, "0");
}

function openCopyUnitModal() {
  if (!state.selectedUnit) return toast("Select a unit first.");
  if (!confirmUnsavedZipChanges("copy the current unpacked unit")) return;
  const suggested = suggestedCopyUnitNumber();
  if (!suggested) return toast("No free unit number is available.");
  const source = state.units.find(unit => unit.number === state.selectedUnit);
  const defaultTitle = replaceUnitNumberInText(state.unitDetail?.meta?.title || source?.title || `Unit ${state.selectedUnit}`, state.selectedUnit, suggested);
  state.copyModalSource = source || null;
  $("#copyTargetUnit").value = suggested;
  $("#copyTitle").value = defaultTitle;
  $("#copyOutputType").value = source?.source === "zip" || state.unitDetail?.canSaveZip ? "auto" : "folder";
  renderCopyModalSummary();
  $("#copyUnitModal").hidden = false;
  $("#copyTargetUnit").focus();
  $("#copyTargetUnit").select();
}

function closeCopyUnitModal() {
  $("#copyUnitModal").hidden = true;
}

function copyModalValues() {
  const targetUnit = normalizePromptedUnitNumber($("#copyTargetUnit").value);
  const title = $("#copyTitle").value.trim();
  const outputType = $("#copyOutputType").value;
  return {targetUnit, title, outputType};
}

function renderCopyModalSummary() {
  const {targetUnit, title, outputType} = copyModalValues();
  const source = state.copyModalSource || state.units.find(unit => unit.number === state.selectedUnit);
  const exists = targetUnit && state.units.some(unit => unit.number === targetUnit);
  const same = targetUnit && targetUnit === state.selectedUnit;
  const sourceKind = state.unitDetail?.canSaveZip || source?.source === "zip" ? "ZIP-backed unit" : "folder unit";
  const lines = [
    `Source: Unit ${state.selectedUnit} ${source?.title || ""}`.trim(),
    `Source type: ${sourceKind}`,
    `Target: ${targetUnit ? `Unit ${targetUnit}` : "enter 001-999"}`,
    `Title: ${title || "(keep copied title)"}`,
    `Output: ${outputType}`,
  ];
  if (!targetUnit) lines.push("Problem: enter a unit number from 001 to 999.");
  if (same) lines.push("Problem: choose a different unit number.");
  if (exists) lines.push(`Problem: Unit ${targetUnit} already exists.`);
  if (state.visualOps.length || state.visualTextEdits.length) {
    lines.push("Note: unsaved visual edits are not copied until you save them.");
  }
  $("#copyModalSummary").textContent = lines.join("\n");
  $("#confirmCopyUnitBtn").disabled = !targetUnit || same || exists;
}

async function copySelectedUnit() {
  if (!state.selectedUnit) return toast("Select a unit first.");
  const {targetUnit, title, outputType} = copyModalValues();
  if (!targetUnit) return toast("Enter a unit number from 001 to 999.");
  if (targetUnit === state.selectedUnit) return toast("Choose a different unit number.");
  if (state.units.some(unit => unit.number === targetUnit)) return toast(`Unit ${targetUnit} already exists.`);
  $("#selectedPath").textContent = `Copying Unit ${state.selectedUnit} to Unit ${targetUnit}...`;
  $("#confirmCopyUnitBtn").disabled = true;
  const data = await api("/api/copy-unit", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({root: state.root, unit: state.selectedUnit, targetUnit, title, outputType})
  });
  closeCopyUnitModal();
  state.units = data.units || state.units;
  renderUnits();
  await selectUnit(data.copy.unit, {skipDirtyCheck: true});
  const copyResult = [
    "PASS",
    `Copied Unit ${data.copy.sourceUnit} to Unit ${data.copy.unit}.`,
    `Source type: ${data.copy.source}`,
    `Output type: ${data.copy.outputType || data.copy.source}`,
    data.copy.title ? `Title: ${data.copy.title}` : "",
    `Path: ${data.copy.path}`,
    data.copy.archivePath ? `ZIP: ${data.copy.archivePath}` : "",
    data.copy.internalPrefix ? `Internal prefix: ${data.copy.internalPrefix}` : "",
    `Files: ${data.copy.fileCount}`,
    data.copy.zipTest ? `Zip test: ${data.copy.zipTest}` : "",
    `Unit metadata updated: ${data.copy.metadataUpdated ? "yes" : "no"}`,
    `Manifest updated: ${data.copy.manifestUpdated ? "yes" : "no"}`
  ].filter(Boolean).join("\n");
  setExportResultFromText("Unit copy", copyResult);
  toast(`Copied to Unit ${data.copy.unit}.`);
}

async function selectUnit(number, options = {}) {
  if (!options.skipDirtyCheck && number !== state.selectedUnit && !confirmUnsavedZipChanges(`open Unit ${number}`)) return;
  state.selectedUnit = number;
  renderUnits();
  const detail = await api(`/api/unit?${currentRootQuery()}&unit=${encodeURIComponent(number)}`);
  state.unitDetail = detail;
  state.openFile = "";
  state.openCsv = "";
  state.csvHeaders = [];
  state.csvRows = [];
  state.unitData = null;
  state.visualSelection = null;
  state.visualOps = [];
  state.visualRedoOps = [];
  state.visualTextEdits = [];
  state.visualTextRedoAvailable = false;
  state.visualReplayPending = false;
  state.visualMapShown = false;
  state.zipDirty = false;
  state.zipStatusMessage = "";
  const unit = state.units.find(item => item.number === number);
  $("#unitTitle").textContent = detail.meta.title || unit?.title || `Unit ${number}`;
  $("#selectedPath").textContent = detail.path;
  renderVisualPanelFold();
  $("#saveBackZipBtn").disabled = !detail.canSaveZip;
  $("#zipSaveHint").textContent = detail.canSaveZip
    ? `Source ZIP: ${detail.archivePath}`
    : "Select a ZIP-backed unit to update its original ZIP.";
  renderZipStatus();
  state.visualEditActive = false;
  $("#previewFrame").src = previewUrl(false);
  $("#visualEditStatus").textContent = "Preview is read-only.";
  $("#saveVisualEditsBtn").disabled = true;
  renderVisualEditToggle();
  renderVisualHistoryButtons();
  renderVisualSelection();
  renderImageOptions();
  $("#scormTitle").value = `${detail.meta.course || "Adventure English World V3"} Unit ${number} ${detail.meta.title || ""}`.trim();
  $("#scormIdentifier").value = defaultIdentifier(unit);
  $("#launchFile").value = "index.html";
  $("#includeUnitSco").checked = false;
  $("#keepTopNavBar").checked = false;
  renderMoodleTargetSummary("Current settings. Preview before importing to confirm the exact Moodle destination.");
  renderFiles();
  renderCsvList();
  renderValidation(detail.validation);
  await loadBackups();
  await refreshScormStructurePreview({silent: true});
  await loadUnitData();
  $("#textEditor").value = "";
  $("#openFileLabel").textContent = "No file open";
  $("#csvGrid").innerHTML = "";
  $("#openCsvLabel").textContent = "No CSV open";
}

function renderFiles() {
  const filter = $("#fileFilter").value.trim().toLowerCase();
  const files = (state.unitDetail?.files || []).filter(file => {
    return (!filter || file.path.toLowerCase().includes(filter)) && file.editable;
  });
  $("#fileList").innerHTML = files.map(file => `
    <button class="file-item ${file.path === state.openFile ? "active" : ""}" data-path="${escapeHtml(file.path)}">
      <span class="unit-line"><span>${escapeHtml(file.path)}</span><span class="meta">${file.kind}</span></span>
      <span class="meta">${fmtBytes(file.size)} · ${file.modified}</span>
    </button>
  `).join("");
}

function renderCsvList() {
  const files = (state.unitDetail?.files || []).filter(file => file.kind === "csv");
  $("#csvList").innerHTML = files.map(file => `
    <button class="file-item ${file.path === state.openCsv ? "active" : ""}" data-csv="${escapeHtml(file.path)}">
      <span class="unit-line"><span>${escapeHtml(file.path)}</span><span class="meta">CSV</span></span>
      <span class="meta">${fmtBytes(file.size)}</span>
    </button>
  `).join("");
}

async function openFile(path) {
  const data = await api(`/api/file?${currentRootQuery()}&unit=${state.selectedUnit}&path=${encodeURIComponent(path)}`);
  state.openFile = path;
  $("#openFileLabel").textContent = path;
  $("#textEditor").value = data.content;
  renderFiles();
}

async function saveFile() {
  if (!state.openFile) return toast("Open a text file first.");
  const wasZipBacked = Boolean(state.unitDetail?.canSaveZip);
  const payload = {
    root: state.root,
    unit: state.selectedUnit,
    path: state.openFile,
    content: $("#textEditor").value
  };
  await api("/api/file", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });
  toast(`Saved ${state.openFile}`);
  await selectUnit(state.selectedUnit);
  await openFile(payload.path);
  if (wasZipBacked) markUnitDirty("ZIP status: file saved in unpacked cache; save back to source ZIP.");
}

async function openCsv(path) {
  const data = await api(`/api/csv?${currentRootQuery()}&unit=${state.selectedUnit}&path=${encodeURIComponent(path)}`);
  state.openCsv = path;
  state.csvHeaders = data.headers;
  state.csvRows = data.rows;
  $("#openCsvLabel").textContent = path;
  renderCsvList();
  renderCsvGrid();
}

function renderCsvGrid() {
  if (!state.csvHeaders.length) {
    $("#csvGrid").innerHTML = "";
    return;
  }
  $("#csvGrid").innerHTML = `
    <table>
      <thead><tr>${state.csvHeaders.map(h => `<th>${escapeHtml(h)}</th>`).join("")}<th></th></tr></thead>
      <tbody>
        ${state.csvRows.map((row, rowIndex) => `
          <tr data-row="${rowIndex}">
            ${state.csvHeaders.map(header => `
              <td><input value="${escapeHtml(row[header] || "")}" data-header="${escapeHtml(header)}"></td>
            `).join("")}
            <td><button data-delete-row="${rowIndex}">Delete</button></td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function collectCsvGrid() {
  const rows = [];
  $$("#csvGrid tbody tr").forEach(tr => {
    const row = {};
    $$("input", tr).forEach(input => {
      row[input.dataset.header] = input.value;
    });
    rows.push(row);
  });
  state.csvRows = rows;
}

async function saveCsv() {
  if (!state.openCsv) return toast("Open a CSV first.");
  const wasZipBacked = Boolean(state.unitDetail?.canSaveZip);
  const csvPath = state.openCsv;
  collectCsvGrid();
  await api("/api/csv", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      root: state.root,
      unit: state.selectedUnit,
      path: csvPath,
      headers: state.csvHeaders,
      rows: state.csvRows
    })
  });
  toast(`Saved ${csvPath}`);
  await selectUnit(state.selectedUnit);
  await openCsv(csvPath);
  if (wasZipBacked) markUnitDirty("ZIP status: CSV saved in unpacked cache; save back to source ZIP.");
}

function addCsvRow() {
  if (!state.openCsv) return toast("Open a CSV first.");
  collectCsvGrid();
  const row = {};
  state.csvHeaders.forEach(header => row[header] = "");
  state.csvRows.push(row);
  renderCsvGrid();
}

const overviewFields = [
  {key: "course", label: "Course"},
  {key: "unit", label: "Unit"},
  {key: "title", label: "Title"},
  {key: "cefr", label: "CEFR"},
  {key: "stage", label: "Stage"},
  {key: "heroStage", label: "Hero stage"},
  {key: "mission", label: "Mission", type: "textarea"},
  {key: "heroImage", label: "Hero image"},
  {key: "watchPoster", label: "Watch poster"},
  {key: "videoSrc", label: "Video source"}
];

const vocabColumns = [
  {key: "word", label: "Word"},
  {key: "ipa", label: "IPA"},
  {key: "kind", label: "Kind"},
  {key: "meaning", label: "Meaning", wide: true},
  {key: "example", label: "Example", wide: true},
  {key: "note", label: "Note", wide: true},
  {key: "icon", label: "Icon"}
];

const lessonColumns = [
  {key: "id", label: "ID"},
  {key: "title", label: "Title"},
  {key: "aim", label: "Aim", wide: true},
  {key: "studyTitle", label: "Study title"},
  {key: "practice", label: "Practice"},
  {key: "image", label: "Image"},
  {key: "style", label: "Style"},
  {key: "audioKey", label: "Audio key"},
  {key: "study", label: "Study lines", type: "lines", wide: true},
  {key: "rule", label: "Rule", type: "textarea", wide: true},
  {key: "tip", label: "Tip", type: "textarea", wide: true}
];

const watchColumns = [
  {key: "speaker", label: "Speaker"},
  {key: "text", label: "Text", wide: true},
  {key: "audioKey", label: "Audio key"},
  {key: "duration", label: "Seconds", type: "number"}
];

function valueText(value) {
  if (Array.isArray(value)) return value.join("\n");
  if (value === null || value === undefined) return "";
  return String(value);
}

async function loadUnitData() {
  $("#unitDataStatus").textContent = "";
  $("#unitDataLabel").textContent = "Loading unit data";
  try {
    const data = await api(`/api/unit-data?${currentRootQuery()}&unit=${state.selectedUnit}`);
    state.unitData = data.data;
    $("#unitDataLabel").textContent = `index.html / window.UNIT_DATA`;
    renderUnitData(data.summary);
  } catch (err) {
    state.unitData = null;
    $("#unitDataLabel").textContent = "No unit data loaded";
    $("#unitDataSummary").textContent = "";
    $("#unitDataStatus").textContent = err.message;
    $("#overviewFields").innerHTML = "";
    $("#vocabEditor").innerHTML = "";
    $("#lessonsEditor").innerHTML = "";
    $("#watchEditor").innerHTML = "";
    $("#rawUnitDataEditor").value = "";
  }
}

function renderUnitData(summary) {
  if (!state.unitData) return;
  const data = state.unitData;
  const currentSummary = summary || {
    title: data.title || "",
    stage: data.stage || data.cefr || "",
    vocab: (data.vocab || []).length,
    lessons: (data.lessons || []).length,
    watch: (data.watch || []).length,
    practiceSets: data.practice && typeof data.practice === "object" ? Object.keys(data.practice).length : 0
  };
  $("#unitDataSummary").textContent = [
    currentSummary.title || "Untitled",
    currentSummary.stage || "No stage",
    `${currentSummary.vocab} vocab`,
    `${currentSummary.lessons} lessons`,
    `${currentSummary.watch} watch lines`,
    `${currentSummary.practiceSets} practice sets`
  ].join("\n");
  renderOverviewFields();
  renderArrayTable("#vocabEditor", data.vocab || [], vocabColumns, "vocab");
  renderArrayTable("#lessonsEditor", data.lessons || [], lessonColumns, "lessons");
  renderArrayTable("#watchEditor", data.watch || [], watchColumns, "watch");
  $("#rawUnitDataEditor").value = JSON.stringify(data, null, 2);
  setDataView(state.dataView);
}

function renderOverviewFields() {
  const data = state.unitData || {};
  $("#overviewFields").innerHTML = overviewFields.map(field => {
    const value = escapeHtml(valueText(data[field.key]));
    if (field.type === "textarea") {
      return `<label>${field.label}<textarea data-overview-field="${field.key}">${value}</textarea></label>`;
    }
    return `<label>${field.label}<input data-overview-field="${field.key}" value="${value}"></label>`;
  }).join("");
}

function renderArrayTable(selector, rows, columns, arrayName) {
  const body = rows.map((row, rowIndex) => `
    <tr data-row="${rowIndex}">
      ${columns.map(column => {
        const value = escapeHtml(valueText(row[column.key]));
        const cls = column.wide ? "wide-cell" : "";
        const input = column.type === "textarea" || column.type === "lines"
          ? `<textarea data-field="${column.key}">${value}</textarea>`
          : `<input data-field="${column.key}" value="${value}"${column.type === "number" ? ' inputmode="decimal"' : ""}>`;
        return `<td class="${cls}">${input}</td>`;
      }).join("")}
      <td><button data-delete-array="${arrayName}" data-delete-index="${rowIndex}">Delete</button></td>
    </tr>
  `).join("");
  $(selector).innerHTML = `
    <table class="editable-table">
      <thead><tr>${columns.map(column => `<th>${column.label}</th>`).join("")}<th></th></tr></thead>
      <tbody>${body}</tbody>
    </table>
  `;
}

function collectOverviewFields() {
  if (!state.unitData) return;
  overviewFields.forEach(field => {
    const input = $(`[data-overview-field="${field.key}"]`);
    if (!input) return;
    if (field.key === "unit") {
      const numberValue = Number(input.value);
      state.unitData[field.key] = Number.isFinite(numberValue) ? numberValue : input.value;
    } else {
      state.unitData[field.key] = input.value;
    }
  });
}

function collectArrayRows(selector, columns) {
  return $$(`${selector} tbody tr`).map(tr => {
    const row = {};
    columns.forEach(column => {
      const input = tr.querySelector(`[data-field="${column.key}"]`);
      if (!input) return;
      if (column.type === "lines") {
        row[column.key] = input.value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
      } else if (column.type === "number") {
        const value = Number(input.value);
        row[column.key] = Number.isFinite(value) ? value : input.value;
      } else {
        row[column.key] = input.value;
      }
    });
    return row;
  });
}

function collectUnitDataFromEditor() {
  if (!state.unitData) return null;
  if (state.dataView === "raw") {
    state.unitData = JSON.parse($("#rawUnitDataEditor").value);
    return state.unitData;
  }
  collectOverviewFields();
  state.unitData.vocab = collectArrayRows("#vocabEditor", vocabColumns);
  state.unitData.lessons = collectArrayRows("#lessonsEditor", lessonColumns);
  state.unitData.watch = collectArrayRows("#watchEditor", watchColumns);
  $("#rawUnitDataEditor").value = JSON.stringify(state.unitData, null, 2);
  return state.unitData;
}

async function saveUnitData() {
  if (!state.unitData) return toast("No unit data is loaded.");
  const wasZipBacked = Boolean(state.unitDetail?.canSaveZip);
  let data;
  try {
    data = collectUnitDataFromEditor();
  } catch (err) {
    return toast(`Unit data JSON error: ${err.message}`);
  }
  const response = await api("/api/unit-data", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      root: state.root,
      unit: state.selectedUnit,
      data
    })
  });
  renderValidation(response.validation);
  toast("Saved unit data.");
  const view = state.dataView;
  await selectUnit(state.selectedUnit);
  switchTab("unitData");
  setDataView(view);
  if (wasZipBacked) markUnitDirty("ZIP status: unit data saved in unpacked cache; save back to source ZIP.");
}

function setDataView(view) {
  state.dataView = view || "overview";
  $$(".data-view-btn").forEach(button => button.classList.toggle("active", button.dataset.dataView === state.dataView));
  $$(".unit-data-view").forEach(panel => panel.classList.remove("active"));
  const panel = $(`#${state.dataView}DataView`);
  if (panel) panel.classList.add("active");
}

function addUnitDataRow(arrayName) {
  if (!state.unitData) return toast("No unit data is loaded.");
  try {
    collectUnitDataFromEditor();
  } catch (err) {
    return toast(`Unit data JSON error: ${err.message}`);
  }
  if (!Array.isArray(state.unitData[arrayName])) state.unitData[arrayName] = [];
  const defaults = {
    vocab: {word: "", ipa: "", kind: "unit word", meaning: "", example: "", note: "", icon: ""},
    lessons: {id: `l${state.unitData[arrayName].length + 1}`, title: "", aim: "", studyTitle: "", practice: "", image: "", style: "", audioKey: "", study: [], rule: "", tip: ""},
    watch: {speaker: "", text: "", audioKey: "", duration: 3}
  };
  state.unitData[arrayName].push(defaults[arrayName]);
  renderUnitData();
  setDataView(arrayName === "vocab" ? "vocab" : arrayName);
}

function renderImageOptions() {
  const images = (state.unitDetail?.files || []).filter(file => file.kind === "image").map(file => file.path);
  $("#unitImageOptions").innerHTML = images.map(path => `<option value="${escapeHtml(path)}"></option>`).join("");
  const media = (state.unitDetail?.files || [])
    .filter(file => file.kind === "audio" || file.kind === "video")
    .map(file => file.path);
  const mediaOptions = $("#unitMediaOptions");
  if (mediaOptions) mediaOptions.innerHTML = media.map(path => `<option value="${escapeHtml(path)}"></option>`).join("");
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Could not read file"));
    reader.readAsDataURL(file);
  });
}

function beginAssetImport(kind) {
  if (!state.selectedUnit) return toast("Select a unit first.");
  state.assetImportKind = kind;
  const input = $("#assetImportInput");
  input.accept = kind === "image" ? "image/*" : "audio/*,video/*";
  input.value = "";
  input.click();
}

async function handleAssetImportChange() {
  const input = $("#assetImportInput");
  const file = input.files?.[0];
  if (!file || !state.selectedUnit) return;
  const contentBase64 = await readFileAsDataUrl(file);
  const data = await api("/api/import-asset", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      root: state.root,
      unit: state.selectedUnit,
      filename: file.name,
      kind: state.assetImportKind,
      contentBase64
    })
  });
  state.unitDetail.files = data.files || state.unitDetail.files;
  state.unitDetail.validation = data.validation || state.unitDetail.validation;
  renderImageOptions();
  renderValidation(state.unitDetail.validation);
  if (data.asset.kind === "image") {
    $("#imagePathInput").value = data.asset.path;
    $("#newImagePath").value = data.asset.path;
  } else if (data.asset.kind === "audio" || data.asset.kind === "video") {
    $("#mediaSourceInput").value = data.asset.path;
  }
  markUnitDirty(`ZIP status: imported ${data.asset.kind} into unpacked cache; save back to source ZIP.`);
  toast(`Imported ${data.asset.path}`);
}

function renderZipStatus() {
  const box = $("#zipStatusBadge");
  if (!box) return;
  box.classList.remove("dirty", "saved");
  if (!state.selectedUnit) {
    box.textContent = "ZIP status: no unit selected.";
    return;
  }
  if (!state.unitDetail?.canSaveZip) {
    box.textContent = "ZIP status: folder unit; changes are saved directly in this folder.";
    box.classList.add("saved");
    return;
  }
  if (state.zipDirty) {
    box.textContent = state.zipStatusMessage || "ZIP status: saved in unpacked cache; not yet saved back to source ZIP.";
    box.classList.add("dirty");
  } else {
    box.textContent = state.zipStatusMessage || "ZIP status: ZIP-backed unit. Save back to source ZIP after editing.";
    box.classList.add("saved");
  }
}

function markUnitDirty(message = "") {
  if (state.unitDetail?.canSaveZip) {
    state.zipDirty = true;
    state.zipStatusMessage = message || "ZIP status: saved in unpacked cache; not yet saved back to source ZIP.";
    renderZipStatus();
  }
}

async function loadBackups() {
  const box = $("#backupDashboard");
  if (!box || !state.selectedUnit) return;
  try {
    const data = await api(`/api/backups?${currentRootQuery()}&unit=${encodeURIComponent(state.selectedUnit)}`);
    state.backups = data.backups || [];
  } catch (err) {
    state.backups = [];
    box.innerHTML = `<div class="empty-list">Could not load backups: ${escapeHtml(err.message)}</div>`;
    return;
  }
  renderBackupDashboard();
}

function renderBackupDashboard() {
  const box = $("#backupDashboard");
  if (!box) return;
  const backups = state.backups || [];
  if (!backups.length) {
    box.innerHTML = `<div class="empty-list">No backups yet. Saving edits creates restorable backups here.</div>`;
    return;
  }
  box.innerHTML = backups.slice(0, 80).map(item => `
    <div class="backup-row">
      <div class="backup-title">
        <span class="backup-path" title="${escapeHtml(item.path)}">${escapeHtml(item.path)}</span>
        <span>${escapeHtml(item.stamp)}</span>
      </div>
      <div class="backup-actions">
        <span class="meta">${fmtBytes(item.size)} · ${escapeHtml(item.modified)}</span>
        <button data-restore-backup="${escapeHtml(item.stamp)}" data-restore-path="${escapeHtml(item.path)}">Restore</button>
      </div>
    </div>
  `).join("");
}

async function restoreBackup(stamp, path) {
  if (!state.selectedUnit) return;
  if (!window.confirm(`Restore this backup over the current file?\n\n${path}\n${stamp}\n\nThe current file will be backed up first.`)) return;
  const data = await api("/api/restore-backup", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({root: state.root, unit: state.selectedUnit, stamp, path})
  });
  state.unitDetail.files = data.files || state.unitDetail.files;
  state.unitDetail.validation = data.validation || state.unitDetail.validation;
  state.backups = data.backups || [];
  renderFiles();
  renderCsvList();
  renderImageOptions();
  renderValidation(state.unitDetail.validation);
  renderBackupDashboard();
  markUnitDirty("ZIP status: backup restored in unpacked cache; save back to source ZIP.");
  if (state.openFile === data.restore.path) await openFile(state.openFile);
  if (state.openCsv === data.restore.path) await openCsv(state.openCsv);
  toast(`Restored ${data.restore.path}`);
}

function renderVisualSelection() {
  const info = state.visualSelection;
  if (!info) {
    $("#visualSelectedInfo").textContent = "Nothing selected";
    const textInput = $("#textValueInput");
    if (textInput) textInput.value = "";
    const mediaInput = $("#mediaSourceInput");
    if (mediaInput) mediaInput.value = "";
    const styleInput = $("#stylePresetSelect");
    if (styleInput) styleInput.value = "none";
    const linkInput = $("#linkHrefInput");
    if (linkInput) linkInput.value = "";
    return;
  }
  $("#visualSelectedInfo").textContent = `${info.tag || "element"} · ${info.text || info.src || info.selector}`;
  const textInput = $("#textValueInput");
  if (textInput) textInput.value = info.text || "";
  const mediaInput = $("#mediaSourceInput");
  if (mediaInput) mediaInput.value = (info.tag === "audio" || info.tag === "video" || info.tag === "source") ? (info.src || "") : "";
  const styleInput = $("#stylePresetSelect");
  if (styleInput) styleInput.value = info.style || "none";
  const linkInput = $("#linkHrefInput");
  if (linkInput) linkInput.value = info.href || "";
  if (info.tag === "img") {
    $("#imagePathInput").value = info.src || "";
    $("#imageAltInput").value = info.alt || "";
  }
}

function postToPreview(message) {
  const frame = $("#previewFrame");
  if (!frame || !frame.contentWindow) return false;
  frame.contentWindow.postMessage(message, "*");
  return true;
}

function queueVisualOp(op) {
  if (!op || !op.selector) return;
  state.visualOps.push(op);
  state.visualRedoOps = [];
  postToPreview({type: "flw-apply-visual-op", op});
  updateVisualEditStatus();
  renderVisualHistoryButtons();
}

function pendingVisualCount() {
  return state.visualOps.length + state.visualTextEdits.length;
}

function visualOpLabel(op) {
  const action = op?.action || (op?.html !== undefined ? "replaceHtml" : (op?.text !== undefined ? "setText" : "edit"));
  const labels = {
    replaceHtml: "Text",
    setText: "Text",
    setImage: "Image",
    setMedia: "Media",
    setLink: "Link",
    setBlockStyle: "Style",
    setCustomStyle: "Custom style",
    remove: "Remove",
    insertAfter: "Insert",
    moveToTop: "Move"
  };
  return labels[action] || action;
}

function visualOpSummary(op) {
  if (!op) return "";
  if (op.text !== undefined) return String(op.text).slice(0, 60);
  if (op.href !== undefined) return op.href;
  if (op.src !== undefined) return op.src;
  if (op.style !== undefined) return op.style;
  if (op.custom) return "custom block style";
  if (op.action === "remove") return "selected block";
  return op.selector || "";
}

function renderVisualHistoryList() {
  const box = $("#visualHistoryList");
  if (!box) return;
  const rows = [
    ...state.visualTextEdits.map(edit => ({...edit, action: edit.action || "replaceHtml"})),
    ...state.visualOps
  ];
  if (!rows.length && !state.visualRedoOps.length && !state.visualTextRedoAvailable) {
    box.textContent = "No visual edit history.";
    return;
  }
  const pending = rows.map((op, index) => `
    <div class="history-item">
      <span class="history-kind">${escapeHtml(visualOpLabel(op))}</span>
      <span title="${escapeHtml(op.selector || "")}">${escapeHtml(visualOpSummary(op))}</span>
    </div>
  `).join("");
  const redoCount = state.visualRedoOps.length + (state.visualTextRedoAvailable ? 1 : 0);
  box.innerHTML = `${pending}${redoCount ? `<div class="history-item"><span class="history-kind">Redo</span><span>${redoCount} available</span></div>` : ""}`;
}

function updateVisualEditStatus(prefix = "") {
  const count = pendingVisualCount();
  const redoCount = state.visualRedoOps.length + (state.visualTextRedoAvailable ? 1 : 0);
  const text = count
    ? `${count} pending visual edit${count === 1 ? "" : "s"}${redoCount ? ` · ${redoCount} redo available` : ""}.`
    : (redoCount ? `${redoCount} redo available.` : "No pending visual edits.");
  $("#visualEditStatus").textContent = prefix ? `${prefix} ${text}` : text;
}

function renderVisualHistoryButtons() {
  const undoButton = $("#undoVisualEditBtn");
  const redoButton = $("#redoVisualEditBtn");
  if (undoButton) undoButton.disabled = !state.visualEditActive || pendingVisualCount() === 0;
  if (redoButton) redoButton.disabled = !state.visualEditActive || (state.visualRedoOps.length === 0 && !state.visualTextRedoAvailable);
  renderVisualHistoryList();
}

function replayVisualOps(prefix = "") {
  state.visualReplayPending = true;
  state.visualSelection = null;
  renderVisualSelection();
  renderVisualHistoryButtons();
  if (prefix) $("#visualEditStatus").textContent = prefix;
  $("#previewFrame").src = previewUrl(true);
}

function undoVisualEdit() {
  if (!state.visualEditActive) return toast("Start visual edit first.");
  if (state.visualOps.length) {
    const op = state.visualOps.pop();
    state.visualRedoOps.push(op);
    replayVisualOps("Undo applied.");
    return;
  }
  if (state.visualTextEdits.length) {
    postToPreview({type: "flw-undo"});
    state.visualTextRedoAvailable = true;
    updateVisualEditStatus("Undo applied.");
    renderVisualHistoryButtons();
    return;
  }
  postToPreview({type: "flw-undo"});
  toast("Nothing to undo.");
  renderVisualHistoryButtons();
}

function redoVisualEdit() {
  if (!state.visualEditActive) return toast("Start visual edit first.");
  const op = state.visualRedoOps.pop();
  if (!op) {
    if (state.visualTextRedoAvailable) {
      postToPreview({type: "flw-redo"});
      state.visualTextRedoAvailable = false;
      updateVisualEditStatus("Redo applied.");
    } else {
      toast("Nothing to redo.");
    }
    renderVisualHistoryButtons();
    return;
  }
  state.visualOps.push(op);
  replayVisualOps("Redo applied.");
}

function requireSelection() {
  if (!state.visualEditActive) {
    toast("Start visual edit first.");
    return null;
  }
  if (!state.visualSelection?.selector) {
    toast("Click a block or image in the preview first.");
    return null;
  }
  return state.visualSelection;
}

function applySelectedImage() {
  const selection = requireSelection();
  if (!selection) return;
  if (selection.tag !== "img") return toast("Select an image first.");
  const src = $("#imagePathInput").value.trim().replaceAll("\\", "/");
  if (!src) return toast("Choose an image path first.");
  const op = {selector: selection.selector, action: "setImage", src, alt: $("#imageAltInput").value};
  queueVisualOp(op);
  state.visualSelection = {...selection, src, alt: op.alt};
  renderVisualSelection();
}

function applySelectedMedia() {
  const selection = requireSelection();
  if (!selection) return;
  if (!["audio", "video", "source"].includes(selection.tag)) return toast("Select an audio or video element first.");
  const src = $("#mediaSourceInput").value.trim().replaceAll("\\", "/");
  if (!src) return toast("Choose an audio/video source first.");
  const op = {selector: selection.selector, action: "setMedia", src};
  queueVisualOp(op);
  state.visualSelection = {...selection, src};
  renderVisualSelection();
}

function applySelectedText() {
  const selection = requireSelection();
  if (!selection) return;
  if (["img", "audio", "video", "source"].includes(selection.tag)) return toast("Select text or a button first.");
  const text = $("#textValueInput").value;
  queueVisualOp({selector: selection.selector, action: "setText", text});
  state.visualSelection = {...selection, text};
  renderVisualSelection();
}

function applySelectedLink() {
  const selection = requireSelection();
  if (!selection) return;
  const href = $("#linkHrefInput").value.trim();
  if (!href) return toast("Enter a link target first.");
  if (selection.tag !== "a" && !selection.href) return toast("Select a link/navigation item first.");
  queueVisualOp({selector: selection.selector, action: "setLink", href});
  state.visualSelection = {...selection, href};
  renderVisualSelection();
}

function applySelectedStyle() {
  const selection = requireSelection();
  if (!selection) return;
  const style = $("#stylePresetSelect").value || "none";
  if (style === "custom") return applySelectedCustomStyle();
  queueVisualOp({selector: selection.selector, action: "setBlockStyle", style});
  state.visualSelection = {...selection, style};
  renderVisualSelection();
}

function applySelectedCustomStyle() {
  const selection = requireSelection();
  if (!selection) return;
  const padding = Number($("#customStylePadding").value);
  const radius = Number($("#customStyleRadius").value);
  const custom = {
    background: $("#customStyleBg").value,
    borderColor: $("#customStyleBorder").value,
    padding: `${Number.isFinite(padding) ? Math.max(0, Math.min(80, padding)) : 14}px`,
    radius: `${Number.isFinite(radius) ? Math.max(0, Math.min(80, radius)) : 14}px`,
    shadow: $("#customStyleShadow").checked
  };
  queueVisualOp({selector: selection.selector, action: "setCustomStyle", custom});
  state.visualSelection = {...selection, style: "custom"};
  renderVisualSelection();
}

function toggleEditableMap() {
  if (!state.visualEditActive) return toast("Start visual edit first.");
  postToPreview({type: "flw-toggle-editable-map"});
}

function selectRelativeVisualTarget(direction) {
  if (!state.visualEditActive) return toast("Start visual edit first.");
  if (!state.visualSelection) return toast("Click something in the preview first.");
  postToPreview({type: "flw-select-relative", direction});
}

function removeSelectedBlock() {
  const selection = requireSelection();
  if (!selection) return;
  queueVisualOp({selector: selection.selector, action: "remove"});
  state.visualSelection = null;
  renderVisualSelection();
}

function duplicateSelectedBlock() {
  const selection = requireSelection();
  if (!selection) return;
  if (!selection.html) return toast("This selected item cannot be duplicated.");
  queueVisualOp({
    selector: selection.selector,
    action: "insertAfter",
    id: visualId("duplicate"),
    html: selection.html
  });
}

function moveSelectedBlockToTop() {
  const selection = requireSelection();
  if (!selection) return;
  queueVisualOp({
    selector: selection.selector,
    action: "moveToTop",
    id: visualId("move-top")
  });
}

function addTextBlockAfterSelection() {
  const selection = requireSelection();
  if (!selection) return;
  const title = $("#newBlockTitle").value.trim() || "New block";
  const text = $("#newBlockText").value.trim() || "Add your text here.";
  const html = `<section class="panel flw-custom-block"><div class="panel-title"><h2>${escapeHtml(title)}</h2></div><p>${escapeHtml(text)}</p></section>`;
  queueVisualOp({selector: selection.selector, action: "insertAfter", id: visualId("text"), html});
}

function addImageBlockAfterSelection() {
  const selection = requireSelection();
  if (!selection) return;
  const src = $("#newImagePath").value.trim().replaceAll("\\", "/");
  if (!src) return toast("Choose an image path first.");
  const caption = $("#newImageCaption").value.trim();
  const html = `<figure class="flw-custom-image-block"><img src="${escapeHtml(src)}" alt="${escapeHtml(caption)}">${caption ? `<figcaption>${escapeHtml(caption)}</figcaption>` : ""}</figure>`;
  queueVisualOp({selector: selection.selector, action: "insertAfter", id: visualId("image"), html});
}

function renderVisualEditToggle() {
  const button = $("#startVisualEditBtn");
  if (!button) return;
  const active = Boolean(state.visualEditActive);
  button.classList.toggle("active", active);
  button.textContent = active ? "■" : "✎";
  button.title = active ? "Stop visual editing" : "Start visual editing";
  button.setAttribute("aria-label", button.title);
}

function toggleVisualEditMode() {
  if (state.visualEditActive) {
    stopVisualEdit();
  } else {
    startVisualEdit();
  }
}

function startVisualEdit() {
  if (!state.selectedUnit) return toast("Select a unit first.");
  state.visualEditActive = true;
  state.visualSelection = null;
  state.visualOps = [];
  state.visualRedoOps = [];
  state.visualTextEdits = [];
  state.visualTextRedoAvailable = false;
  state.visualReplayPending = false;
  state.visualMapShown = false;
  $("#showEditableBtn").classList.remove("active");
  renderVisualSelection();
  $("#visualEditStatus").textContent = "Loading editable preview...";
  $("#saveVisualEditsBtn").disabled = false;
  renderVisualEditToggle();
  renderVisualHistoryButtons();
  $("#previewFrame").src = previewUrl(true);
}

function stopVisualEdit() {
  state.visualEditActive = false;
  $("#visualEditStatus").textContent = "Preview is read-only.";
  $("#saveVisualEditsBtn").disabled = true;
  state.visualMapShown = false;
  $("#showEditableBtn").classList.remove("active");
  renderVisualEditToggle();
  renderVisualHistoryButtons();
  postToPreview({type: "flw-disable-visual-edit"});
  $("#previewFrame").src = previewUrl(false);
}

function collectVisualEdits() {
  return new Promise((resolve, reject) => {
    state.visualEditResolver = resolve;
    state.visualEditRejecter = reject;
    if (!postToPreview({type: "flw-collect-visual-edits"})) {
      state.visualEditResolver = null;
      state.visualEditRejecter = null;
      reject(new Error("Editable preview is not ready."));
      return;
    }
    clearTimeout(window.visualEditTimer);
    window.visualEditTimer = setTimeout(() => {
      if (state.visualEditRejecter) {
        state.visualEditResolver = null;
        state.visualEditRejecter = null;
        reject(new Error("Timed out while collecting visual edits."));
      }
    }, 5000);
  });
}

async function saveVisualEdits() {
  if (!state.visualEditActive) return toast("Start visual edit first.");
  const textEdits = await collectVisualEdits();
  const textSupersedingSelectors = new Set(
    state.visualOps
      .filter(op => ["replaceHtml", "setText", "remove"].includes(op.action) || (!op.action && (op.html !== undefined || op.text !== undefined)))
      .map(op => op.selector)
  );
  const filteredTextEdits = textEdits.filter(edit => !textSupersedingSelectors.has(edit.selector));
  const edits = [...filteredTextEdits, ...state.visualOps];
  if (!edits.length) return toast("No visual changes found.");
  const response = await api("/api/visual-edits", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      root: state.root,
      unit: state.selectedUnit,
      mode: "merge",
      edits
    })
  });
  renderValidation(response.validation);
  await loadBackups();
  $("#visualEditStatus").textContent = `Saved ${response.count} visual edit patch${response.count === 1 ? "" : "es"}.`;
  markUnitDirty("ZIP status: visual edits saved in unpacked cache; save back to source ZIP.");
  state.visualOps = [];
  state.visualRedoOps = [];
  state.visualTextEdits = [];
  state.visualTextRedoAvailable = false;
  toast("Saved visual edits.");
  renderVisualHistoryButtons();
  $("#previewFrame").src = previewUrl(true);
}

async function clearVisualEdits() {
  if (!state.selectedUnit) return;
  const response = await api("/api/visual-edits", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      root: state.root,
      unit: state.selectedUnit,
      mode: "clear",
      edits: []
    })
  });
  renderValidation(response.validation);
  await loadBackups();
  markUnitDirty("ZIP status: visual edit patches changed in unpacked cache; save back to source ZIP.");
  state.visualOps = [];
  state.visualRedoOps = [];
  state.visualTextEdits = [];
  state.visualTextRedoAvailable = false;
  state.visualReplayPending = false;
  state.visualSelection = null;
  renderVisualSelection();
  renderVisualHistoryButtons();
  $("#visualEditStatus").textContent = "Cleared visual edit patches.";
  toast("Cleared visual edits.");
  $("#previewFrame").src = previewUrl(state.visualEditActive);
}

function handleVisualEditMessage(event) {
  const message = event.data || {};
  if (!String(message.type || "").startsWith("flw-visual-")) return;
  if (message.type === "flw-visual-ready") {
    $("#visualEditStatus").textContent = `Editable preview ready: ${message.count || 0} visible text items.`;
    if (state.visualEditActive) {
      postToPreview({type: "flw-enable-visual-edit"});
      if (state.visualReplayPending) {
        [...state.visualTextEdits, ...state.visualOps].forEach(op => postToPreview({type: "flw-apply-visual-op", op}));
      }
      if (state.visualReplayPending) {
        state.visualReplayPending = false;
        updateVisualEditStatus("History updated.");
      }
      renderVisualHistoryButtons();
    }
  }
  if (message.type === "flw-visual-enabled") {
    $("#visualEditStatus").textContent = `Editing ${message.count || 0} visible text items directly in preview.`;
    renderVisualHistoryButtons();
  }
  if (message.type === "flw-visual-selection") {
    state.visualSelection = message.selection || null;
    renderVisualSelection();
  }
  if (message.type === "flw-visual-map") {
    state.visualMapShown = Boolean(message.shown);
    $("#showEditableBtn").classList.toggle("active", state.visualMapShown);
    $("#visualEditStatus").textContent = state.visualMapShown
      ? `Showing ${message.count || 0} editable text/link items.`
      : "Editable text finder hidden.";
  }
  if (message.type === "flw-visual-text-change") {
    if (message.source === "input") {
      state.visualRedoOps = [];
      state.visualTextRedoAvailable = false;
    } else if (message.source === "undo") {
      state.visualTextRedoAvailable = true;
    } else if (message.source === "redo") {
      state.visualTextRedoAvailable = false;
    }
    const selector = message.edit?.selector || message.selection?.selector;
    if (message.edit?.selector) {
      const next = message.edit;
      const existing = state.visualTextEdits.findIndex(edit => edit.selector === next.selector);
      if (existing >= 0) {
        state.visualTextEdits[existing] = next;
      } else {
        state.visualTextEdits.push(next);
      }
    } else if (selector) {
      state.visualTextEdits = state.visualTextEdits.filter(edit => edit.selector !== selector);
    }
    if (message.selection) state.visualSelection = message.selection;
    renderVisualSelection();
    updateVisualEditStatus();
    renderVisualHistoryButtons();
  }
  if (message.type === "flw-visual-disabled") {
    $("#visualEditStatus").textContent = "Preview is read-only.";
  }
  if (message.type === "flw-visual-edits") {
    clearTimeout(window.visualEditTimer);
    state.visualTextEdits = message.edits || [];
    state.visualTextRedoAvailable = false;
    if (state.visualEditResolver) state.visualEditResolver(message.edits || []);
    state.visualEditResolver = null;
    state.visualEditRejecter = null;
    renderVisualHistoryButtons();
  }
}

async function validateSelected() {
  if (!state.selectedUnit) return;
  const data = await api("/api/validate", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({root: state.root, unit: state.selectedUnit})
  });
  if (state.unitDetail) state.unitDetail.validation = data.validation;
  renderValidation(data.validation);
  toast(data.validation.ok ? "Validation passed." : "Validation found issues.");
}

function renderValidation(validation) {
  if (!validation) {
    $("#validationSummary").textContent = "";
    renderBrokenAssetsDashboard(null);
    return;
  }
  const lines = [];
  lines.push(validation.ok ? "PASS" : "CHECK");
  lines.push(`Unit: ${validation.unit}`);
  lines.push(`Title: ${validation.title}`);
  lines.push(`Files: ${validation.stats.files}`);
  lines.push(`Images: ${validation.stats.images}`);
  lines.push(`Audio: ${validation.stats.audio}`);
  lines.push(`Video: ${validation.stats.video}`);
  if (validation.issues.length) {
    lines.push("");
    lines.push("Issues:");
    validation.issues.forEach(item => lines.push(`- ${item.message}`));
  }
  if (validation.warnings.length) {
    lines.push("");
    lines.push("Warnings:");
    validation.warnings.forEach(item => lines.push(`- ${item.message}`));
  }
  $("#validationSummary").textContent = lines.join("\n");
  renderBrokenAssetsDashboard(validation);
}

function replacementCandidatesFor(kind) {
  const files = state.unitDetail?.files || [];
  if (kind === "image") return files.filter(file => file.kind === "image").map(file => file.path);
  if (kind === "audio") return files.filter(file => file.kind === "audio").map(file => file.path);
  if (kind === "video") return files.filter(file => file.kind === "video").map(file => file.path);
  if (kind === "text") return files.filter(file => file.kind === "text").map(file => file.path);
  return files.filter(file => file.kind !== "binary").map(file => file.path);
}

function pathLeaf(path) {
  return String(path || "").split(/[\\/]/).pop().toLowerCase();
}

function pathExt(path) {
  const leaf = pathLeaf(path);
  const index = leaf.lastIndexOf(".");
  return index >= 0 ? leaf.slice(index) : "";
}

function rankedReplacementCandidates(item) {
  const missingLeaf = pathLeaf(item.ref);
  const missingExt = pathExt(item.ref);
  return replacementCandidatesFor(item.kind)
    .map(path => {
      const leaf = pathLeaf(path);
      let score = 0;
      if (leaf === missingLeaf) score += 100;
      if (missingLeaf && leaf.includes(missingLeaf.replace(/\.[^.]+$/, ""))) score += 35;
      if (missingExt && pathExt(path) === missingExt) score += 20;
      if (String(path).toLowerCase().includes(String(item.kind || "").toLowerCase())) score += 5;
      return {path, score};
    })
    .sort((a, b) => b.score - a.score || a.path.localeCompare(b.path))
    .map(item => item.path);
}

function assetPreviewHtml(path, kind) {
  if (!path) return `<span>No replacement selected.</span>`;
  const url = unitPreviewUrl(path);
  if (kind === "image") return `<img src="${escapeHtml(url)}" alt="${escapeHtml(path)}">`;
  if (kind === "audio") return `<audio controls src="${escapeHtml(url)}"></audio>`;
  if (kind === "video") return `<video controls src="${escapeHtml(url)}"></video>`;
  return `<span>${escapeHtml(path)}</span>`;
}

function renderBrokenAssetsDashboard(validation) {
  const box = $("#brokenAssetsDashboard");
  if (!box) return;
  const refs = validation?.missingRefs || [];
  if (!refs.length) {
    box.innerHTML = `<div class="empty-list">No broken local references found.</div>`;
    return;
  }
  box.innerHTML = refs.map((item, index) => {
    const candidates = rankedReplacementCandidates(item);
    const first = candidates[0] || "";
    const options = candidates.length
      ? candidates.map(path => `<option value="${escapeHtml(path)}">${escapeHtml(path)}</option>`).join("")
      : `<option value="">No ${escapeHtml(item.kind)} files found</option>`;
    return `
      <div class="broken-asset-row">
        <div class="broken-asset-title">
          <span class="broken-asset-ref" title="${escapeHtml(item.ref)}">${escapeHtml(item.ref)}</span>
          <span>${escapeHtml(item.kind)}</span>
        </div>
        <div class="broken-asset-actions">
          <select data-replace-ref="${escapeHtml(item.ref)}" ${candidates.length ? "" : "disabled"}>${options}</select>
          <button data-replace-ref-button="${escapeHtml(item.ref)}" ${candidates.length ? "" : "disabled"}>Replace</button>
        </div>
        <div class="asset-preview" data-asset-preview-for="${escapeHtml(item.ref)}">${assetPreviewHtml(first, item.kind)}</div>
      </div>
    `;
  }).join("");
}

function updateBrokenAssetPreview(select) {
  const ref = select?.dataset?.replaceRef;
  if (!ref) return;
  const item = (state.unitDetail?.validation?.missingRefs || []).find(refItem => refItem.ref === ref);
  const preview = $$("[data-asset-preview-for]", $("#brokenAssetsDashboard")).find(node => node.dataset.assetPreviewFor === ref);
  if (preview) preview.innerHTML = assetPreviewHtml(select.value, item?.kind || "link");
}

async function replaceBrokenReference(oldRef, newRef) {
  if (!state.selectedUnit) return;
  if (!oldRef || !newRef) return toast("Choose a replacement file first.");
  const data = await api("/api/replace-reference", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({root: state.root, unit: state.selectedUnit, oldRef, newRef})
  });
  state.unitDetail.files = data.files || state.unitDetail.files;
  state.unitDetail.validation = data.validation;
  renderValidation(data.validation);
  await loadBackups();
  markUnitDirty("ZIP status: broken reference fixed in unpacked cache; save back to source ZIP.");
  toast(`Replaced ${data.replace.count} reference${data.replace.count === 1 ? "" : "s"}.`);
}

function scormOptionsPayload() {
  return {
    root: state.root,
    unit: state.selectedUnit,
    title: $("#scormTitle").value.trim(),
    identifier: $("#scormIdentifier").value.trim(),
    exportDir: $("#exportDir").value.trim(),
    moodleUrl: $("#moodleUrl").value.trim(),
    moodlePhpPath: $("#moodlePhpPath").value.trim(),
    moodleConfigPath: $("#moodleConfigPath").value.trim(),
    flwImportMode: $("#flwImportMode")?.value || "overwrite",
    launchFile: $("#launchFile").value.trim() || "index.html",
    includeSourceData: $("#includeSourceData").checked,
    includeTools: $("#includeTools").checked,
    includeUnitSco: $("#includeUnitSco").checked,
    keepTopNavBar: $("#keepTopNavBar").checked,
    autocomplete: $("#autocomplete").checked
  };
}

function batchScormOptionsPayload() {
  const mode = $("#batchFlwImportMode")?.value || "overwrite";
  const dryRun = $("#batchDryRun").checked;
  return {
    ...scormOptionsPayload(),
    batchAllUnits: $("#batchAllUnits").checked,
    batchUnitStart: $("#batchUnitStart").value.trim(),
    batchUnitEnd: $("#batchUnitEnd").value.trim(),
    batchFlwImportMode: mode,
    batchProductionScope: $("#batchProductionScope")?.value || "",
    batchWorldScope: $("#batchWorldScope")?.value || "all",
    batchSpecificWorld: $("#batchSpecificWorld")?.value || "",
    flwDryRun: dryRun,
    batchPreviewStateHash: mode === "clear_add" && !dryRun ? state.batchRebuildPreviewHash : ""
  };
}

function batchProductionScopeLabel(value) {
  return value === "seven_world_production"
    ? "Current production: 7 worlds (Spanish out of scope)"
    : "All configured worlds";
}

function batchWorldOptionLabel(world) {
  const title = world?.worldTitle || world?.worldCode || world?.sourceRootCode || "World";
  const code = world?.sourceRootCode || "";
  return code ? `${title} (${code})` : title;
}

function populateBatchWorldOptions() {
  const select = $("#batchSpecificWorld");
  if (!select) return;
  const worlds = Array.isArray(state.config?.flwWorlds)
    ? state.config.flwWorlds.filter(world => world?.sourceRootCode)
    : [];
  const previous = select.value;
  select.innerHTML = worlds.map(world =>
    `<option value="${escapeHtml(world.sourceRootCode)}">${escapeHtml(batchWorldOptionLabel(world))}</option>`
  ).join("");
  if (worlds.some(world => world.sourceRootCode === previous)) select.value = previous;
}

function batchWorldScopeLabel(scope, specificWorld = "") {
  const normalized = scope || "all";
  if (normalized === "current") return "Currently selected world";
  if (normalized === "specific") {
    const world = (state.config?.flwWorlds || []).find(item => item?.sourceRootCode === specificWorld);
    return world ? batchWorldOptionLabel(world) : (specificWorld || "Specific world not selected");
  }
  return "All worlds in production scope";
}

function renderBatchControls() {
  const allUnits = $("#batchAllUnits")?.checked;
  const start = $("#batchUnitStart");
  const end = $("#batchUnitEnd");
  if (start) start.disabled = allUnits;
  if (end) end.disabled = allUnits;
  const worldScope = $("#batchWorldScope")?.value || "all";
  const specificLabel = $("#batchSpecificWorldLabel");
  const specificWorld = $("#batchSpecificWorld");
  if (specificLabel) specificLabel.hidden = worldScope !== "specific";
  if (specificWorld) specificWorld.disabled = worldScope !== "specific";
  const mode = $("#batchFlwImportMode")?.value || "overwrite";
  const dryRun = $("#batchDryRun")?.checked;
  const button = $("#batchImportToFlwBtn");
  if (button) {
    button.textContent = mode === "clear_add"
      ? (dryRun ? "Dry-run rebuild scope" : "Rebuild selected FLW scope")
      : "Batch deploy Unit SCORM";
  }
  const importDryRunButton = $("#importCompletedDryRunBtn");
  if (importDryRunButton) {
    importDryRunButton.title = dryRun
      ? "Imports packages from a previous completed dry-run using the current settings as a match."
      : "Imports packages from a previous completed dry-run without rebuilding them.";
  }
  renderMoodleTargetSummary("Current settings. Preview before importing to confirm the exact Moodle destination.");
}

function renderScormStructurePreview(structure) {
  const box = $("#scormStructurePreview");
  if (!box) return;
  if (!structure) {
    box.textContent = "Select a unit to preview the SCORM organization.";
    return;
  }
  const rows = (structure.scos || []).map((sco, index) => `
    <div class="sco-row">
      <div class="sco-kind">${escapeHtml(sco.kind)}</div>
      <div>
        <div>${index + 1}. ${escapeHtml(sco.title)}</div>
        <div class="sco-path">${escapeHtml(sco.launchFile)} · header ${sco.headerIncluded ? "included" : "not included"} · ${sco.filteredContent ? "filtered section content" : "whole unit content"}</div>
      </div>
    </div>
  `).join("");
  box.innerHTML = `
    <div>Unit ${escapeHtml(structure.unit)} · ${escapeHtml(structure.title)}</div>
    <div>Launch file: ${escapeHtml(structure.launchFile)} ${structure.launchFileExists ? "" : "(missing)"}</div>
    <div>SCOs: ${structure.scoCount} · Lessons: ${structure.lessonScoCount} · Sections: ${structure.sectionScoCount}</div>
    <div>Whole-unit SCO included: ${structure.includeUnitSco ? "yes" : "no"}</div>
    <div>Unit top nav bar: ${structure.keepTopNavBar ? "kept" : "hidden"}</div>
    <hr>
    ${rows || "<div>No section SCOs detected; export will fall back to a unit-level SCO.</div>"}
  `;
}

async function refreshScormStructurePreview(options = {}) {
  if (!state.selectedUnit) {
    renderScormStructurePreview(null);
    return;
  }
  const data = await api("/api/scorm-preview", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(scormOptionsPayload())
  });
  renderScormStructurePreview(data.structure);
  if (!options.silent) toast("SCORM structure preview refreshed.");
}

async function exportScorm() {
  if (!state.selectedUnit) return;
  if (!confirmUnsavedZipChanges("export SCORM using the current unpacked cache")) return;
  setExportResultLoading("Build SCORM zip", "Building package from the selected unit...");
  await refreshScormStructurePreview({silent: true});
  const payload = scormOptionsPayload();
  const data = await api("/api/export-scorm", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });
  await saveSettings({
    root: state.root,
    exportDir: payload.exportDir,
    moodleUrl: payload.moodleUrl,
    moodlePhpPath: payload.moodlePhpPath,
    moodleConfigPath: payload.moodleConfigPath
  });
  const exportLines = [
    "PASS",
    `Zip: ${data.export.zipPath}`,
    data.export.exportDirWarning ? `Warning: ${data.export.exportDirWarning}` : "",
    `Report: ${data.export.reportPath}`,
    `Files: ${data.export.fileCount}`,
    `Size: ${fmtBytes(data.export.zipBytes)}`,
    `Zip test: ${data.export.zipTest}`,
    `Manifest root: ${data.export.manifestAtRoot}`,
    `Manifest XML: ${data.export.manifestXmlOk}`,
    `Manifest items: ${data.export.manifestItemCount}`,
    `SCOs: ${data.export.scoCount}`,
    `Unit SCO: ${data.export.unitScoIncluded}`,
    `Unit top nav bar kept: ${data.export.keepTopNavBar}`,
    `Section SCOs: ${data.export.sectionScoCount}`,
    `Non-lesson SCOs: ${data.export.nonLessonScoCount}`,
    `Lesson SCOs: ${data.export.lessonScoCount}`,
    `Section pages filtered: ${data.export.sectionPagesFiltered ?? data.export.lessonPagesFiltered}`,
    `Course image source: ${data.export.courseImage?.packagePath || "(no usable image found)"}`,
    `SCORM script injected: ${data.export.scormScriptInjected}`
  ].join("\n");
  setExportResultFromText("SCORM package built", exportLines);
  toast("SCORM package built.");
}

function formatFlwImportResult(data) {
  const report = data.flw?.report || {};
  const summary = report.summary || {};
  const first = (report.results || [])[0] || {};
  const unitFirst = (report.unitResults || [])[0] || {};
  const single = report.singleImport || {};
  const flwUnit = single.flwUnit || {};
  const destination = single.moodleDestination || {};
  const planned = single.plannedAction || {};
  const history = single.historySafety || {};
  const publicStatus = single.publicStatus || summary.publicStatus || ((summary.failed || summary.conflictCount) ? "FAILED" : "");
  if (report.s6SingleImport || single.publicStatus) {
    const dryRun = Boolean(report.dryRun || data.flw?.dryRun || single.dryRun);
    const statusLine = dryRun
      ? `PREVIEW / DRY RUN — ${publicStatus || "READY"}`
      : (publicStatus === "UNCHANGED" ? "UNCHANGED" : ((summary.failed || summary.conflictCount) ? "DONE WITH ISSUES" : "PASS"));
    const courseLabel = destination.stageCourseName
      ? `${destination.stageCourseName}${destination.stageCourseKey ? ` (${destination.stageCourseKey})` : ""}`
      : (first.courseFullname || first.courseShortname || first.courseExternalKey || "(not resolved)");
    const sectionLabel = destination.unitSectionName
      ? `${destination.unitSectionName}${destination.unitSectionNumber != null ? ` (#${destination.unitSectionNumber})` : ""}`
      : (unitFirst.expectedSectionName || unitFirst.sectionName || "(not resolved)");
    const unitId = flwUnit.unitId || unitFirst.unitId || data.flw?.singleImportRequest?.unitId || "";
    const resultLines = [
      statusLine,
      dryRun ? "No Moodle changes were made." : "Single Unit SCORM deploy finished.",
      `Import mode: ${flwImportModeLabel(data.flw?.importMode || report.importMode || "overwrite")}`,
      flwImportModeDescription(data.flw?.importMode || report.importMode || "overwrite", false),
      "",
      "FLW Unit",
      `World: ${flwUnit.worldTitle || flwUnit.worldCode || first.worldTitle || first.worldCode || ""}`,
      flwUnit.sourceStage ? `Source Stage: ${flwUnit.sourceStage}` : "",
      `Deployment Stage: ${flwUnit.deploymentStageCode || first.deploymentStageCode || unitFirst.deploymentStageCode || ""}`,
      `Unit: ${unitId}`,
      `Unit Title: ${flwUnit.unitTitle || unitFirst.unitTitle || ""}`,
      "",
      "Moodle Destination",
      `Stage Course: ${courseLabel}`,
      `Course key: ${destination.stageCourseKey || first.courseExternalKey || unitFirst.courseExternalKey || ""}`,
      `Unit Section: ${sectionLabel}`,
      `Unit SCORM: ${destination.unitScormName || "Unit SCORM"}${unitFirst.cmid ? ` (activity ${unitFirst.cmid})` : ""}`,
      destination.unitScormUrl ? `Launch URL: ${destination.unitScormUrl}` : "",
      "",
      "Planned / Completed Action",
      `Course: ${planned.course || first.courseAction || first.status || "(not reported)"}`,
      `Course image: ${first.courseImage?.status || "(not reported)"}${first.courseImage?.unitId ? ` · ${first.courseImage.unitId}` : ""}${first.courseImage?.packageMember ? ` · ${first.courseImage.packageMember}` : ""}`,
      `Section: ${planned.section || unitFirst.sectionAction || unitFirst.status || "(not reported)"}`,
      `SCORM: ${planned.scorm || unitFirst.scormAction || "(not reported)"}`,
      `History Safety: ${history.deploymentStrategy || unitFirst.historyRisk || "New Unit SCORM"}`,
      history.learnerAttempts ? `Learner attempts: ${history.learnerAttempts}` : "",
      `Manual Moodle content: ${single.manualTeacherContent || unitFirst.manualTeacherContent || "preserved"}`,
      single.legacyWarning ? `Warning: ${single.legacyWarning}` : "",
      unitFirst.addNewAdvice ? `Next step: ${unitFirst.addNewAdvice}` : "",
      report.message ? `Message: ${report.message}` : (single.message ? `Message: ${single.message}` : ""),
      `Preview state: ${report.previewStateHash || data.flw?.previewStateHash || ""}`,
      "",
      `Zip: ${data.export?.zipPath || ""}`,
      `Export report: ${data.export?.reportPath || ""}`,
      `FLW manifest: ${data.flw?.manifestPath || ""}`,
      `FLW import report: ${data.flw?.reportPath || ""}`,
      `SCOs: ${data.export?.scoCount ?? ""}`,
      `Unit top nav bar kept: ${data.export?.keepTopNavBar ?? ""}`,
      `Failed: ${summary.failed ?? 0}`
    ];
    return resultLines.filter(Boolean).join("\n");
  }
  const course = first.courseFullname
    ? `${first.courseFullname}${first.courseShortname ? ` (${first.courseShortname})` : ""}`
    : first.courseId
      ? `Course ID ${first.courseId}`
      : "(not reported)";
  const lines = [
    (summary.failed || summary.conflictCount) ? "DONE WITH ISSUES" : "PASS",
    report.s5Only
      ? "Built SCORM package and deployed the canonical Unit SCORM activity into the resolved FLW Unit Section."
      : report.s4Only
      ? "Built SCORM package and resolved the FLW Stage Course + Unit Section. SCORM import is pending S5."
      : report.s3Only
        ? "Built SCORM package and resolved the FLW Stage Course. Unit Section/SCORM import is pending S4."
      : "Built SCORM package and imported it into FLW.",
    `Import mode: ${flwImportModeLabel(data.flw?.importMode || report.importMode || "overwrite")}`,
    `Moodle URL: ${data.flw?.moodleUrl || report.moodleUrl || ""}`,
    `Moodle PHP: ${data.flw?.moodlePhpPath || ""}`,
    `Moodle config: ${data.flw?.moodleConfigPath || ""}`,
    `Language: ${data.flw?.language || "(auto)"}${data.flw?.code ? ` (${data.flw.code})` : ""}`,
    `World / Stage: ${first.worldCode || unitFirst.worldCode || ""}:${first.deploymentStageCode || unitFirst.deploymentStageCode || ""}`,
    `Stage Course key: ${first.courseExternalKey || unitFirst.courseExternalKey || ""}`,
    `Target Moodle Course: ${course}`,
    (report.s4Only || report.s5Only) ? `Unit Section action: ${unitFirst.sectionAction || unitFirst.status || "(not reported)"}${unitFirst.sectionNumber != null ? ` (#${unitFirst.sectionNumber})` : ""}` : (report.s3Only ? `Future Unit action: ${first.futureUnitAction || unitFirst.futureUnitAction || "UNIT_SECTION_PENDING_S4"}` : `Section: ${report.sectionName || "(not reported)"}${first.sectionNumber != null ? ` (#${first.sectionNumber})` : ""}`),
    (report.s4Only || report.s5Only) ? `SCORM action: ${unitFirst.scormAction || first.futureScormAction || "SCORM_PENDING_S5"}` : "",
    unitFirst.historyRisk ? `History risk: ${unitFirst.historyRisk}` : "",
    `Course action: ${first.courseAction || first.status || "(not reported)"}`,
    `Course image: ${first.courseImage?.status || "(not reported)"}${first.courseImage?.unitId ? ` · ${first.courseImage.unitId}` : ""}`,
    (unitFirst.cmid || first.cmid) ? `Moodle activity cmid: ${unitFirst.cmid || first.cmid}` : "",
    (unitFirst.scormId || first.scormId) ? `Moodle SCORM id: ${unitFirst.scormId || first.scormId}` : "",
    (unitFirst.viewUrl || first.viewUrl) ? `Moodle URL: ${unitFirst.viewUrl || first.viewUrl}` : "",
    `Stage Courses reused: ${summary.reusedStageCourses ?? 0}`,
    `Stage Courses created: ${summary.createdStageCourses ?? summary.createdCourses ?? (report.createdCourses || []).length ?? 0}`,
    `Unit Sections created: ${summary.unitSectionsCreated ?? 0}`,
    `SCORM activities imported: ${summary.scormActivitiesImported ?? summary.imported ?? 0}`,
    data.export?.exportDirWarning ? `Warning: ${data.export.exportDirWarning}` : "",
    `Already exists: ${summary.alreadyExists ?? 0}`,
    `Failed: ${summary.failed ?? 0}`,
    `Zip: ${data.export.zipPath}`,
    `Export report: ${data.export.reportPath}`,
    `FLW manifest: ${data.flw?.manifestPath || ""}`,
    `FLW import report: ${data.flw?.reportPath || ""}`,
    `SCOs: ${data.export.scoCount}`,
    `Unit top nav bar kept: ${data.export.keepTopNavBar}`
  ];
  return lines.filter(Boolean).join("\n");
}

async function previewSingleFlwDestination(options = {}) {
  if (!state.selectedUnit) return null;
  if (options.checkUnsaved !== false && !confirmUnsavedZipChanges("preview this Unit's Moodle destination")) return null;
  const payload = {...scormOptionsPayload(), flwDryRun: true};
  const button = $("#previewFlwImportBtn");
  if (button) button.disabled = true;
  renderMoodleTargetSummary("Preview is resolving the exact Moodle course, unit section, and activity.");
  setExportResultLoading("Preview Moodle destination", "Building a temporary package and resolving the Moodle target...");
  try {
    await refreshScormStructurePreview({silent: true});
    const data = await api("/api/export-scorm-to-flw", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    state.singleFlwPreviewHash = data.flw?.report?.previewStateHash || "";
    await saveSettings({
      root: state.root,
      exportDir: payload.exportDir,
      moodleUrl: payload.moodleUrl,
      moodlePhpPath: payload.moodlePhpPath,
      moodleConfigPath: payload.moodleConfigPath
    });
    renderMoodleTargetSummaryFromSingle(data, "Resolved Moodle target for selected unit");
    setExportResultFromText("Moodle destination preview", formatFlwImportResult(data));
    if (!options.silent) toast("Moodle destination preview finished.");
    return data;
  } finally {
    if (button) button.disabled = false;
  }
}

async function exportScormToFlw() {
  if (!state.selectedUnit) return;
  if (!confirmUnsavedZipChanges("build and import SCORM into FLW")) return;
  const payload = scormOptionsPayload();
  const preview = await previewSingleFlwDestination({checkUnsaved: false, silent: true});
  if (!preview) return;
  const previewReport = preview.flw?.report || {};
  const previewSummary = previewReport.summary || {};
  const previewHash = previewReport.previewStateHash || "";
  const previewSingle = previewReport.singleImport || {};
  const previewActions = previewSingle.plannedAction || {};
  renderMoodleTargetSummaryFromSingle(preview, "Confirm this Moodle target before import");
  const message = [
    "Deploy this Unit SCORM to the Moodle destination shown in the preview?",
    "",
    `Moodle URL: ${payload.moodleUrl || "(default)"}`,
    `Moodle PHP: ${payload.moodlePhpPath || "(default)"}`,
    `Moodle config: ${payload.moodleConfigPath || "(default)"}`,
    `Import mode: ${flwImportModeLabel(payload.flwImportMode)}`,
    flwImportModeDescription(payload.flwImportMode, false),
    "",
    `Course action: ${previewActions.course || "(not reported)"}`,
    `Section action: ${previewActions.section || "(not reported)"}`,
    `SCORM action: ${previewActions.scorm || "(not reported)"}`,
    `Preview status: ${previewSingle.publicStatus || previewSummary.publicStatus || "READY"}`,
    "",
    previewSingle.legacyWarning || "",
    "Other Units and teacher-added Moodle content are preserved.",
    "Normal local export remains available with “Build SCORM zip”."
  ].join("\n");
  if (!window.confirm(message)) return;

  const button = $("#exportToFlwBtn");
  button.disabled = true;
  setExportResultLoading("Build + deploy selected unit", "Building the SCORM package and importing it into FLW...");
  try {
    await refreshScormStructurePreview({silent: true});
    const data = await api("/api/export-scorm-to-flw", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({...payload, previewStateHash: previewHash})
    });
    await saveSettings({
      root: state.root,
      exportDir: payload.exportDir,
      moodleUrl: payload.moodleUrl,
      moodlePhpPath: payload.moodlePhpPath,
      moodleConfigPath: payload.moodleConfigPath
    });
    renderMoodleTargetSummaryFromSingle(data, "Imported selected unit to this Moodle target");
    setExportResultFromText("Selected unit deployed", formatFlwImportResult(data));
    toast("FLW Unit SCORM deployed.");
  } finally {
    button.disabled = false;
  }
}

function formatBatchFlwResult(data) {
  const report = data.flw?.report || {};
  const summary = report.summary || {};
  const results = report.results || [];
  const unitRows = report.unitResults || [];
  const failed = Number(summary.failed ?? 0) + Number(data.exportFailedCount ?? 0);
  const header = failed > 0 ? "DONE WITH ISSUES" : "PASS";
  const mode = data.dryRun ? "Dry run - no Moodle changes created" : "Real Unit SCORM deployment";
  const languageLabels = (data.languageRoots || []).map(item => {
    const count = item.plannedUnitCount ?? item.unitCount;
    return `${item.label}${count != null ? ` (${count})` : ""}`;
  }).join(", ");
  const resultLines = results.map(row => {
    const lang = row.worldCode || row.label || row.language || "Stage";
    const unit = row.unitIds?.length ? ` ${row.unitIds[0]}${row.unitIds.length > 1 ? `-${row.unitIds[row.unitIds.length - 1]}` : ""}` : (row.unit ? ` U${row.unit}` : "");
    const course = row.courseShortname || row.courseFullname || (row.courseId ? `course ${row.courseId}` : "");
    const url = row.viewUrl ? ` · ${row.viewUrl}` : "";
    const courseImage = row.courseImage?.status ? ` · image ${row.courseImage.status}${row.courseImage.unitId ? ` from ${row.courseImage.unitId}` : ""}` : "";
    return `${lang}${unit}: ${row.courseAction || row.status || "unknown"}${course ? ` · ${course}` : ""}${courseImage}${url}`;
  });
  const unitLines = unitRows.map(row => {
    const course = row.courseExternalKey || (row.courseId ? `course ${row.courseId}` : "");
    const section = row.sectionNumber != null ? ` section ${row.sectionNumber}` : "";
    const scorm = row.scormAction ? ` · ${row.scormAction}` : "";
    return `${row.unitId || row.label || "Unit"}: ${row.sectionAction || row.status || "unknown"}${section}${course ? ` · ${course}` : ""}${scorm}`;
  });
  return [
    header,
    "Batch SCORM export / Unit SCORM deployment finished.",
    `Run mode: ${mode}`,
    `Import mode: ${flwImportModeLabel(data.importMode || data.flw?.importMode || report.importMode || "overwrite")}`,
    `Moodle URL: ${data.moodleUrl || data.flw?.moodleUrl || report.moodleUrl || ""}`,
    `Moodle PHP: ${data.flw?.moodlePhpPath || ""}`,
    `Moodle config: ${data.flw?.moodleConfigPath || ""}`,
    `Languages: ${languageLabels}`,
    data.catalogValidation ? `Production scope: ${batchProductionScopeLabel(data.catalogValidation.productionScope)}` : "",
    `World selection: ${formatBatchWorldSelection(data)}`,
    data.catalogValidation?.spanishReadinessStatus ? `Spanish readiness: ${data.catalogValidation.spanishReadinessStatus}` : "",
    `Units selected: ${formatBatchUnitSelection(data)}`,
    `Target rows: ${data.itemCount}`,
    `World/Stage groups: ${data.stageGroupCount ?? report.stageGroups?.length ?? 0}`,
    data.catalogValidation ? `Catalog expected/available/selected: ${data.catalogValidation.expectedTotal ?? 0}/${data.catalogValidation.availableValidTotal ?? 0}/${data.catalogValidation.selectedTotal ?? 0}` : "",
    `Packages exported: ${data.exportedCount}`,
    `Missing source units: ${data.missingCount}`,
    `Export failures: ${data.exportFailedCount}`,
    `Stage Courses reused: ${summary.reusedStageCourses ?? 0}`,
    `Stage Courses created: ${summary.createdStageCourses ?? summary.createdCourses ?? 0}`,
    `Stage Courses that would be created: ${summary.wouldCreateStageCourses ?? 0}`,
    `Course images set: ${summary.courseImagesSet ?? 0}`,
    `Course images updated: ${summary.courseImagesUpdated ?? 0}`,
    `Course images unchanged: ${summary.courseImagesUnchanged ?? 0}`,
    `Course images that would be set/updated: ${(summary.courseImagesWouldSet ?? 0) + (summary.courseImagesWouldUpdate ?? 0)}`,
    `Course images missing/pending/failures: ${summary.courseImagesMissing ?? 0}/${summary.courseImagesPendingExport ?? 0}/${summary.courseImageFailures ?? 0}`,
    `Unit Sections created: ${summary.unitSectionsCreated ?? 0}`,
    `Unit Sections reused: ${summary.reusedUnitSections ?? 0}`,
    `Unit Sections updated: ${summary.updatedUnitSections ?? 0}`,
    `Unit Sections reordered: ${summary.reorderedUnitSections ?? 0}`,
    `SCORM created: ${summary.scormCreated ?? 0}`,
    `SCORM updated: ${summary.scormUpdated ?? 0}`,
    `SCORM unchanged: ${summary.scormUnchanged ?? 0}`,
    `SCORM superseded: ${summary.scormSuperseded ?? 0}`,
    `SCORM diff needs exported package: ${summary.scormDiffRequiresPackage ?? 0}`,
    `SCORM activities imported: ${summary.scormActivitiesImported ?? summary.imported ?? 0}`,
    summary.s8Rebuild ? `S8 rebuild action counts: ${Object.entries(summary.s8Rebuild.actionCounts || {}).map(([key, value]) => `${key} ${value}`).join(", ")}` : "",
    summary.s8Rebuild ? `S8 historical SCORMs preserved: ${summary.s8Rebuild.historicalScormsPreserved ?? 0}` : "",
    summary.s8Rebuild ? `S8 manual objects preserved: ${summary.s8Rebuild.manualObjectsPreserved ?? 0}` : "",
    summary.s8Rebuild ? `S8 legacy courses detected: ${summary.s8Rebuild.legacyCoursesDetected ?? 0}` : "",
    `Units unchanged: ${summary.unitsUnchanged ?? 0}`,
    `Units blocked: ${summary.unitsBlocked ?? 0}`,
    `Units conflict: ${summary.unitsConflict ?? 0}`,
    `Units failed: ${summary.unitsFailed ?? summary.failed ?? 0}`,
    `Manual content preserved: ${summary.manualContentPreserved ?? 0}`,
    `Learner attempts/history preserved where applicable: ${summary.attemptsPreserved ?? 0}`,
    `Export folder: ${data.exportDir}`,
    data.exportDirWarning ? `Warning: ${data.exportDirWarning}` : "",
    `Batch manifest: ${data.manifestPath}`,
    `Moodle import report: ${data.flw?.reportPath || ""}`,
    "",
    ...resultLines,
    unitLines.length ? "" : null,
    ...unitLines
  ].filter(line => line !== null && line !== undefined).join("\n");
}

function formatBatchCoursePreview(data) {
  const preview = data.preview || {};
  const report = preview.report || {};
  const summary = report.summary || {};
  const rows = report.results || [];
  const unitRows = report.unitResults || [];
  const languageLabels = (data.languageRoots || []).map(item => {
    const count = item.plannedUnitCount ?? item.unitCount;
    return `${item.label}${count != null ? ` (${count})` : ""}`;
  }).join(", ");
  const lines = rows.map(row => {
    const unit = row.unitIds?.length ? ` ${row.unitIds[0]}${row.unitIds.length > 1 ? `-${row.unitIds[row.unitIds.length - 1]}` : ""}` : (row.unit ? ` U${row.unit}` : "");
    const course = row.courseShortname || row.courseFullname || "";
    const url = row.courseUrl ? ` · ${row.courseUrl}` : "";
    const reason = row.error || row.reason || "";
    const worldStage = row.worldCode ? `${row.worldCode}:${row.deploymentStageCode || ""}` : (row.label || row.language || "Stage");
    const conflicts = row.potentialConflicts?.length ? ` · ${row.potentialConflicts.length} legacy/conflict note(s)` : "";
    const courseImage = row.courseImage?.status ? ` · image ${row.courseImage.status}${row.courseImage.unitId ? ` from ${row.courseImage.unitId}` : ""}` : "";
    return `${worldStage}${unit}: ${row.courseAction || row.status || "unknown"}${course ? ` · ${course}` : ""}${courseImage}${reason ? ` · ${reason}` : ""}${conflicts}${url}`;
  });
  const unitLines = unitRows.map(row => {
    const course = row.courseExternalKey || (row.courseId ? `course ${row.courseId}` : "");
    const section = row.sectionNumber != null ? ` section ${row.sectionNumber}` : "";
    const scorm = row.scormAction ? ` · ${row.scormAction}` : "";
    return `${row.unitId || row.label || "Unit"}: ${row.sectionAction || row.status || "unknown"}${section}${course ? ` · ${course}` : ""}${scorm}`;
  });
  return [
    (summary.missingCourse || summary.missingSourceUnits || data.failureCount) ? "DONE WITH ISSUES" : "PASS",
    "Moodle Course / Unit-Section mapping preview finished.",
    `Import mode: ${flwImportModeLabel(data.importMode || preview.importMode || report.importMode || "overwrite")}`,
    "Hierarchy: FLW World → Deployment Stage / Moodle Course → FLW Unit / Moodle Section → Unit SCORM",
    `Moodle URL: ${preview.moodleUrl || report.moodleUrl || ""}`,
    `Moodle PHP: ${preview.moodlePhpPath || ""}`,
    `Moodle config: ${preview.moodleConfigPath || ""}`,
    `Languages: ${languageLabels}`,
    data.catalogValidation ? `Production scope: ${batchProductionScopeLabel(data.catalogValidation.productionScope)}` : "",
    `World selection: ${formatBatchWorldSelection(data)}`,
    data.catalogValidation?.spanishReadinessStatus ? `Spanish readiness: ${data.catalogValidation.spanishReadinessStatus}` : "",
    `Units selected: ${formatBatchUnitSelection(data)}`,
    data.catalogValidation ? `Catalog expected/available/selected: ${data.catalogValidation.expectedTotal ?? 0}/${data.catalogValidation.availableValidTotal ?? 0}/${data.catalogValidation.selectedTotal ?? 0}` : "",
    data.catalogValidation ? `Catalog missing/invalid: ${data.catalogValidation.missingOrInvalidTotal ?? 0} · extra available: ${data.catalogValidation.extraAvailableTotal ?? 0} · Spanish source present: ${data.catalogValidation.spanishSourcePresent ? "yes" : "no"}` : "",
    `Source rows: ${data.itemCount}`,
    `Source planned: ${data.plannedCount}`,
    `Source missing: ${data.missingCount}`,
    `Stage Course groups: ${summary.stageCourseCount ?? rows.length}`,
    `Reused Stage Courses: ${summary.reusedStageCourses ?? summary.mapped ?? 0}`,
    `Would create Stage Courses: ${summary.wouldCreateStageCourses ?? summary.wouldCreateCourse ?? 0}`,
    `Course images that would be set: ${summary.courseImagesWouldSet ?? 0}`,
    `Course images that would be updated: ${summary.courseImagesWouldUpdate ?? 0}`,
    `Course images unchanged: ${summary.courseImagesUnchanged ?? 0}`,
    `Course images pending Unit export: ${summary.courseImagesPendingExport ?? 0}`,
    `Course images missing/failures: ${summary.courseImagesMissing ?? 0}/${summary.courseImageFailures ?? 0}`,
    `Unit Sections planned: ${summary.unitSectionCount ?? 0}`,
    `Unit Sections reused: ${summary.reusedUnitSections ?? 0}`,
    `Would create Unit Sections: ${summary.wouldCreateUnitSections ?? 0}`,
    `Would update Unit Sections: ${summary.updatedUnitSections ?? 0}`,
    `Would reorder Unit Sections: ${summary.reorderedUnitSections ?? 0}`,
    `SCORM create planned: ${summary.scormCreated ?? 0}`,
    `SCORM update planned: ${summary.scormUpdated ?? 0}`,
    `SCORM unchanged: ${summary.scormUnchanged ?? 0}`,
    `SCORM supersede planned: ${summary.scormSuperseded ?? 0}`,
    `SCORM diff needs exported package: ${summary.scormDiffRequiresPackage ?? 0}`,
    `Legacy Unit Courses found: ${summary.legacyUnitCoursesFound ?? 0}`,
    `Conflicts/blockers: ${summary.conflictCount ?? summary.missingCourse ?? 0}`,
    summary.scormDiffRequiresPackage ? "Note: this preview does not export ZIPs; run Batch deploy with Dry run only for package-aware SCORM diffs." : "",
    `Preview report: ${preview.reportPath || ""}`,
    report.previewStateHash ? `Preview state hash: ${report.previewStateHash}` : "",
    data.exportDirWarning ? `Warning: ${data.exportDirWarning}` : "",
    "",
    ...lines,
    unitLines.length ? "" : null,
    ...unitLines
  ].join("\n");
}

async function previewBatchCourses() {
  const payload = batchScormOptionsPayload();
  const button = $("#previewBatchCoursesBtn");
  button.disabled = true;
  renderMoodleTargetSummary("Batch preview is resolving Moodle courses and unit sections.");
  setExportResultLoading("Preview batch Moodle mapping", "Resolving Moodle Course / Unit-Section mapping...");
  try {
    const data = await api("/api/batch-preview-flw-courses", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    await saveSettings({
      root: state.root,
      exportDir: payload.exportDir,
      moodleUrl: payload.moodleUrl,
      moodlePhpPath: payload.moodlePhpPath,
      moodleConfigPath: payload.moodleConfigPath
    });
    renderMoodleTargetSummaryFromBatchPreview(data);
    setExportResultFromText("Batch Moodle mapping preview", formatBatchCoursePreview(data));
    toast("Moodle Course / Unit-Section mapping preview finished.");
  } finally {
    button.disabled = false;
  }
}

function batchJobIsTerminal(job) {
  return ["complete", "completed_with_issues", "failed", "canceled", "interrupted"].includes(job?.status);
}

function batchJobCanResume(job) {
  if (!job) return false;
  if (job.status === "interrupted") return job.canResume !== false;
  return ["failed", "canceled"].includes(job.status);
}

function batchFailedUnitDetails(job) {
  const rows = job?.flw?.report?.unitResults || [];
  return rows.filter(row => {
    const status = String(row.unitResultStatus || row.scormStatus || row.scormAction || row.status || "").toUpperCase();
    return status.includes("FAILED") || status.includes("BLOCKED") || status.includes("CONFLICT");
  });
}

function formatBatchFailedUnit(row) {
  const unit = row.unitId || `${row.label || row.language || "Unit"}${row.unit ? ` U${row.unit}` : ""}`;
  const action = row.scormAction || row.scormStatus || row.sectionAction || row.status || "DEPLOYMENT_FAILED";
  const message = row.message || row.error || row.reason || "No detailed error was returned.";
  const target = [
    row.courseId ? `Moodle course ${row.courseId}` : "",
    row.cmid ? `activity cmid ${row.cmid}` : ""
  ].filter(Boolean).join(", ");
  return `${unit}: ${action} — ${message}${target ? ` (${target})` : ""}`;
}

function formatBatchJob(job) {
  if (!job) return "No batch job.";
  const progress = `${job.processedCount || 0}/${job.itemCount || 0} Units`;
  const languageLabels = (job.languageRoots || []).map(item => {
    const count = item.plannedUnitCount ?? item.unitCount;
    return `${item.label}${count != null ? ` (${count})` : ""}`;
  }).join(", ");
  const lines = [
    `Batch job: ${job.jobId}`,
    `Status: ${job.status || "unknown"} · Phase: ${job.phase || "unknown"}`,
    `Import mode: ${flwImportModeLabel(job.importMode || job.options?.batchFlwImportMode || job.flw?.importMode || "overwrite")}`,
    `Progress: ${progress}`,
    job.current ? `Current: ${job.current}` : "",
    `World/Stage groups: ${job.stageGroupCount ?? job.stageGroups?.length ?? 0}`,
    job.catalogValidation ? `Production scope: ${batchProductionScopeLabel(job.catalogValidation.productionScope)}` : "",
    job.catalogValidation?.spanishReadinessStatus ? `Spanish readiness: ${job.catalogValidation.spanishReadinessStatus}` : "",
    job.catalogValidation ? `Catalog expected/available/selected: ${job.catalogValidation.expectedTotal ?? 0}/${job.catalogValidation.availableValidTotal ?? 0}/${job.catalogValidation.selectedTotal ?? 0}` : "",
    `Packages exported: ${job.exportedCount || 0}`,
    languageLabels ? `Languages: ${languageLabels}` : "",
    `Units selected: ${formatBatchUnitSelection(job)}`,
    `Missing source units: ${job.missingCount || 0}`,
    `Export failures: ${job.exportFailedCount || 0}`,
    job.exportDir ? `Export folder: ${job.exportDir}` : "",
    job.exportDirWarning ? `Warning: ${job.exportDirWarning}` : "",
    job.manifestPath ? `Batch manifest: ${job.manifestPath}` : "",
    job.flwReportPath ? `Moodle import report: ${job.flwReportPath}` : "",
    job.flw?.report?.previewStateHash ? `Preview state hash: ${job.flw.report.previewStateHash}` : "",
    job.cancelPolicy ? `Cancel policy: ${job.cancelPolicy}` : "",
    job.cancelResult ? `Cancel result: ${job.cancelResult}` : "",
    job.interruptionReason ? `Interruption: ${job.interruptionReason}` : "",
    job.lastImporterOutput ? `Last completed import step: ${job.lastImporterOutput}` : "",
    job.status === "interrupted" ? `Reusable packages for Resume: ${job.resumeReusableExportCount || 0}/${job.itemCount || 0}` : "",
    job.status === "interrupted" && job.resumeWillReuseAllExports ? "Resume behavior: import-only; no SCORM packages will be rebuilt." : "",
    job.error ? `Error: ${job.error}` : ""
  ].filter(Boolean);
  if (job.flw?.report) {
    const summary = job.flw.report.summary || {};
    lines.push("");
    lines.push(`Stage Courses reused: ${summary.reusedStageCourses ?? 0}`);
    lines.push(`Stage Courses created: ${summary.createdStageCourses ?? summary.createdCourses ?? 0}`);
    lines.push(`Stage Courses that would be created: ${summary.wouldCreateStageCourses ?? 0}`);
    lines.push(`Course images set: ${summary.courseImagesSet ?? 0}`);
    lines.push(`Course images updated: ${summary.courseImagesUpdated ?? 0}`);
    lines.push(`Course images unchanged: ${summary.courseImagesUnchanged ?? 0}`);
    lines.push(`Course images that would be set/updated: ${(summary.courseImagesWouldSet ?? 0) + (summary.courseImagesWouldUpdate ?? 0)}`);
    lines.push(`Course images missing/pending/failures: ${summary.courseImagesMissing ?? 0}/${summary.courseImagesPendingExport ?? 0}/${summary.courseImageFailures ?? 0}`);
    lines.push(`Unit Sections created: ${summary.unitSectionsCreated ?? 0}`);
    lines.push(`Unit Sections reused: ${summary.reusedUnitSections ?? 0}`);
    lines.push(`Unit Sections updated: ${summary.updatedUnitSections ?? 0}`);
    lines.push(`Unit Sections reordered: ${summary.reorderedUnitSections ?? 0}`);
    lines.push(`SCORM created: ${summary.scormCreated ?? 0}`);
    lines.push(`SCORM updated: ${summary.scormUpdated ?? 0}`);
    lines.push(`SCORM unchanged: ${summary.scormUnchanged ?? 0}`);
    lines.push(`SCORM superseded: ${summary.scormSuperseded ?? 0}`);
    lines.push(`SCORM diff needs exported package: ${summary.scormDiffRequiresPackage ?? 0}`);
    lines.push(`SCORM activities imported: ${summary.scormActivitiesImported ?? summary.imported ?? 0}`);
    if (summary.s8Rebuild) {
      lines.push(`S8 rebuild action counts: ${Object.entries(summary.s8Rebuild.actionCounts || {}).map(([key, value]) => `${key} ${value}`).join(", ")}`);
      lines.push(`S8 historical SCORMs preserved: ${summary.s8Rebuild.historicalScormsPreserved ?? 0}`);
      lines.push(`S8 manual objects preserved: ${summary.s8Rebuild.manualObjectsPreserved ?? 0}`);
      lines.push(`S8 legacy courses detected: ${summary.s8Rebuild.legacyCoursesDetected ?? 0}`);
    }
    lines.push(`Units unchanged: ${summary.unitsUnchanged ?? 0}`);
    lines.push(`Units blocked: ${summary.unitsBlocked ?? 0}`);
    lines.push(`Units conflict: ${summary.unitsConflict ?? 0}`);
    lines.push(`Unit Moodle deployments failed: ${summary.unitsFailed ?? summary.failed ?? 0}`);
    lines.push(`Manual content preserved: ${summary.manualContentPreserved ?? 0}`);
    lines.push(`Learner attempts/history preserved where applicable: ${summary.attemptsPreserved ?? 0}`);
  }
  const failedUnits = batchFailedUnitDetails(job);
  if (failedUnits.length) {
    const blockedUnits = failedUnits.filter(row => String(row.unitResultStatus || "").toUpperCase() === "BLOCKED");
    lines.push("");
    lines.push(
      blockedUnits.length === failedUnits.length
        ? `Failure meaning: all selected SCORM ZIPs exported, but Moodle deployment was safely blocked before changes for ${failedUnits.length} Unit(s).`
        : Number(job.exportFailedCount || 0) === 0
        ? `Failure meaning: all selected SCORM ZIPs exported, but Moodle deployment failed for ${failedUnits.length} Unit(s).`
        : `Failure meaning: ${failedUnits.length} Unit(s) did not complete Moodle deployment; review export and Moodle errors below.`
    );
    lines.push("Failed Unit details:");
    failedUnits.slice(0, 25).forEach(row => lines.push(formatBatchFailedUnit(row)));
    if (failedUnits.length > 25) lines.push(`...and ${failedUnits.length - 25} more failed Unit(s). See the raw log or Moodle import report.`);
  }
  return lines.join("\n");
}

function setBatchButtons(running, job = state.lastBatchJob) {
  $("#batchImportToFlwBtn").disabled = running;
  const importDryRunButton = $("#importCompletedDryRunBtn");
  if (importDryRunButton) importDryRunButton.disabled = running;
  $("#cancelBatchJobBtn").disabled = !running;
  const resumeButton = $("#resumeBatchJobBtn");
  if (resumeButton) {
    resumeButton.disabled = running || (job ? !batchJobCanResume(job) : false);
    resumeButton.textContent = job?.status === "interrupted" ? "Resume interrupted import" : "Resume last batch";
  }
}

async function pollBatchJob(jobId) {
  clearTimeout(state.batchPollTimer);
  state.batchJobId = jobId;
  localStorage.setItem(LAST_BATCH_JOB_KEY, jobId);
  const data = await api(`/api/batch-job?jobId=${encodeURIComponent(jobId)}`);
  const job = data.job;
  state.lastBatchJob = job;
  renderMoodleTargetSummaryFromJob(job);
  setExportResultFromText("Batch job status", formatBatchJob(job), {
    status: batchJobIsTerminal(job) ? (job.status === "complete" ? "PASS" : job.status) : "RUNNING",
    preserveDisclosureState: true
  });
  const terminal = batchJobIsTerminal(job);
  const previewHash = job?.flw?.report?.previewStateHash;
  if (terminal && job?.importMode === "clear_add" && (job?.flw?.dryRun === true || job?.options?.flwDryRun === true) && previewHash) {
    state.batchRebuildPreviewHash = previewHash;
    localStorage.setItem(BATCH_REBUILD_PREVIEW_HASH_KEY, previewHash);
  }
  setBatchButtons(!terminal, job);
  if (!terminal) {
    state.batchPollTimer = setTimeout(() => pollBatchJob(jobId).catch(err => {
      setExportResultError(err, "Batch status refresh failed");
      toast(err.message);
      setBatchButtons(false);
    }), 1500);
  } else {
    toast(`Batch job ${job.status}.`);
  }
}

async function batchImportScormToFlw(options = {}) {
  const forceReuseDryRunExports = Boolean(options.reuseCompletedDryRunExports);
  if (!confirmUnsavedZipChanges(forceReuseDryRunExports ? "import completed dry-run SCORM packages into FLW" : "batch export SCORM packages and deploy FLW Unit SCORM activities")) return;
  const payload = batchScormOptionsPayload();
  if (forceReuseDryRunExports) payload.flwDryRun = false;
  if (forceReuseDryRunExports && payload.batchFlwImportMode === "clear_add" && !payload.batchPreviewStateHash) {
    payload.batchPreviewStateHash = state.batchRebuildPreviewHash || "";
  }
  const isRebuild = payload.batchFlwImportMode === "clear_add";
  if (isRebuild && !payload.flwDryRun && !payload.batchPreviewStateHash) {
    const message = "PREVIEW_REQUIRED: Run Rebuild Selected FLW Scope with Dry run only first. After the dry run finishes, uncheck Dry run only and run the real rebuild.";
    setExportResultPanel({
      title: "Batch rebuild preview required",
      status: "BLOCKED",
      message,
      summary: [{label: "Next step", value: "Run the rebuild dry-run first, then run the real rebuild."}],
      raw: message
    });
    toast("Run rebuild dry-run first.");
    return;
  }
  const reuseDryRunJobId = forceReuseDryRunExports ? await reusableCompletedDryRunJobId(payload) : "";
  const reuseCompletedDryRunExports = forceReuseDryRunExports && Boolean(reuseDryRunJobId);
  if (forceReuseDryRunExports && !reuseDryRunJobId) {
    const message = "No matching completed dry-run export job was found for the current batch settings.";
    renderMoodleTargetSummary("No reusable dry-run package set was found for the current settings.");
    setExportResultPanel({
      title: "Import completed dry-run packages",
      status: "NEEDS DRY RUN",
      message,
      summary: [
        {label: "Next step", value: "Run Batch deploy with Dry run only using these same settings, then click this button again."},
        {label: "Scope checked", value: batchScopeText(payload)}
      ],
      raw: message
    });
    toast("No matching completed dry-run packages found.");
    return;
  }
  const scope = batchScopeText(payload);
  setMoodleTargetSummary({
    title: reuseCompletedDryRunExports ? "Ready to import completed dry-run packages" : "Ready for batch build + deploy",
    message: "Confirm this run before Moodle is changed.",
    rows: [
      {label: "Moodle URL", value: payload.moodleUrl || "(default)"},
      {label: "Scope", value: scope},
      {label: "World selection", value: batchWorldScopeLabel(payload.batchWorldScope, payload.batchSpecificWorld)},
      {label: "Production scope", value: batchProductionScopeLabel(payload.batchProductionScope)},
      {label: "Run mode", value: payload.flwDryRun ? "Dry run only" : (reuseCompletedDryRunExports ? "Import existing completed dry-run packages" : "Build packages and deploy to Moodle")},
      {label: "Import mode", value: flwImportModeLabel(payload.batchFlwImportMode)},
      reuseCompletedDryRunExports ? {label: "Dry-run job", value: reuseDryRunJobId} : {label: "Dry-run job", value: "Not used by this button"}
    ]
  });
  const message = [
    isRebuild
      ? "Rebuild selected FLW scope in Moodle?"
      : (reuseCompletedDryRunExports
          ? "Import existing completed dry-run SCORM packages into Moodle?"
          : "Batch build SCORM packages and deploy FLW Unit SCORM activities in Moodle?"),
    "",
    `Moodle URL: ${payload.moodleUrl || "(default)"}`,
    `Moodle PHP: ${payload.moodlePhpPath || "(default)"}`,
    `Moodle config: ${payload.moodleConfigPath || "(default)"}`,
    `Scope: ${scope}`,
    `World selection: ${batchWorldScopeLabel(payload.batchWorldScope, payload.batchSpecificWorld)}`,
    `Production scope: ${batchProductionScopeLabel(payload.batchProductionScope)}`,
    `Run mode: ${payload.flwDryRun ? "dry run only" : (reuseCompletedDryRunExports ? "REAL import - reuse completed dry-run SCORM packages" : (isRebuild ? "REAL safe scoped rebuild" : "REAL build + deploy"))}`,
    `Import mode: ${flwImportModeLabel(payload.batchFlwImportMode)}`,
    flwImportModeDescription(payload.batchFlwImportMode, true),
    reuseCompletedDryRunExports ? `Reusing dry-run job: ${reuseDryRunJobId}` : "",
    isRebuild && !payload.flwDryRun ? `Preview state hash: ${payload.batchPreviewStateHash}` : "",
    "",
    isRebuild
      ? "The rebuild will resolve only the selected FLW scope, preserve Stage Courses and Unit Sections, preserve teacher content, rebuild no-history SCORMs safely, and supersede history-bearing SCORMs."
      : "The batch deploy will group selected Units by World+Stage, resolve each Moodle Course once, then create/reuse Unit Sections and create/update one canonical Unit SCORM activity in each section.",
    payload.batchProductionScope === "seven_world_production"
      ? "The editor will detect Adventure, Real, Russian, Chinese, German, Japanese, and French roots for the current production-readiness scope. Spanish support remains configured but out of this readiness run."
      : "The editor will detect Adventure, Real, Russian, Chinese, German, Japanese, Spanish, and French roots near the selected course root."
  ].filter(Boolean).join("\n");
  if (!window.confirm(message)) return;
  if (!payload.flwDryRun && !window.confirm(isRebuild
    ? "Real S8 rebuild will not delete Stage Courses, reset Moodle IDs, delete legacy Unit Courses, or delete learner history. History-bearing current SCORMs will be preserved as historical and replaced by a new current SCORM. Continue?"
    : "Real S7 may create missing Moodle Stage Courses, Unit Sections, and Unit SCORM activities. It will not clear Stage Courses or delete legacy Unit Courses. Continue?")) return;

  const button = reuseCompletedDryRunExports ? $("#importCompletedDryRunBtn") : $("#batchImportToFlwBtn");
  if (button) button.disabled = true;
  setBatchButtons(true);
  setExportResultLoading(
    reuseCompletedDryRunExports ? "Import completed dry-run packages" : "Batch deploy Unit SCORM",
    reuseCompletedDryRunExports
      ? "Starting Moodle import from completed dry-run SCORM packages..."
      : "Starting batch SCORM export / Unit SCORM deployment job..."
  );
  try {
    const endpoint = reuseCompletedDryRunExports ? "/api/resume-batch-job" : "/api/batch-export-scorm-to-flw";
    const requestPayload = reuseCompletedDryRunExports
      ? {...payload, jobId: reuseDryRunJobId, reuseCompletedDryRunExports: true}
      : payload;
    const data = await api(endpoint, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(requestPayload)
    });
    await saveSettings({
      root: state.root,
      exportDir: payload.exportDir,
      moodleUrl: payload.moodleUrl,
      moodlePhpPath: payload.moodlePhpPath,
      moodleConfigPath: payload.moodleConfigPath
    });
    const jobId = data.job?.jobId;
    if (!jobId) throw new Error("Batch job did not return a job id.");
    toast(reuseCompletedDryRunExports ? "Moodle import started from completed dry-run packages." : "Batch job started.");
    await pollBatchJob(jobId);
  } finally {
    if (!state.batchJobId) setBatchButtons(false);
  }
}

async function importCompletedDryRunPackages() {
  return batchImportScormToFlw({reuseCompletedDryRunExports: true});
}

async function cancelBatchJob() {
  const jobId = state.batchJobId || localStorage.getItem(LAST_BATCH_JOB_KEY);
  if (!jobId) return toast("No batch job to cancel.");
  await api("/api/cancel-batch-job", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({jobId})
  });
  toast("Cancel requested.");
  await pollBatchJob(jobId);
}

async function resumeBatchJob() {
  const jobId = state.batchJobId || localStorage.getItem(LAST_BATCH_JOB_KEY);
  if (!jobId) return toast("No previous batch job id was found.");
  let previousJob = state.lastBatchJob;
  if (!previousJob || previousJob.jobId !== jobId) {
    previousJob = (await api(`/api/batch-job?jobId=${encodeURIComponent(jobId)}`)).job;
  }
  if (!batchJobCanResume(previousJob)) {
    return toast(`Batch job cannot be resumed from status: ${previousJob?.status || "unknown"}.`);
  }
  const interrupted = previousJob.status === "interrupted";
  const realImport = previousJob.options?.flwDryRun === false;
  const confirmation = [
    interrupted ? "Resume the interrupted Moodle import?" : "Resume the previous batch job?",
    "",
    `Job: ${jobId}`,
    `Import mode: ${flwImportModeLabel(previousJob.importMode || previousJob.options?.batchFlwImportMode || "overwrite")}`,
    `Existing packages reusable: ${previousJob.resumeReusableExportCount ?? previousJob.exportedCount ?? 0}/${previousJob.itemCount || 0}`,
    interrupted && previousJob.resumeWillReuseAllExports ? "No SCORM packages will be exported again." : "Existing valid packages will be reused; only missing packages may be rebuilt.",
    realImport ? "This will continue making changes in Moodle and idempotently re-check items that completed before interruption." : "This is a dry-run resume."
  ].join("\n");
  if (!window.confirm(confirmation)) return;
  const payload = batchScormOptionsPayload();
  setBatchButtons(true, previousJob);
  setExportResultLoading(
    interrupted ? "Resume interrupted Moodle import" : "Resume batch job",
    interrupted ? "Reusing existing packages and re-checking Moodle state..." : "Resuming the previous batch job..."
  );
  const data = await api("/api/resume-batch-job", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({...payload, jobId})
  });
  const resumedId = data.job?.jobId || jobId;
  toast(interrupted ? "Interrupted import resumed using existing packages." : "Batch job resumed.");
  await pollBatchJob(resumedId);
}

async function saveBackToZip() {
  if (!state.selectedUnit || !state.unitDetail?.canSaveZip) {
    toast("This unit was not opened from a ZIP.");
    return;
  }
  const archivePath = state.unitDetail.archivePath;
  const message = [
    "Save the edited unpacked unit back into the original ZIP?",
    "",
    archivePath,
    "",
    "A timestamped backup of the current ZIP will be created first."
  ].join("\n");
  if (!window.confirm(message)) return;
  setExportResultLoading("Save back to source ZIP", "Writing the unpacked cache back into the original ZIP...");
  const data = await api("/api/repack-unit-zip", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({root: state.root, unit: state.selectedUnit})
  });
  const zipResult = [
    "PASS",
    "Saved edited unit back to source ZIP.",
    `Zip: ${data.zip.zipPath}`,
    `Backup: ${data.zip.backupPath}`,
    `Files written: ${data.zip.fileCount}`,
    `Preserved outside unit folder: ${data.zip.preservedOutsidePrefix}`,
    `Internal prefix: ${data.zip.internalPrefix || "(root)"}`,
    `Size: ${fmtBytes(data.zip.zipBytes)}`,
    `Zip test: ${data.zip.zipTest}`
  ].join("\n");
  setExportResultFromText("Source ZIP updated", zipResult);
  toast("Source ZIP updated.");
  state.zipDirty = false;
  state.zipStatusMessage = "ZIP status: saved back to original ZIP.";
  renderZipStatus();
  await loadUnits();
}

function switchTab(name) {
  $$(".tab").forEach(button => button.classList.toggle("active", button.dataset.tab === name));
  $$(".panel").forEach(panel => panel.classList.remove("active"));
  $(`#${name}Panel`).classList.add("active");
  if (name === "export") renderMoodleTargetSummary();
}

function moveUnitsToTop() {
  const sidebar = $(".sidebar");
  const unitList = $("#unitList");
  unitList.scrollTo({top: 0, behavior: "smooth"});
  sidebar.scrollIntoView({block: "start", behavior: "smooth"});
  $("#unitFilter").focus({preventScroll: true});
}

function renderVisualPanelFold() {
  const panel = $("#visualActionPanel");
  const previewPanel = $("#previewPanel");
  const button = $("#visualPanelToggleBtn");
  if (!panel || !previewPanel || !button) return;
  const open = Boolean(state.visualPanelOpen);
  panel.classList.toggle("is-folded", !open);
  panel.setAttribute("aria-hidden", String(!open));
  previewPanel.classList.toggle("visual-panel-folded", !open);
  button.classList.toggle("active", open);
  button.textContent = open ? "Hide edit panel" : "Edit panel";
  button.setAttribute("aria-expanded", String(open));
}

function clampVisualTogglePosition(left, top, button) {
  const margin = 8;
  const width = button.offsetWidth || 120;
  const height = button.offsetHeight || 40;
  return {
    left: Math.min(Math.max(margin, left), window.innerWidth - width - margin),
    top: Math.min(Math.max(margin, top), window.innerHeight - height - margin)
  };
}

function applySavedVisualTogglePosition() {
  const button = $("#visualPanelToggleBtn");
  if (!button) return;
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(VISUAL_PANEL_TOGGLE_POS_KEY) || "null");
  } catch (err) {
    saved = null;
  }
  if (!saved || !Number.isFinite(saved.left) || !Number.isFinite(saved.top)) return;
  const next = clampVisualTogglePosition(saved.left, saved.top, button);
  button.style.left = `${next.left}px`;
  button.style.top = `${next.top}px`;
  button.style.right = "auto";
  button.style.bottom = "auto";
}

function saveVisualTogglePosition(button) {
  const rect = button.getBoundingClientRect();
  localStorage.setItem(VISUAL_PANEL_TOGGLE_POS_KEY, JSON.stringify({left: rect.left, top: rect.top}));
}

function startVisualToggleDrag(event) {
  if (event.button !== undefined && event.button !== 0) return;
  const button = $("#visualPanelToggleBtn");
  if (!button) return;
  const rect = button.getBoundingClientRect();
  state.visualToggleDrag = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    left: rect.left,
    top: rect.top,
    moved: false
  };
  button.classList.add("is-dragging");
  button.setPointerCapture?.(event.pointerId);
}

function moveVisualToggleDrag(event) {
  const drag = state.visualToggleDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  const button = $("#visualPanelToggleBtn");
  if (!button) return;
  const dx = event.clientX - drag.startX;
  const dy = event.clientY - drag.startY;
  if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
  const next = clampVisualTogglePosition(drag.left + dx, drag.top + dy, button);
  button.style.left = `${next.left}px`;
  button.style.top = `${next.top}px`;
  button.style.right = "auto";
  button.style.bottom = "auto";
  event.preventDefault();
}

function endVisualToggleDrag(event) {
  const drag = state.visualToggleDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  const button = $("#visualPanelToggleBtn");
  state.visualToggleDrag = null;
  if (!button) return;
  button.classList.remove("is-dragging");
  button.releasePointerCapture?.(event.pointerId);
  if (drag.moved) {
    state.visualToggleSuppressClick = true;
    saveVisualTogglePosition(button);
    window.setTimeout(() => {
      state.visualToggleSuppressClick = false;
    }, 180);
  }
}

function toggleVisualPanel() {
  if (state.visualToggleSuppressClick) {
    state.visualToggleSuppressClick = false;
    return;
  }
  state.visualPanelOpen = !state.visualPanelOpen;
  renderVisualPanelFold();
}

function bindEvents() {
  $("#unitsToTopBtn").addEventListener("click", moveUnitsToTop);
  $("#visualPanelToggleBtn").addEventListener("click", toggleVisualPanel);
  $("#browseRoot").addEventListener("click", () => browseRootDirectory().catch(err => toast(err.message)));
  $("#browseExportDir").addEventListener("click", () => browseExportDirectory().catch(err => toast(err.message)));
  $("#refreshUnits").addEventListener("click", () => {
    if (!confirmUnsavedZipChanges("refresh units")) return;
    loadUnits().catch(err => toast(err.message));
  });
  $("#rootInput").addEventListener("keydown", event => {
    if (event.key === "Enter") {
      if (!confirmUnsavedZipChanges("change the course root")) return;
      loadUnits({saveRoot: true}).catch(err => toast(err.message));
    }
  });
  $("#rootInput").addEventListener("change", () => {
    if (!confirmUnsavedZipChanges("change the course root")) {
      $("#rootInput").value = state.root;
      return;
    }
    loadUnits({saveRoot: true}).catch(err => toast(err.message));
  });
  $("#exportDir").addEventListener("change", () => {
    const exportDir = $("#exportDir").value.trim();
    if (exportDir) saveSettings({exportDir}).catch(err => toast(err.message));
    renderMoodleTargetSummary();
  });
  $("#moodleUrl").addEventListener("change", () => {
    const moodleUrl = $("#moodleUrl").value.trim();
    if (moodleUrl) saveSettings({moodleUrl}).catch(err => toast(err.message));
    renderMoodleTargetSummary();
  });
  $("#moodlePhpPath").addEventListener("change", () => {
    const moodlePhpPath = $("#moodlePhpPath").value.trim();
    if (moodlePhpPath) saveSettings({moodlePhpPath}).catch(err => toast(err.message));
    renderMoodleTargetSummary();
  });
  $("#moodleConfigPath").addEventListener("change", () => {
    const moodleConfigPath = $("#moodleConfigPath").value.trim();
    if (moodleConfigPath) saveSettings({moodleConfigPath}).catch(err => toast(err.message));
    renderMoodleTargetSummary();
  });
  $("#unitFilter").addEventListener("input", renderUnits);
  $("#fileFilter").addEventListener("input", renderFiles);
  $("#unitList").addEventListener("click", event => {
    const button = event.target.closest("[data-unit]");
    if (button) selectUnit(button.dataset.unit).catch(err => toast(err.message));
  });
  $("#fileList").addEventListener("click", event => {
    const button = event.target.closest("[data-path]");
    if (button) openFile(button.dataset.path).catch(err => toast(err.message));
  });
  $("#csvList").addEventListener("click", event => {
    const button = event.target.closest("[data-csv]");
    if (button) openCsv(button.dataset.csv).catch(err => toast(err.message));
  });
  $("#csvGrid").addEventListener("click", event => {
    const button = event.target.closest("[data-delete-row]");
    if (!button) return;
    collectCsvGrid();
    state.csvRows.splice(Number(button.dataset.deleteRow), 1);
    renderCsvGrid();
  });
  $("#unitDataPanel").addEventListener("click", event => {
    const viewButton = event.target.closest("[data-data-view]");
    if (viewButton) setDataView(viewButton.dataset.dataView);
    const deleteButton = event.target.closest("[data-delete-array]");
    if (deleteButton && state.unitData) {
      try {
        collectUnitDataFromEditor();
      } catch (err) {
        toast(`Unit data JSON error: ${err.message}`);
        return;
      }
      const name = deleteButton.dataset.deleteArray;
      const index = Number(deleteButton.dataset.deleteIndex);
      if (Array.isArray(state.unitData[name])) {
        state.unitData[name].splice(index, 1);
        renderUnitData();
        setDataView(name === "vocab" ? "vocab" : name);
      }
    }
  });
  $("#saveFileBtn").addEventListener("click", () => saveFile().catch(err => toast(err.message)));
  $("#saveCsvBtn").addEventListener("click", () => saveCsv().catch(err => toast(err.message)));
  $("#addCsvRowBtn").addEventListener("click", addCsvRow);
  $("#saveUnitDataBtn").addEventListener("click", () => saveUnitData().catch(err => toast(err.message)));
  $("#addVocabBtn").addEventListener("click", () => addUnitDataRow("vocab"));
  $("#addLessonBtn").addEventListener("click", () => addUnitDataRow("lessons"));
  $("#addWatchBtn").addEventListener("click", () => addUnitDataRow("watch"));
  $("#startVisualEditBtn").addEventListener("click", toggleVisualEditMode);
  $("#undoVisualEditBtn").addEventListener("click", undoVisualEdit);
  $("#redoVisualEditBtn").addEventListener("click", redoVisualEdit);
  $("#showEditableBtn").addEventListener("click", toggleEditableMap);
  $("#selectParentBtn").addEventListener("click", () => selectRelativeVisualTarget("parent"));
  $("#selectChildBtn").addEventListener("click", () => selectRelativeVisualTarget("child"));
  $("#saveVisualEditsBtn").addEventListener("click", () => saveVisualEdits().catch(err => toast(err.message)));
  $("#clearVisualEditsBtn").addEventListener("click", () => clearVisualEdits().catch(err => toast(err.message)));
  $("#importImageBtn").addEventListener("click", () => beginAssetImport("image"));
  $("#importMediaBtn").addEventListener("click", () => beginAssetImport("media"));
  $("#assetImportInput").addEventListener("change", () => handleAssetImportChange().catch(err => toast(err.message)));
  $("#applyImageBtn").addEventListener("click", applySelectedImage);
  $("#applyMediaBtn").addEventListener("click", applySelectedMedia);
  $("#applyTextBtn").addEventListener("click", applySelectedText);
  $("#applyLinkBtn").addEventListener("click", applySelectedLink);
  $("#applyStyleBtn").addEventListener("click", applySelectedStyle);
  $("#applyCustomStyleBtn").addEventListener("click", applySelectedCustomStyle);
  $("#textValueInput").addEventListener("keydown", event => {
    if (event.key === "Enter") {
      event.preventDefault();
      applySelectedText();
    }
  });
  $("#linkHrefInput").addEventListener("keydown", event => {
    if (event.key === "Enter") {
      event.preventDefault();
      applySelectedLink();
    }
  });
  $("#removeBlockBtn").addEventListener("click", removeSelectedBlock);
  $("#duplicateBlockBtn").addEventListener("click", duplicateSelectedBlock);
  $("#moveBlockToTopBtn").addEventListener("click", moveSelectedBlockToTop);
  $("#addTextBlockBtn").addEventListener("click", addTextBlockAfterSelection);
  $("#addImageBlockBtn").addEventListener("click", addImageBlockAfterSelection);
  document.addEventListener("keydown", event => {
    if (!state.visualEditActive) return;
    if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
    const key = event.key.toLowerCase();
    if (key === "z" && event.shiftKey) {
      event.preventDefault();
      redoVisualEdit();
    } else if (key === "z") {
      event.preventDefault();
      undoVisualEdit();
    } else if (key === "y") {
      event.preventDefault();
      redoVisualEdit();
    }
  });
  window.addEventListener("message", handleVisualEditMessage);
  $("#brokenAssetsDashboard").addEventListener("click", event => {
    const button = event.target.closest("[data-replace-ref-button]");
    if (!button) return;
    const oldRef = button.dataset.replaceRefButton;
    const select = $$("[data-replace-ref]", $("#brokenAssetsDashboard")).find(item => item.dataset.replaceRef === oldRef);
    replaceBrokenReference(oldRef, select?.value || "").catch(err => toast(err.message));
  });
  $("#brokenAssetsDashboard").addEventListener("change", event => {
    const select = event.target.closest("[data-replace-ref]");
    if (select) updateBrokenAssetPreview(select);
  });
  $("#backupDashboard").addEventListener("click", event => {
    const button = event.target.closest("[data-restore-backup]");
    if (!button) return;
    restoreBackup(button.dataset.restoreBackup, button.dataset.restorePath).catch(err => toast(err.message));
  });
  $("#copyUnitBtn").addEventListener("click", openCopyUnitModal);
  $("#cancelCopyUnitBtn").addEventListener("click", closeCopyUnitModal);
  $("#confirmCopyUnitBtn").addEventListener("click", () => copySelectedUnit().catch(err => {
    $("#confirmCopyUnitBtn").disabled = false;
    toast(err.message);
  }));
  $("#copyTargetUnit").addEventListener("input", renderCopyModalSummary);
  $("#copyTitle").addEventListener("input", renderCopyModalSummary);
  $("#copyOutputType").addEventListener("change", renderCopyModalSummary);
  $("#copyUnitModal").addEventListener("click", event => {
    if (event.target.id === "copyUnitModal") closeCopyUnitModal();
  });
  $("#validateBtn").addEventListener("click", () => validateSelected().catch(err => toast(err.message)));
  $("#exportBtn").addEventListener("click", () => {
    switchTab("export");
    refreshScormStructurePreview({silent: true}).catch(err => toast(err.message));
  });
  $("#refreshScormPreviewBtn").addEventListener("click", () => refreshScormStructurePreview().catch(err => toast(err.message)));
  ["#scormTitle", "#launchFile", "#includeUnitSco", "#keepTopNavBar"].forEach(selector => {
    const control = $(selector);
    if (control) control.addEventListener("change", () => refreshScormStructurePreview({silent: true}).catch(err => toast(err.message)));
  });
  $("#runExportBtn").addEventListener("click", () => exportScorm().catch(err => {
    setExportResultError(err, "SCORM package build failed");
    toast(err.message);
  }));
  $("#previewFlwImportBtn").addEventListener("click", () => previewSingleFlwDestination().catch(err => {
    setExportResultError(err, "Moodle destination preview failed");
    toast(err.message);
  }));
  $("#exportToFlwBtn").addEventListener("click", () => exportScormToFlw().catch(err => {
    setExportResultError(err, "Selected unit deploy failed");
    toast(err.message);
  }));
  $("#batchAllUnits").addEventListener("change", renderBatchControls);
  $("#batchFlwImportMode").addEventListener("change", renderBatchControls);
  $("#batchDryRun").addEventListener("change", renderBatchControls);
  $("#batchProductionScope").addEventListener("change", renderBatchControls);
  $("#batchWorldScope").addEventListener("change", renderBatchControls);
  $("#batchSpecificWorld").addEventListener("change", renderBatchControls);
  $("#batchUnitStart").addEventListener("input", renderBatchControls);
  $("#batchUnitEnd").addEventListener("input", renderBatchControls);
  $("#flwImportMode").addEventListener("change", () => renderMoodleTargetSummary());
  $("#previewBatchCoursesBtn").addEventListener("click", () => previewBatchCourses().catch(err => {
    setExportResultError(err, "Batch Moodle mapping preview failed");
    toast(err.message);
  }));
  $("#batchImportToFlwBtn").addEventListener("click", () => batchImportScormToFlw().catch(err => {
    setExportResultError(err, "Batch deploy failed");
    toast(err.message);
    setBatchButtons(false);
  }));
  $("#importCompletedDryRunBtn").addEventListener("click", () => importCompletedDryRunPackages().catch(err => {
    setExportResultError(err, "Import completed dry-run packages failed");
    toast(err.message);
    setBatchButtons(false);
  }));
  $("#cancelBatchJobBtn").addEventListener("click", () => cancelBatchJob().catch(err => {
    setExportResultError(err, "Cancel batch failed");
    toast(err.message);
  }));
  $("#resumeBatchJobBtn").addEventListener("click", () => resumeBatchJob().catch(err => {
    setExportResultError(err, "Resume batch failed");
    toast(err.message);
  }));
  $("#saveBackZipBtn").addEventListener("click", () => saveBackToZip().catch(err => {
    setExportResultError(err, "Save back to source ZIP failed");
    toast(err.message);
  }));
  $$(".tab").forEach(button => button.addEventListener("click", () => switchTab(button.dataset.tab)));
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !$("#copyUnitModal").hidden) closeCopyUnitModal();
  });
  window.addEventListener("beforeunload", event => {
    if (!hasUnsavedZipChanges()) return;
    event.preventDefault();
    event.returnValue = "";
  });
}

async function init() {
  bindEvents();
  renderVisualPanelFold();
  renderVisualEditToggle();
  renderBatchControls();
  await loadConfig();
  await loadUnits();
}

init().catch(err => toast(err.message));
