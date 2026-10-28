const datasetUrl = "../data/parsed/study_app_dataset.json";
const storageKey = "subtitle-prototype-public-progress-v1";

const state = {
  dataset: null,
  items: [],
  currentIndex: 0,
  filter: "all",
  query: "",
  progress: loadProgress(),
};

const els = {
  datasetMeta: document.querySelector("#datasetMeta"),
  exportButton: document.querySelector("#exportButton"),
  searchInput: document.querySelector("#searchInput"),
  sentenceList: document.querySelector("#sentenceList"),
  positionLabel: document.querySelector("#positionLabel"),
  qualityLabel: document.querySelector("#qualityLabel"),
  timeLabel: document.querySelector("#timeLabel"),
  reviewLabel: document.querySelector("#reviewLabel"),
  japaneseText: document.querySelector("#japaneseText"),
  chineseText: document.querySelector("#chineseText"),
  videoPlayer: document.querySelector("#videoPlayer"),
  audioPlayer: document.querySelector("#audioPlayer"),
  playButton: document.querySelector("#playButton"),
  audioButton: document.querySelector("#audioButton"),
  reviewButton: document.querySelector("#reviewButton"),
  knownButton: document.querySelector("#knownButton"),
  fixButton: document.querySelector("#fixButton"),
  tokenList: document.querySelector("#tokenList"),
  analyzerLabel: document.querySelector("#analyzerLabel"),
  noteInput: document.querySelector("#noteInput"),
  filterButtons: [...document.querySelectorAll(".filter-button")],
};

function loadProgress() {
  try {
    return JSON.parse(localStorage.getItem(storageKey) || "{}");
  } catch {
    return {};
  }
}

function saveProgress() {
  localStorage.setItem(storageKey, JSON.stringify(state.progress));
}

function progressFor(item) {
  if (!state.progress[item.id]) {
    state.progress[item.id] = { status: "review", note: "" };
  }
  return state.progress[item.id];
}

function visibleItems() {
  const query = state.query.trim().toLowerCase();
  return state.items.filter((item) => {
    const progress = progressFor(item);
    const statusMatches = state.filter === "all" || progress.status === state.filter;
    const text = `${item.japanese_text} ${item.chinese_text}`.toLowerCase();
    return statusMatches && (!query || text.includes(query));
  });
}

function setCurrentById(id) {
  const index = state.items.findIndex((item) => item.id === id);
  if (index >= 0) {
    state.currentIndex = index;
    render();
  }
}

function currentItem() {
  return state.items[state.currentIndex];
}

function setStatus(status) {
  const item = currentItem();
  if (!item) return;
  progressFor(item).status = status;
  saveProgress();
  render();
}

function renderList() {
  const items = visibleItems();
  els.sentenceList.innerHTML = "";

  items.forEach((item) => {
    const progress = progressFor(item);
    const button = document.createElement("button");
    button.className = `sentence-item ${item.id === currentItem()?.id ? "current" : ""}`;
    button.type = "button";
    button.dataset.id = item.id;
    button.innerHTML = `
      <strong>${item.index}. ${escapeHtml(item.japanese_text || "(empty)")}</strong>
      <span>${escapeHtml(item.chinese_text || "")}</span>
      <span>${item.start} · ${progress.status}</span>
    `;
    button.addEventListener("click", () => setCurrentById(item.id));
    els.sentenceList.appendChild(button);
  });
}

function renderDetail() {
  const item = currentItem();
  if (!item) return;

  const progress = progressFor(item);
  els.positionLabel.textContent = `${item.index} / ${state.items.length}`;
  els.qualityLabel.textContent = `${item.source_quality} · ${item.nlp_reliability}`;
  els.timeLabel.textContent = `${item.start} - ${item.end}`;
  els.reviewLabel.textContent = progress.status;
  els.japaneseText.textContent = item.japanese_text || "(no ASR text)";
  els.chineseText.textContent = item.chinese_text || "";
  els.videoPlayer.src = item.video_src ? `../${item.video_src}` : "";
  els.videoPlayer.hidden = !item.video_src;
  els.audioPlayer.src = `../${item.audio_src}`;
  els.noteInput.value = progress.note || "";
  els.analyzerLabel.textContent = item.is_true_morphological_analysis ? item.analyzer : `${item.analyzer} preview`;

  els.tokenList.innerHTML = "";
  item.tokens.forEach((token) => {
    const div = document.createElement("div");
    div.className = `token ${token.is_particle_candidate ? "particle" : ""}`;
    div.innerHTML = `
      <b>${escapeHtml(token.surface)}</b>
      <em>${escapeHtml(token.meaning_zh || "待查")}</em>
      <small>${escapeHtml(token.script_type)} · ${escapeHtml(token.lookup_status || token.pos)}</small>
    `;
    els.tokenList.appendChild(div);
  });
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

function exportProgress() {
  const rows = [["id", "status", "note"]];
  Object.entries(state.progress).forEach(([id, value]) => {
    rows.push([id, value.status || "", value.note || ""]);
  });
  const csv = rows.map((row) => row.map(csvCell).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "study_progress.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function csvCell(value) {
  const text = String(value).replaceAll('"', '""');
  return `"${text}"`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function bindEvents() {
  els.filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      state.filter = button.dataset.filter;
      render();
    });
  });

  els.searchInput.addEventListener("input", (event) => {
    state.query = event.target.value;
    renderList();
  });

  els.playButton.addEventListener("click", () => {
    if (els.videoPlayer.src) {
      els.videoPlayer.currentTime = 0;
      els.videoPlayer.play();
      return;
    }
    els.audioPlayer.currentTime = 0;
    els.audioPlayer.play();
  });

  els.audioButton.addEventListener("click", () => {
    els.audioPlayer.currentTime = 0;
    els.audioPlayer.play();
  });

  els.reviewButton.addEventListener("click", () => setStatus("review"));
  els.knownButton.addEventListener("click", () => setStatus("known"));
  els.fixButton.addEventListener("click", () => setStatus("fix"));
  els.exportButton.addEventListener("click", exportProgress);

  els.noteInput.addEventListener("input", () => {
    const item = currentItem();
    if (!item) return;
    progressFor(item).note = els.noteInput.value;
    saveProgress();
  });

  window.addEventListener("keydown", (event) => {
    if (event.target.matches("input, textarea")) return;
    if (event.key === " ") {
      event.preventDefault();
      els.playButton.click();
    }
    if (event.key === "ArrowDown") {
      state.currentIndex = Math.min(state.currentIndex + 1, state.items.length - 1);
      render();
    }
    if (event.key === "ArrowUp") {
      state.currentIndex = Math.max(state.currentIndex - 1, 0);
      render();
    }
  });
}

async function init() {
  bindEvents();
  const response = await fetch(datasetUrl);
  state.dataset = await response.json();
  state.items = state.dataset.items || [];
  document.querySelector("#sourceNote").textContent = state.dataset.source_note || "";
  els.datasetMeta.textContent = `${state.dataset.record_count} records · local prototype`;
  render();
}

init().catch((error) => {
  console.error(error);
  els.datasetMeta.textContent = "Failed to load dataset";
  els.japaneseText.textContent = "Could not load study_app_dataset.json";
});
