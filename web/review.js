const studyDatasetUrl = "../data/parsed/study_app_dataset.json";
const ocrDatasetUrl = "../data/parsed/hardsub_ocr.json";
const reviewApiUrl = "../api/hardsub-review";
const reviewStorageKey = "subtitle-prototype-public-review-drafts-v1";

const state = {
  studyItems: [],
  ocrRecords: [],
  reviewRows: new Map(),
  currentIndex: 0,
  filter: "all",
  query: "",
  apiAvailable: true,
};

const els = {
  reviewMeta: document.querySelector("#reviewMeta"),
  reviewList: document.querySelector("#reviewList"),
  reviewSearchInput: document.querySelector("#reviewSearchInput"),
  reviewPositionLabel: document.querySelector("#reviewPositionLabel"),
  reviewStatusLabel: document.querySelector("#reviewStatusLabel"),
  reviewVideoPlayer: document.querySelector("#reviewVideoPlayer"),
  cropImage: document.querySelector("#cropImage"),
  playReviewVideoButton: document.querySelector("#playReviewVideoButton"),
  copyAsrButton: document.querySelector("#copyAsrButton"),
  copyOcrButton: document.querySelector("#copyOcrButton"),
  reviewTimeLabel: document.querySelector("#reviewTimeLabel"),
  ocrStatusText: document.querySelector("#ocrStatusText"),
  asrText: document.querySelector("#asrText"),
  ocrText: document.querySelector("#ocrText"),
  correctedText: document.querySelector("#correctedText"),
  chineseTextReview: document.querySelector("#chineseTextReview"),
  reviewNotes: document.querySelector("#reviewNotes"),
  saveDraftButton: document.querySelector("#saveDraftButton"),
  approveButton: document.querySelector("#approveButton"),
  markProblemButton: document.querySelector("#markProblemButton"),
  nextReviewButton: document.querySelector("#nextReviewButton"),
  filterButtons: [...document.querySelectorAll(".filter-button")],
};

function currentRecord() {
  return state.ocrRecords[state.currentIndex];
}

function studyFor(record) {
  return state.studyItems.find((item) => Number(item.index) === Number(record.index)) || {};
}

function rowFor(record) {
  return state.reviewRows.get(String(record.index)) || {};
}

function visibleRecords() {
  const query = state.query.trim().toLowerCase();
  return state.ocrRecords.filter((record) => {
    const row = rowFor(record);
    const approved = row.approved === "yes";
    const problem = row.approved === "problem";
    const statusMatches =
      state.filter === "all" ||
      (state.filter === "todo" && !approved && !problem) ||
      (state.filter === "approved" && approved) ||
      (state.filter === "problem" && problem);
    const text = `${record.ocr_japanese_text} ${record.asr_japanese_text} ${record.chinese_text}`.toLowerCase();
    return statusMatches && (!query || text.includes(query));
  });
}

function setCurrent(index) {
  const realIndex = state.ocrRecords.findIndex((record) => Number(record.index) === Number(index));
  if (realIndex >= 0) {
    state.currentIndex = realIndex;
    render();
  }
}

function renderList() {
  const records = visibleRecords();
  const current = currentRecord();
  els.reviewList.innerHTML = "";

  records.forEach((record) => {
    const row = rowFor(record);
    const approved = row.approved === "yes";
    const problem = row.approved === "problem";
    const button = document.createElement("button");
    button.className = `sentence-item ${record.index === current?.index ? "current" : ""}`;
    button.type = "button";
    button.innerHTML = `
      <strong>${record.index}. ${escapeHtml(row.corrected_japanese_text || record.asr_japanese_text || "(empty)")}</strong>
      <span>${escapeHtml(record.chinese_text || "")}</span>
      <span>${record.start} - ${record.end} · ${approved ? "approved" : problem ? "problem" : "todo"}</span>
    `;
    button.addEventListener("click", () => setCurrent(record.index));
    els.reviewList.appendChild(button);
  });
}

function renderDetail() {
  const record = currentRecord();
  if (!record) return;

  const study = studyFor(record);
  const row = rowFor(record);
  const approved = row.approved === "yes";
  const problem = row.approved === "problem";
  const corrected = row.corrected_japanese_text ?? (record.asr_japanese_text || record.ocr_japanese_text || "");

  els.reviewPositionLabel.textContent = `${record.index} / ${state.ocrRecords.length}`;
  els.reviewStatusLabel.textContent = approved ? "approved" : problem ? "problem" : state.apiAvailable ? "todo" : "local fallback";
  els.reviewTimeLabel.textContent = `${record.start} - ${record.end}`;
  els.ocrStatusText.textContent = `${record.ocr_backend} · ${record.ocr_status}`;
  els.reviewVideoPlayer.src = study.video_src ? `../${study.video_src}` : "";
  els.cropImage.src = `../${record.crop_image}`;
  els.asrText.value = record.asr_japanese_text || "";
  els.ocrText.value = record.ocr_japanese_text || "";
  els.correctedText.value = corrected;
  els.chineseTextReview.value = record.chinese_text || "";
  els.reviewNotes.value = row.notes || "";
}

function renderFilters() {
  els.filterButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.filter === state.filter);
  });
}

function render() {
  renderFilters();
  renderList();
  renderDetail();
}

async function saveCurrent(approvedValue) {
  const record = currentRecord();
  if (!record) return false;
  const payload = {
    index: Number(record.index),
    corrected_japanese_text: els.correctedText.value.trim(),
    approved: approvedValue === "yes", review_state: approvedValue,
    notes: els.reviewNotes.value.trim(),
  };
  if (payload.approved && !payload.corrected_japanese_text) {
    els.reviewStatusLabel.textContent = "Approval needs non-empty corrected text";
    return false;
  }
  els.approveButton.disabled = true;
  try {
    const response = await fetch(reviewApiUrl, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    if (!result.saved_to_csv || !result.row || (payload.approved && result.row.approved !== "yes")) {
      throw new Error("Server did not confirm the CSV write");
    }
    state.apiAvailable = true;
    state.reviewRows.set(String(record.index), result.row);
    const fallback = loadFallbackRows();
    fallback.delete(String(record.index));
    localStorage.setItem(reviewStorageKey, JSON.stringify([...fallback.entries()]));
    renderList();
    els.reviewStatusLabel.textContent = payload.approved ? "approved and saved to CSV" : "draft saved to CSV";
    return true;
  } catch (error) {
    state.apiAvailable = false;
    const draft = { ...rowFor(record), index: String(record.index),
      corrected_japanese_text: payload.corrected_japanese_text, approved: "",
      notes: payload.notes, browser_only: true };
    const fallback = loadFallbackRows();
    fallback.set(String(record.index), draft);
    localStorage.setItem(reviewStorageKey, JSON.stringify([...fallback.entries()]));
    state.reviewRows.set(String(record.index), draft);
    renderList();
    els.reviewStatusLabel.textContent = "CSV save failed — browser draft only; not approved";
    console.warn(error);
    return false;
  } finally {
    els.approveButton.disabled = false;
  }
}

function goNext() {
  state.currentIndex = Math.min(state.currentIndex + 1, state.ocrRecords.length - 1);
  render();
}

function saveFallbackRows() {
  localStorage.setItem(reviewStorageKey, JSON.stringify([...state.reviewRows.entries()]));
}

function loadFallbackRows() {
  try {
    return new Map(JSON.parse(localStorage.getItem(reviewStorageKey) || "[]").map(([key, row]) => [key, { ...row, approved: "", browser_only: true }]));
  } catch {
    return new Map();
  }
}

async function loadReviewRows() {
  try {
    const response = await fetch(reviewApiUrl);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    state.apiAvailable = true;
    return new Map((data.rows || []).map((row) => [String(row.index), row]));
  } catch (error) {
    state.apiAvailable = false;
    console.warn(error);
    return loadFallbackRows();
  }
}

function bindEvents() {
  els.filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      state.filter = button.dataset.filter;
      render();
    });
  });

  els.reviewSearchInput.addEventListener("input", (event) => {
    state.query = event.target.value;
    renderList();
  });

  els.playReviewVideoButton.addEventListener("click", () => {
    els.reviewVideoPlayer.currentTime = 0;
    els.reviewVideoPlayer.play();
  });

  els.copyAsrButton.addEventListener("click", () => {
    els.correctedText.value = els.asrText.value;
    els.correctedText.focus();
  });

  els.copyOcrButton.addEventListener("click", () => {
    els.correctedText.value = els.ocrText.value;
    els.correctedText.focus();
  });

  els.saveDraftButton.addEventListener("click", () => saveCurrent(""));
  els.approveButton.addEventListener("click", async () => {
    if (await saveCurrent("yes")) goNext();
  });
  els.markProblemButton.addEventListener("click", () => saveCurrent("problem"));
  els.nextReviewButton.addEventListener("click", goNext);

  window.addEventListener("keydown", (event) => {
    if (event.target.matches("input, textarea")) return;
    if (event.key === " ") {
      event.preventDefault();
      els.playReviewVideoButton.click();
    }
    if (event.key === "ArrowDown") goNext();
    if (event.key === "ArrowUp") {
      state.currentIndex = Math.max(state.currentIndex - 1, 0);
      render();
    }
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function init() {
  bindEvents();
  const [studyResponse, ocrResponse, reviewRows] = await Promise.all([
    fetch(studyDatasetUrl),
    fetch(ocrDatasetUrl),
    loadReviewRows(),
  ]);
  const studyDataset = await studyResponse.json();
  const ocrDataset = await ocrResponse.json();

  state.studyItems = studyDataset.items || [];
  state.ocrRecords = ocrDataset.records || [];
  state.reviewRows = reviewRows;
  els.reviewMeta.textContent = `${ocrDataset.record_count} records · ${state.apiAvailable ? "CSV save" : "browser drafts only"} · demo_fixture is not model output`;
  render();
}

init().catch((error) => {
  console.error(error);
  els.reviewMeta.textContent = "Failed to load OCR review data";
});
