// The offcard panel for Windows, in a web view: the card, three chevrons, the drive, then HDR Merge
// and a one-line footer. It follows the Mac panel (mac/Sources/Panel.swift, Choose.swift, HDR.swift)
// state for state and word for word, on the same local engine API. The app around it (the tray,
// the window, the engine) is desktop/src-tauri; in a browser, desktop/dev.py stands in for it.

"use strict";
const TAURI = window.__TAURI__ && window.__TAURI__.core;
const call = (cmd, args) => TAURI ? TAURI.invoke(cmd, args) : Promise.resolve(null);

async function api(path, body) {
  if (TAURI) return TAURI.invoke("api", { path, body: body === undefined ? null : body });
  const r = await fetch(path, body === undefined ? {} : { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
  const json = await r.json().catch(() => ({}));
  if (!r.ok) throw json.error || "Something went wrong.";
  return json;
}

// ---- small formatters, like the Mac's
const num = n => Number(n || 0).toLocaleString("en-US");
const plural = (n, word) => `${num(n)} ${word}${n === 1 ? "" : "s"}`;
const esc = t => String(t ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const GB = 1073741824, MB = 1048576, KB = 1024;
function human(n) {
  n = n || 0;
  if (n >= GB) return (n / GB).toFixed(2) + " GB";
  if (n >= MB) return (n / MB).toFixed(1) + " MB";
  if (n >= KB) return Math.round(n / KB) + " KB";
  return n + " B";
}
function amountOf(done, total) {
  const [u, d, name] = total >= GB ? [GB, 2, "GB"] : total >= MB ? [MB, 1, "MB"] : [KB, 0, "KB"];
  return `${(done / u).toFixed(d)} of ${(total / u).toFixed(d)} ${name}`;
}
function counts(p, v) {
  const parts = [p > 0 && plural(p, "photo"), v > 0 && plural(v, "video")].filter(Boolean);
  return parts.length ? parts.join(" and ") : "nothing";
}
const first = t => t.charAt(0).toUpperCase() + t.slice(1);
const pieces = path => String(path || "").split(/[\\/]/).filter(Boolean);
function dayTitle(key) {
  return /^\d{2}[A-Z][a-z]{2}\d{2}$/.test(key) ? `${+key.slice(0, 2)} ${key.slice(2, 5)} 20${key.slice(5)}` : key;
}
function dayRange(keys) {
  const a = keys[0] || "", b = keys[keys.length - 1] || "";
  if (a.length !== 7 || b.length !== 7) return "";
  return a.slice(2, 5) === b.slice(2, 5) ? `${+a.slice(0, 2)}–${+b.slice(0, 2)} ${a.slice(2, 5)}` : `${+a.slice(0, 2)} ${a.slice(2, 5)} – ${+b.slice(0, 2)} ${b.slice(2, 5)}`;
}
/** The drive, and the folder on it (null when the folder is the drive itself). */
function place(path) {
  const parts = pieces(path);
  if (String(path).startsWith("\\\\")) {          // a network share: \\nas\Photo\Sony Backup
    return { drive: parts[1] || parts[0], folder: parts.length > 2 ? parts[parts.length - 1] : null };
  }
  if (/^[A-Za-z]:$/.test(parts[0] || "")) {
    const letter = parts[0].toUpperCase();
    const same = s.dest && pieces(s.dest)[0]?.toUpperCase() === letter;
    const drive = letter === "C:" ? "This PC" : (same && s.dest_label) || `Drive ${letter}`;
    return { drive, folder: parts.length > 1 ? parts[parts.length - 1] : null };
  }
  const drive = parts[0] === "Volumes" && parts.length > 1 ? parts[1] : "This Mac";
  const last = parts[parts.length - 1];
  return { drive, folder: last && last !== drive ? last : null };
}
const placeName = path => { const p = place(path); return p.folder ? `${p.drive} › ${p.folder}` : p.drive; };

// ---- glyphs
const svg = (w, h, inner) => `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" fill="none" aria-hidden="true">${inner}</svg>`;
const stroke = (d, w = 1.5) => `<path d="${d}" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;
const I = {
  card: svg(16, 18, `<path d="M3 1.5h7L14 5.5V15a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 15V3A1.5 1.5 0 0 1 3 1.5Z" fill="currentColor"/>`),
  cardOut: svg(16, 18, `<path d="M3 1.5h7L14 5.5V15a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 15V3A1.5 1.5 0 0 1 3 1.5Z" stroke="currentColor" stroke-width="1.4"/>`),
  drive: svg(20, 14, `<rect x="1" y="1.5" width="18" height="11" rx="2.5" stroke="currentColor" stroke-width="1.5"/><circle cx="15" cy="7" r="1.1" fill="currentColor"/>${stroke("M4.5 7h5")}`),
  check: svg(18, 14, stroke("M1.5 7.5 6.5 12 16.5 2", 2.2)),
  computer: svg(20, 16, `<rect x="1" y="1" width="18" height="11" rx="1.6" stroke="currentColor" stroke-width="1.5"/>${stroke("M7 15h6M10 12v3")}`),
  network: svg(18, 18, `<circle cx="9" cy="9" r="7.8" stroke="currentColor" stroke-width="1.4"/><ellipse cx="9" cy="9" rx="3.4" ry="7.8" stroke="currentColor" stroke-width="1.2"/>${stroke("M1.5 6.5h15M1.5 11.5h15", 1.2)}`),
  folder: svg(13, 11, `<path d="M1 2.2C1 1.5 1.5 1 2.2 1h2.6l1.3 1.3h4.7c.7 0 1.2.5 1.2 1.2v5.3c0 .7-.5 1.2-1.2 1.2H2.2C1.5 9.8 1 9.3 1 8.6Z" fill="var(--ter)"/>`),
  folderBig: svg(18, 15, `<path d="M1.5 3C1.5 2 2.2 1.5 3 1.5h3.6l1.8 1.8H15c.9 0 1.5.6 1.5 1.5v7.2c0 .9-.6 1.5-1.5 1.5H3c-.8 0-1.5-.6-1.5-1.5Z" stroke="currentColor" stroke-width="1.4"/>`),
  down: svg(10, 6, stroke("M1 1l4 4 4-4")),
  updown: svg(8, 11, stroke("M1 4l3-3 3 3M1 7l3 3 3-3", 1.2)),
  pencil: svg(11, 11, `<path d="M1.5 9.5l.5-2.3 5.6-5.6 1.8 1.8L3.8 9Z" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/>`),
  hdr: svg(16, 14, `<circle cx="5.5" cy="7" r="4.5" stroke="currentColor" stroke-width="1.2" opacity=".5"/><circle cx="8" cy="7" r="4.5" stroke="currentColor" stroke-width="1.2" opacity=".75"/><circle cx="10.5" cy="7" r="4.5" stroke="currentColor" stroke-width="1.2"/>`),
  arrow: svg(12, 13, stroke("M6 1v11M1.5 7.5 6 12l4.5-4.5", 1.7)),
  tick: svg(10, 8, stroke("M1 4l2.8 2.8L9 1.2", 1.5)),
  dash: svg(10, 2, stroke("M1 1h8", 1.6)),
  left: svg(7, 12, stroke("M6 1 1 6l5 5", 1.8)),
  right: svg(6, 10, stroke("M1 1l4 4-4 4", 1.5)),
  dots: svg(14, 4, `<circle cx="2" cy="2" r="1.4" fill="currentColor"/><circle cx="7" cy="2" r="1.4" fill="currentColor"/><circle cx="12" cy="2" r="1.4" fill="currentColor"/>`),
  chev: svg(28, 16, [3, 11, 19].map(x => stroke(`M${x} 2.5 ${x + 5.5} 8 ${x} 13.5`, 2)).join("")),
  menuTick: svg(12, 9, stroke("M1 4.5 4.5 8 11 1", 1.4)),
  photo: svg(20, 16, `<rect x="1" y="1" width="18" height="14" rx="2" stroke="currentColor" stroke-width="1.3"/><circle cx="6.5" cy="5.5" r="1.5" fill="currentColor"/>${stroke("M2 13l5-4 3 2.5 3.5-3.5L18 12", 1.3)}`),
  video: svg(20, 14, `<rect x="1" y="1" width="13" height="12" rx="2" fill="currentColor"/><path d="M15 5.5 19 3v8l-4-2.5Z" fill="currentColor"/>`),
  play: svg(5, 6, `<path d="M0 0l5 3-5 3Z" fill="currentColor"/>`),
};
const tile = (name, big) => {
  const size = big ? 40 : 28;
  const parts = [0, 1, 2].map(i => `<rect x="${size * (.22 + i * .19)}" y="${size * (.33 - i * .03)}" width="${size * .26}" height="${size * .34}" rx="${size * .07}" fill="currentColor" opacity="${[.3, .6, .95][i]}"/>`).join("");
  return `<span class="gl ${name}" ${big ? 'style="width:40px;height:40px"' : ""}>${svg(size, size, parts)}</span>`;
};

// ---- what the app knows
let s = {}, ready = false, failure = null, note = null, pollTimer = null;
let path = [];               // the pages over the backup page, deepest last
let editing = null, tagText = "";  // the day whose tag is being typed, and what's typed
let menu = null;             // the open menu: its items and the element it hangs from
let loginOn = false;
let lastPlan = null, lastKey = "", hdrLooked = "", lastBackup = "";
const choice = { files: [], chosen: null, thumbs: {}, planID: -1, asked: new Set() };
const hdr = { sets: null, selected: new Set(), tiff: false, merging: [], failed: {}, lastMerged: null, note: null, mergeStart: 0, seenJob: -1, opened: false, folder: null };

const running = () => s.job?.state === "running" || s.hdr_job?.state === "running";
const job = () => s.job || {};
const allIds = () => choice.files.map(f => f.id);
const picked = () => choice.chosen || new Set(allIds());
const everything = () => !choice.chosen || choice.chosen.size === choice.files.length;
const isOn = id => picked().has(id);
function setChoice(ids, on) {
  const p = new Set(picked());
  ids.forEach(i => on ? p.add(i) : p.delete(i));
  choice.chosen = p.size === choice.files.length ? null : p;
}
function only(keep) {
  const p = new Set(choice.files.filter(keep).map(f => f.id));
  choice.chosen = p.size === choice.files.length ? null : p;
}
const fileCount = f => Math.max(1, (f.names || []).length);
const chosenCount = ids => choice.files.filter(f => (ids || picked()).has(f.id)).reduce((n, f) => n + fileCount(f), 0);
const chosenBytes = ids => choice.files.filter(f => (ids || picked()).has(f.id)).reduce((n, f) => n + f.size, 0);
const totalFiles = () => choice.files.reduce((n, f) => n + fileCount(f), 0);

// ---- what the app does on its own as the engine's state changes
let applyingUpdate = false;
function update() {
  if (s.update_job?.state === "ready" && !running() && !applyingUpdate) {
    applyingUpdate = true;      // the new version is checked and waiting: swap it in and quit
    api("/api/update/apply", {}).then(() => call("quit")).catch(() => { applyingUpdate = false; });
  }
  const j = job(), cards = (s.cards || []).map(c => c.path).sort();
  const k = JSON.stringify([cards, s.dest ?? null]);
  const planned = j.kind === "plan" && j.state === "done" && JSON.stringify(s.plan_for) === k;
  if (j.kind === "plan" && j.state === "done") lastPlan = j.result;
  if (j.kind === "plan" && j.state === "done" && j.id !== choice.planID) {
    choice.planID = j.id; choice.files = []; choice.chosen = null; choice.thumbs = {}; choice.asked = new Set();
    api("/api/plan/items").then(r => { choice.files = r.items; render(); }).catch(() => {});
  }
  if (!cards.length) lastKey = "";
  if (cards.length && s.dest && s.dest_drive_connected && j.state !== "running" && k !== lastKey) {
    lastKey = k;
    if (!planned) api("/api/plan", {}).catch(() => {});
  }
  const after = j.kind === "import" && j.state === "done" ? String(j.id) : lastBackup;
  lastBackup = after;
  const key = (s.hdr_folder || "") + "|" + after;
  if (s.hdr_folder && s.hdr_folder_exists && s.hdr_job?.state !== "running" && key !== hdrLooked) {
    hdrLooked = key;
    api("/api/hdr/scan", {}).catch(() => {});
  }
  if (hdr.opened) {
    if (s.hdr_folder !== hdr.folder) { hdr.folder = s.hdr_folder; hdr.sets = null; hdr.selected = new Set(); hdr.merging = []; hdr.failed = {}; hdr.lastMerged = null; hdrOpen(); }
    hdrJobChanged();
  }
}
async function refresh() {
  try {
    s = await api("/api/state");
    ready = true; failure = null;
    update();
  } catch (e) {
    if (e !== "starting") failure = String(e);
  }
  render();
}
function schedule() {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => { await refresh(); schedule(); }, running() ? 500 : 1500);
}
async function act(p, body = {}) {
  try {
    await api(p, body);
    await refresh(); schedule();
    return null;
  } catch (e) {
    await refresh();
    return String(e);
  }
}
const say = e => { note = e ? { text: e, bad: true } : null; render(); };

// ---- actions
function backUp() {
  note = null;
  act("/api/import", everything() ? {} : { ids: [...picked()].sort((a, b) => a - b) }).then(say);
}
function setTag(day, tag) { editing = null; act("/api/tag", { day, tag }).then(say); render(); }
function beginTag(day, start) { editing = day; tagText = start || ""; closeMenu(); render(); focusTag(start); }
function focusTag(start) {
  const i = document.querySelector("[data-tagin]");
  if (i) { i.value = start || ""; i.focus(); i.select(); }
}
const verify = () => { note = null; act("/api/verify").then(say); };
const retry = async () => { note = null; await act("/api/reset"); lastKey = ""; render(); };
const useBackup = p => { if (p !== s.dest) act("/api/dest", { path: p }).then(e => { say(e); lastKey = ""; }); };
async function chooseFolder(title, start) {
  if (!TAURI) return window.prompt(title, start || "");
  return call("pick_folder", { title, start: start || null });
}
async function pickBackup() {
  const p = await chooseFolder("Choose where offcard backs up your photos and videos", s.dest);
  if (p) { const e = await act("/api/dest", { path: p }); say(e); lastKey = ""; }
}
async function eject() {
  try {
    const r = await api("/api/eject", {});
    const bad = (r.results || []).find(x => !x.ejected);
    note = bad ? { text: `Couldn't eject ${pieces(bad.card).pop()}. Eject it in ${s.file_manager}.`, bad: true } : { text: "Ejected. You can take the card out.", bad: false };
  } catch (e) { note = { text: String(e), bad: true }; }
  refresh();
}
async function moveExtras() {
  try {
    const r = await api("/api/trash", {});
    note = { text: `Moved ${plural(r.moved, "JPG")} to the ${s.trash_name}.`, bad: false };
  } catch (e) { note = { text: String(e), bad: true }; }
  refresh();
}
function copyUpdate() {
  const t = document.createElement("textarea");
  t.value = s.update.line; document.body.append(t); t.select();
  document.execCommand("copy"); t.remove();
  note = { text: `Install line copied. Paste it into ${s.update.line.startsWith("irm") ? "PowerShell" : "Terminal"}.`, bad: false };
  render();
}
const setLogin = async on => { const r = await call("login_set", { on }); loginOn = r === null ? on : r; render(); };

// HDR
function hdrOpen() {
  hdr.opened = true; hdr.folder = s.hdr_folder;
  if (!s.hdr_folder || !s.hdr_folder_exists || hdr.sets) return;
  const j = s.hdr_job;
  if (j?.state === "running") return;
  if (j?.state === "done") hdrLoad(); else hdrScan();
}
function hdrJobChanged() {
  const j = s.hdr_job;
  if (!j || j.state === "running" || j.id === hdr.seenJob) return;
  hdr.seenJob = j.id;
  if (j.state === "error") hdr.note = j.error;
  if (j.kind === "merge" && j.result) hdr.failed = Object.fromEntries((j.result.failed || []).map(f => [f.file, f.error]));
  hdrLoad();
}
async function hdrLoad() {
  try {
    const r = await api("/api/hdr/sets");
    if (!r.sets) return hdrScan();
    const firstLoad = !hdr.sets;
    hdr.sets = r.sets;
    if (firstLoad) hdr.selected = new Set(r.sets.filter(x => !x.done).map(x => x.id));
    else hdr.selected = new Set([...hdr.selected].filter(id => r.sets.some(x => x.id === id && !x.done)));
    const done = [...hdr.merging].reverse().find(id => r.sets.some(x => x.id === id && x.done));
    if (done !== undefined) hdr.lastMerged = done;
    render();
  } catch { /* the next look fixes it */ }
}
function hdrScan() {
  if (s.hdr_job?.state === "running") return;
  hdr.note = null;
  act("/api/hdr/scan").then(e => { if (e) { hdr.note = e; render(); } });
}
function hdrMerge() {
  const ids = [...hdr.selected].sort((a, b) => a - b);
  if (!ids.length) return;
  hdr.note = null; hdr.failed = {}; hdr.lastMerged = null; hdr.merging = ids; hdr.mergeStart = Date.now();
  act("/api/hdr/merge", { ids, tiff: hdr.tiff }).then(e => { if (e) { hdr.note = e; hdr.merging = []; render(); } });
}
const hdrFinish = () => { hdr.merging = []; hdr.failed = {}; hdr.lastMerged = null; hdr.note = null; };
const hdrSetFolder = p => { hdr.note = null; act("/api/hdr/folder", { path: p }).then(e => { if (e) { hdr.note = e; render(); } }); };
const hdrReveal = id => act("/api/reveal", { id }).then(e => { if (e) { hdr.note = e; render(); } });
async function hdrChoose() {
  const p = await chooseFolder("Choose a folder with bracketed shots", s.hdr_folder || s.dest);
  if (p) hdrSetFolder(p);
}
function hdrRetry() {
  hdr.selected = new Set((hdr.sets || []).filter(x => hdr.failed[x.output] !== undefined).map(x => x.id));
  hdrMerge();
}

// Previews for a day's photos, fetched once.
async function loadThumbs(ids) {
  const want = ids.filter(i => !choice.asked.has(i));
  want.forEach(i => choice.asked.add(i));
  for (let i = 0; i < want.length; i += 24) {
    const chunk = want.slice(i, i + 24);
    try {
      const r = await api("/api/plan/thumbs", { ids: chunk });
      chunk.forEach(id => { if (r.thumbs[id]) choice.thumbs[id] = r.thumbs[id]; });
      render();
    } catch { /* a tile without a preview keeps its glyph */ }
  }
}

// ---- pieces of the panel
const line = (t, bad) => `<div class="${bad ? "bad" : ""}">${esc(t)}</div>`;
const noteLine = () => s.update_job?.state === "error" ? line(`Couldn't update: ${s.update_job.error}`, true) : note ? line(note.text, note.bad) : null;
const on = (name, ...args) => `data-do="${name}" data-args="${esc(JSON.stringify(args))}"`;
const ink = (t, name, ...a) => `<button class="pill ink" ${on(name, ...a)}>${esc(t)}</button>`;
const quiet = (t, name, ...a) => `<button class="pill quiet" ${on(name, ...a)}>${esc(t)}</button>`;
const off = t => `<button class="pill" disabled>${esc(t)}</button>`;
const split = (t) => `<div class="split"><button class="main" ${on("backUp")}>${esc(t)}</button><button class="more" ${on("moreMenu")} title="Back up only some files, or tag the day" aria-label="More backup choices">${I.down}</button></div>`;
const pair = (a, an, b, bn) => ink(a, an) + `<button class="pill quiet small" ${on(bn)}>${esc(b)}</button>`;
const text = t => esc(t);
const tick = st => `<span class="tick ${st === "off" ? "" : "on"}">${st === "on" ? I.tick : st === "some" ? I.dash : ""}</span>`;
const mark = { ink: `<div class="ic ink">${I.card}</div>`, check: `<div class="ic ink">${I.check}</div>`, quiet: `<div class="ic">${I.cardOut}</div>`, spin: `<div class="ic spin"></div>`, alert: `<div class="ic alert">!</div>`, drive: `<div class="ic">${I.drive}</div>`, computer: `<div class="ic">${I.computer}</div>`, network: `<div class="ic">${I.network}</div>`, folder: `<div class="ic">${I.folderBig}</div>` };
const ring = p => `<div class="ring" data-ring="${p}"><svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true"><defs><clipPath id="ringclip"><circle cx="20" cy="20" r="18"/></clipPath></defs><circle cx="20" cy="20" r="18.75" fill="var(--fill3)"/><g clip-path="url(#ringclip)"><path class="w1" fill="var(--ink)" opacity=".13"/><path class="w2" fill="var(--ink)" opacity=".26"/></g><circle cx="20" cy="20" r="18.75" stroke="var(--fill2)" stroke-width="2.5"/><circle class="arc" cx="20" cy="20" r="18.75" stroke="var(--ink)" stroke-width="2.5" stroke-linecap="round" pathLength="100" stroke-dasharray="100" transform="rotate(-90 20 20)"/></svg><em></em></div>`;

function timeLeft(p) {
  const done = p?.done || 0, total = p?.total || 0, t = p?.elapsed || 0;
  if (t <= 2 || done <= 0 || done >= total) return null;
  const left = (total - done) / (done / t);
  return left < 50 ? "Less than a minute left" : `About ${plural(Math.ceil(left / 60), "minute")} left`;
}
function folderText(d) {
  const parts = pieces(d.folder), name = parts.pop() || "";
  return `${I.folder}<span class="txt">${esc(parts.join(" › "))}${parts.length ? " › " : ""}<b>${esc(name)}</b>${d.new ? " new" : ""}</span>`;
}
function dayIsNew(parts, tree) {
  let node = tree;
  for (const p of parts) {
    node = (node?.children || []).find(c => c.name === p);
    if (!node) return false;
  }
  return !!node.new;
}
function destinationLines(fallback) {
  const r = (job().kind === "plan" ? job().result : lastPlan) || {}, days = r.days || [];
  const cnt = [r.new_photos > 0 && `Photos ${num(r.new_photos)}`, r.new_videos > 0 && `Videos ${num(r.new_videos)}`].filter(Boolean).join("  ·  ");
  if (!days.length) return [line(fallback), line(cnt)];
  const parts = pieces(days[0].folder), name = parts[parts.length - 1];
  const fresh = dayIsNew(parts, r.tree);
  return [`<div class="folder">${I.folder}<span class="txt">${esc(parts.slice(0, -1).join(" › "))}${parts.length > 1 ? " › " : ""}<b>${esc(name)}</b>${fresh ? " new" : ""}${days.length > 1 ? ` +${days.length - 1} more` : ""}</span></div>`, line(cnt)];
}
function suggestions() {
  const t = tagText.trim().toLowerCase();
  return (s.recent_tags || []).filter(x => !t || (x.toLowerCase().startsWith(t) && x.toLowerCase() !== t)).slice(0, 3);
}
function tagField(day) {
  const picks = suggestions();
  return `<label class="field">${esc(day)} - <input data-tagin data-day="${esc(day)}" placeholder="Birthday, Ooty, Reunion…" maxlength="40" aria-label="Tag for ${esc(dayTitle(day))}"><kbd>Enter</kbd></label>${picks.length ? `<div class="chips">${picks.map(t => `<button class="chip" ${on("commitTag", day, t)}>${esc(t)}</button>`).join("")}</div>` : ""}`;
}
function secondLine(partial, normal) {
  const n = noteLine();
  if (n) return n;
  if (partial) return `<div><button class="link" style="text-decoration:none;color:var(--sub);font-weight:400" ${on("push", "days")}>${plural(totalFiles() - chosenCount(), "file")} left for later  ·  <u style="color:var(--text)">Change</u></button></div>`;
  return normal;
}
function readyInfo() {
  const r = job().result || {}, days = r.days || [], partial = !everything() && choice.files.length > 0;
  if (days.length === 1) {
    const d = days[0];
    if (editing === d.key) return [tagField(d.key)];
    const btn = d.tag ? `<button class="pencil" ${on("beginTag", d.key, d.tag)} title="Change this day's tag" aria-label="Change this day's tag">${I.pencil}</button>`
      : `<button class="addtag" ${on("beginTag", d.key, "")} title="Name this day's folder, like &quot;24Oct26 - Birthday&quot;">+ Add tag</button>`;
    const cnt = [r.new_photos > 0 && `Photos ${num(r.new_photos)}`, r.new_videos > 0 && `Videos ${num(r.new_videos)}`].filter(Boolean).join("  ·  ");
    return [`<div class="folder">${folderText(d)}${btn}</div>`, secondLine(partial, line(cnt))];
  }
  const tagged = days.filter(d => d.tag);
  const names = [...new Set(tagged.map(d => d.tag))];
  const btn = tagged.length
    ? `<button style="font-size:11px" ${on("push", "days")}><span style="color:var(--sub)">${tagged.length} tagged: ${esc(names.slice(0, 2).join(", "))}${names.length > 2 ? "…" : ""}  ·  </span>Add tags<span style="color:var(--sub)"> ›</span></button>`
    : `<button class="tagsbtn" ${on("push", "days")} title="Tag each day on its own">Add tags ›</button>`;
  return [`<div class="folder">${I.folder}<span>${days.length} days · ${esc(dayRange(days.map(d => d.key)))}</span></div>`, secondLine(partial, `<div>${btn}</div>`)];
}
function backUpTitle(r) {
  const p = r.new_photos, v = r.new_videos + r.new_xml;
  return `Back Up ${v === 0 ? plural(p, "Photo") : p === 0 ? plural(r.new_videos, "Video") : `${num(r.new_files)} Files`}`;
}

/** Every state of the backup page, as on the Mac (PanelView.view). */
function panelState() {
  const v = { card: mark.ink, cardTitle: "", cardLine: "", cardBad: false, cardDim: false, drive: mark.drive, driveTitle: "", driveLine: null, driveBad: false, copying: false, info: [], slot: off("Back Up") };
  const j = job(), r = j.result || {}, p = j.progress, kind = j.kind, st = j.state;
  const fraction = p ? p.done / Math.max(p.total, 1) : 0;
  const drive = s.dest ? place(s.dest).drive : "";
  if (!s.dest) { v.drive = mark.folder; v.driveTitle = "Choose"; v.driveLine = "a backup folder"; }
  else {
    v.driveTitle = drive;
    v.drive = s.dest_kind === "internal" ? mark.computer : s.dest_kind === "network" ? mark.network : mark.drive;
    if (!s.dest_drive_connected) { v.drive = mark.alert; v.driveLine = "Not connected"; v.driveBad = true; }
  }
  if (!ready) {
    v.card = failure ? mark.alert : mark.spin; v.cardTitle = "offcard"; v.cardLine = "Starting…"; v.driveTitle = "";  v.driveLine = "";
    v.drive = mark.drive;
    v.info = [line(failure || "Getting ready", !!failure)];
    return v;
  }
  const cards = s.cards || [], card = cards[0];
  if (!card) {
    v.card = mark.quiet; v.cardTitle = "No card"; v.cardLine = "Insert one"; v.cardDim = true;
    v.info = [line("Put a memory card in to see what's new"), noteLine() || line("offcard only ever reads it")];
    if (!s.dest) v.slot = ink("Choose Folder…", "pickBackup");
    return v;
  }
  v.cardTitle = card.name + (cards.length > 1 ? ` +${cards.length - 1}` : "");
  v.cardLine = first(counts(card.photos, card.videos));
  if (!s.dest) {
    v.info = [line("Choose where your photos and videos go"), line("offcard remembers it for next time")];
    v.slot = ink("Choose Folder…", "pickBackup");
    return v;
  }
  if (!s.dest_drive_connected) {
    v.info = [line(s.dest_kind === "network" ? `Connect to ${drive} to back up` : `Plug in ${drive} to back up`, true), line("or choose another folder")];
    v.slot = quiet("Choose Another Folder…", "pickBackup");
    return v;
  }
  if (!s.job || (kind === "plan" && st === "running")) {
    v.card = mark.spin; v.cardLine = "Checking…";
    v.info = [line(p ? `Reading ${num(p.done)} of ${plural(p.total, "file")}` : "Looking for what's new"), line("The card is only ever read")];
    return v;
  }
  if (st === "error") {
    v.card = mark.alert; v.cardLine = "Couldn't finish"; v.cardBad = true;
    v.info = [line(j.error, true), line("Nothing on the card was changed")];
    v.slot = ink("Try Again", "retry");
    return v;
  }
  if (st === "running" && kind === "import") {
    v.card = ring(fraction); v.copying = true;
    v.cardLine = p ? amountOf(p.done, p.total) : "Starting…";
    v.info = destinationLines(`Copying to ${drive}`);
    v.slot = text(timeLeft(p) || "Copying…");
    return v;
  }
  if (st === "running" && kind === "verify") {
    v.card = ring(fraction); v.copying = true; v.cardLine = "Comparing…";
    v.info = [line("Comparing every file byte by byte"), line(p?.files_total > 0 ? `${num(p.files_done)} of ${num(p.files_total)} checked` : "Reading the card and the copies")];
    v.slot = text(timeLeft(p) || "Checking…");
    return v;
  }
  if (kind === "plan") {
    if (!r.new_files) {
      v.card = mark.check; v.cardLine = "All backed up";
      v.info = [line("Nothing new since your last backup"), noteLine() || line(`${first(counts(card.photos, card.videos))}, all on ${drive}`)];
      v.slot = pair("Check Before Formatting", "verify", "Eject", "eject");
      return v;
    }
    const partial = !everything() && choice.files.length > 0;
    const needed = partial ? chosenBytes() : r.needed_bytes;
    if (needed + 50 * MB > r.free_bytes) {
      v.cardLine = `${partial ? chosenCount() : num(r.new_files)} new · ${human(needed)}`;
      v.drive = mark.alert; v.driveLine = `${human(r.free_bytes)} free`; v.driveBad = true;
      v.info = [line(`Needs ${human(Math.max(0, needed - r.free_bytes))} more on ${drive}`, true), line("Back up some files now, or choose another folder")];
      v.slot = pair("Choose Files…", "pushDays", "Change", "pickBackup");
      return v;
    }
    v.cardLine = partial ? `${num(chosenCount())} of ${num(r.new_files)} new · ${human(chosenBytes())}` : `${num(r.new_files)} new · ${human(r.needed_bytes)}`;
    v.info = readyInfo();
    const title = partial ? `Back Up ${plural(chosenCount(), "File")}` : backUpTitle(r);
    v.slot = st !== "done" || (partial && chosenCount() === 0) ? off("Back Up") : split(title);
    return v;
  }
  if (kind === "import") {
    const errs = (r.errors || []).length;
    if (errs > 0) {
      v.card = mark.alert; v.cardLine = `${plural(errs, "file")} not copied`; v.cardBad = true;
      v.info = [line(`${plural(errs, "file")} couldn't be copied`, true), line("Try again, or check the card and the drive")];
      v.slot = ink("Try Again", "retry");
    } else {
      v.card = mark.check; v.cardLine = `Backed up ${plural(r.files, "file")}`;
      const days = r.days || [];
      const filed = line(days.length ? `Filed in ${pieces(days[0]).join(" › ")}${days.length > 1 ? ` +${days.length - 1}` : ""}` : `Filed by day on ${drive}`);
      const n = noteLine();
      if (n) v.info = [filed, n];
      else if (r.raw_jpg_pairs > 0) v.info = [filed, `<button class="link" ${on("moveExtras")}>Move ${plural(r.raw_jpg_pairs, "extra JPG")} to the ${esc(s.trash_name)}</button>`];
      else v.info = [filed, line("Check it before you format the card")];
      v.slot = pair("Check Before Formatting", "verify", "Eject", "eject");
    }
    return v;
  }
  if (kind === "verify") {
    const bad = (r.cards || []).reduce((n, c) => n + c.missing.length + c.different.length, 0);
    if (bad > 0) {
      v.card = mark.alert; v.cardLine = `${plural(bad, "file")} not backed up`; v.cardBad = true;
      v.info = [line(`${plural(bad, "file")} ${bad === 1 ? "isn't" : "aren't"} on ${drive} yet`, true), line("Back up again before you format the card")];
      v.slot = ink("Back Up Again", "retry");
    } else {
      v.card = mark.check; v.cardLine = "Safe to format";
      v.info = [line(`Every file is on ${drive}, byte for byte`), noteLine() || line("You can format the card in the camera")];
      v.slot = ink(`Eject ${card.name}`, "eject");
    }
    return v;
  }
  return v;
}
function hdrDetail() {
  const j = s.hdr_job;
  if (j?.state === "running") return j.kind === "merge" ? "Merging…" : "";
  return s.hdr_new > 0 ? plural(s.hdr_new, "new set") : "";
}
/** A newer version: one click downloads and installs it. The install line stays for when it can't. */
function updateRow() {
  const u = s.update_job, st = u?.state, latest = esc(s.update.latest);
  const row = (act, title, detail) => `<button class="mrow" ${act ? on(act) : ""}><span class="gl ink">${I.arrow}</span><span class="t">${title}</span><span class="d">${esc(detail)}</span></button><div class="rule tight"></div>`;
  if (st === "running" || st === "ready" || st === "applying") {
    const p = u.progress;
    return row(null, `Updating to ${latest}`, st === "running" ? (p?.total ? `${Math.floor(p.done * 100 / p.total)}%` : "Starting…") : running() ? "After this finishes" : "Restarting…");
  }
  return s.can_update && st !== "error" ? row("startUpdate", `Update to ${latest}`, "Update") : row("copyUpdate", `Update to ${latest}`, "Copy Install Line");
}
function backupPage() {
  const v = panelState();
  const place_ = s.dest ? (place(s.dest).folder || "Whole drive") : "";
  const dest = v.driveLine !== null
    ? `<div class="small ${v.driveBad ? "bad" : ""}">${esc(v.driveLine)}</div>`
    : `<div class="small"><button class="dest" ${on("destMenu")} ${job().state === "running" && job().kind !== "plan" ? "disabled" : ""} title="Choose where this backup goes"><span>${esc(place_)}</span>${I.updown}</button></div>`;
  const update = s.update ? updateRow() : "";
  return `<div class="flow">
      <div class="tile ${v.cardDim ? "dim" : ""}">${v.card}<div class="name">${esc(v.cardTitle)}</div><div class="small ${v.cardBad ? "bad" : ""}">${esc(v.cardLine)}</div></div>
      <div class="chev ${v.copying ? "run" : ""}">${I.chev}</div>
      <div class="tile">${v.drive}<div class="name">${esc(v.driveTitle)}</div>${dest}</div>
    </div>
    <div class="info">${v.info.join("")}</div>
    <div class="slot">${v.slot}</div>
    <div class="rule"></div>${update}
    <button class="mrow" ${on("push", "hdr")}><span class="gl">${I.hdr}</span><span class="t">HDR Merge</span><span class="d">${esc(hdrDetail())}</span></button>
    <div class="foot"><button class="login" ${on("toggleLogin")} role="switch" aria-checked="${loginOn}"><span class="sw ${loginOn ? "on" : ""}"></span><span>Start with Windows</span></button><span class="sp"></span><span class="v" title="The version of offcard you have">v${esc(s.version || "")}</span><button class="quit" ${on("quit")} title="Quit offcard">Quit</button></div>`;
}
const head = (title, sub, options) => `<div class="phead"><button class="round" ${on("pop")} title="Back" aria-label="Back">${I.left}</button><div class="tt"><b>${esc(title)}</b><div class="sub">${sub}</div></div>${options ? `<button class="round" ${on(options)} title="Options" aria-label="Options">${I.dots}</button>` : "<span></span>"}</div><div class="rule tight"></div>`;
const pfoot = slot => `<div class="pfoot"><div class="slot">${slot}</div></div>`;
const message = (glyph, title, sub, bad) => `<div class="msg">${glyph}<b>${esc(title)}</b><div class="s ${bad ? "bad" : ""}">${esc(sub)}</div></div>`;

function daysPage() {
  const days = job().kind === "plan" && job().state === "done" ? job().result.days : [];
  const sub = `${num(chosenCount())} of ${plural(totalFiles(), "new file")} · ${human(chosenBytes())}`;
  const tickOf = ids => { const n = ids.filter(isOn).length; return n === 0 ? "off" : n === ids.length ? "on" : "some"; };
  const detail = (d, mine) => {
    const all = new Set(d.ids);
    if (!mine.size) return `${plural(chosenCount(all), "file")} · left for later`;
    const what = [d.photos > 0 && plural(d.photos, "photo"), d.videos > 0 && plural(d.videos, "video")].filter(Boolean).join(" · ");
    if (mine.size === all.size) return `${what} · ${human(d.bytes)}`;
    return `${chosenCount(mine)} of ${chosenCount(all)} · ${human(chosenBytes(mine))}`;
  };
  const row = d => {
    const t = tickOf(d.ids), mine = new Set(d.ids.filter(isOn));
    const name = editing === d.key ? tagField(d.key) : `<span class="n"><span>${esc(pieces(d.folder).pop())}</span>${d.tag ? `<button class="pencil" ${on("beginTag", d.key, d.tag)} title="Change this day's tag" aria-label="Change this day's tag">${I.pencil}</button>` : `<button class="addtag short" ${on("beginTag", d.key, "")}>+ Tag</button>`}</span>`;
    return `<div class="rowx"><button ${on("tickDay", d.ids, t !== "on")} aria-label="${t === "on" ? "Leave out" : "Back up"} ${esc(dayTitle(d.key))}">${tick(t)}</button><span class="tx">${name}<span class="m">${esc(detail(d, mine))}</span></span><button class="go" ${on("push", "files", d.key)} title="Choose files from ${esc(dayTitle(d.key))}">${I.right}</button></div>`;
  };
  const n = chosenCount();
  return head(days.length === 1 ? "Choose What to Back Up" : `${days.length} Days to Back Up`, esc(sub), "daysMenu") +
    (days.length ? `<div class="scroll" style="padding:4px 0">${days.map(row).join("")}</div>` : message(mark.quiet, "Nothing to choose", "Put a card in, and offcard checks what's new")) +
    pfoot(n === 0 ? off("Back Up") : ink(`Back Up ${plural(n, "File")}`, "backUpFrom"));
}
function filesPage(day) {
  const files = choice.files.filter(f => f.day === day), photos = files.filter(f => f.kind !== "video"), videos = files.filter(f => f.kind === "video");
  const tag = ((job().result || {}).days || []).find(d => d.key === day)?.tag || "";
  const chosen = files.filter(f => isOn(f.id)).reduce((n, f) => n + fileCount(f), 0), total = files.reduce((n, f) => n + fileCount(f), 0);
  const tile = f => {
    const lit = isOn(f.id), badge = f.kind === "pair" ? "RAW+JPG" : f.kind === "video" ? f.time.slice(0, 5) : null;
    return `<button class="th ${lit ? "on" : ""}" ${on("toggleFile", f.id)} title="${esc(f.name)} · ${esc(f.time)}" aria-label="${esc(f.name)}, ${esc(f.time)}, ${lit ? "chosen" : "left out"}">${choice.thumbs[f.id] ? `<img src="${choice.thumbs[f.id]}" alt="">` : f.kind === "video" ? I.video : I.photo}${tick(lit ? "on" : "off")}${badge ? `<span class="bdg">${f.kind === "video" ? I.play + "&nbsp;" : ""}${esc(badge)}</span>` : ""}</button>`;
  };
  const section = (title, items) => {
    const allOn = items.every(f => isOn(f.id));
    return `<div class="sec"><span>${title} · ${items.length}</span><button ${on("tickDay", items.map(f => f.id), !allOn)}>${allOn ? "Select None" : "Select All"}</button></div><div class="grid">${items.map(tile).join("")}</div>`;
  };
  const n = chosenCount();
  return head(dayTitle(day), `${tag ? `<span>${esc(tag)}</span>` : ""}<span>${chosen} of ${total} chosen</span>`, "filesMenu") +
    `<div class="scroll">${photos.length ? section("Photos", photos) : ""}${videos.length ? section("Videos", videos) : ""}</div>` +
    pfoot(n === 0 ? off("Back Up") : ink(`Back Up ${plural(n, "File")}`, "backUpFrom"));
}
const evs = st => st.biases.map(b => { const f = v => String(v); return b > 0 ? `+${f(b)}` : b < 0 ? `−${f(-b)}` : "0"; }).join(" · ") + " EV";
function hdrPage() {
  const j = s.hdr_job || {}, busy = j.state === "running", merging = busy && j.kind === "merge";
  const folderName = s.hdr_folder ? pieces(s.hdr_folder).pop() : "";
  const sub = `<button class="dest" style="font-size:11px" ${on("hdrFolderMenu")} ${busy ? "disabled" : ""}><span>${s.hdr_folder ? `in ${esc(folderName)}` : "no folder yet"}</span>${I.updown}</button>`;
  const stateOf = st => {
    if (hdr.failed[st.output] !== undefined) return ["failed", hdr.failed[st.output]];
    const k = merging ? hdr.merging.indexOf(st.id) : -1;
    if (k >= 0) {
      const at = j.progress?.done || 0;
      if (k + 1 <= at || st.done) return ["merged"];
      if (k <= at) return ["merging", at - k];
      return ["waiting"];
    }
    if (st.done) return ["merged"];
    return ["pick", hdr.selected.has(st.id)];
  };
  const row = st => {
    const [state, x] = stateOf(st);
    const right = state === "pick" ? tick(x ? "on" : "off") : state === "merged" ? "Merged" : state === "waiting" ? `<span style="color:var(--ter)">Waiting</span>`
      : state === "merging" ? `${Math.floor(x * 100)}%<svg class="mini" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="9" r="8" stroke="var(--fill2)" stroke-width="2"/><circle cx="9" cy="9" r="8" stroke="var(--ink)" stroke-width="2" stroke-linecap="round" pathLength="100" stroke-dasharray="100" stroke-dashoffset="${100 * (1 - Math.max(.02, x))}" transform="rotate(-90 9 9)"/></svg>`
      : `<span class="bad">!</span>`;
    return `<button class="rowx set" ${state === "pick" ? on("toggleSet", st.id) : on("revealSet", st.id, state === "merged")} aria-label="${esc(st.date)}, ${esc(st.time)}, ${plural(st.names.length, "shot")}, ${esc(evs(st))}">${tile(state === "merged" ? "ink" : "")}<span class="tx"><span class="n"><span>${esc(st.time)} · ${plural(st.names.length, "shot")}</span></span><span class="m ${state === "failed" ? "bad" : ""}">${state === "failed" ? `Couldn't merge: ${esc(x)}` : esc(evs(st))}</span></span><span class="right">${right}</span></button>`;
  };
  let content;
  if (s.hdr_missing) content = message(mark.alert, "HDR Merge isn't available", s.hdr_missing);
  else if (!s.hdr_folder) content = message(tile("", true), "Choose a folder", "offcard finds the bracketed shots in it,\nand in every folder inside it.");
  else if (!s.hdr_folder_exists) content = message(mark.alert, `${place(s.hdr_folder).drive} isn't connected`, "Connect it to see its bracketed shots", true);
  else if (busy && j.kind === "scan") {
    const p = j.progress;
    content = message(mark.spin, "Looking for bracketed shots…", p?.stage === "Making previews" ? "Almost done" : p ? `Reading ${num(p.done)} of ${num(p.total)} photos in ${folderName}` : `In ${folderName}`);
  } else if (hdr.sets) {
    if (!hdr.sets.length) content = message(tile("", true), `No bracketed shots in ${folderName}`, "Shoot with Continuous Bracket (BRK C) in RAW,\nthen back the card up.");
    else {
      const days = [];
      hdr.sets.forEach(st => { const d = days.find(x => x[0] === st.date); d ? d[1].push(st) : days.push([st.date, [st]]); });
      content = `<div class="scroll">${days.map(([d, items]) => `<div class="day">${esc(d)}</div>${items.map(row).join("")}`).join("")}</div>`;
    }
  } else content = message(mark.spin, "Looking for bracketed shots…", `In ${folderName}`);

  let slot;
  if (hdr.note && !busy) slot = text(hdr.note);
  else if (s.hdr_missing) slot = off("Merge");
  else if (!s.hdr_folder) slot = s.dest ? ink("Use Backup Folder", "hdrUseBackup") : ink("Choose Folder…", "hdrChoose");
  else if (!s.hdr_folder_exists) slot = quiet("Choose Another Folder…", "hdrChoose");
  else if (busy && j.kind === "scan") slot = off("Merge");
  else if (merging) {
    const p = j.progress || {}, at = p.done || 0, total = Math.max(p.total || 0, 1), t = (Date.now() - hdr.mergeStart) / 1000;
    let l = `Merging ${Math.min(Math.floor(at) + 1, p.total || 0)} of ${p.total || 0}`;
    if (at > .15 && t > 3) { const left = t / at * (total - at); l += left < 50 ? " · less than a minute left" : ` · about ${plural(Math.ceil(left / 60), "minute")} left`; }
    slot = text(l);
  } else if (!hdr.sets || !hdr.sets.length) slot = !hdr.sets ? off("Merge") : quiet("Choose Another Folder…", "hdrChoose");
  else if (hdr.merging.length) {
    slot = Object.keys(hdr.failed).length
      ? pair("Retry", "hdrRetry", hdr.lastMerged === null ? "Done" : "Show", "hdrShowOrDone")
      : ink(`Show in ${s.file_manager}`, "hdrShow") + `<button class="pill quiet small" ${on("hdrDone")}>Done</button>`;
  } else {
    const n = hdr.selected.size;
    slot = n === 0 ? (hdr.sets.every(x => x.done) ? text("Every set here is merged") : off("Merge")) : ink(`Merge ${plural(n, "Set")}`, "hdrMerge");
  }
  return head("HDR Merge", sub, merging ? null : "hdrOptions") + content + pfoot(slot);
}

// ---- menus
function openMenu(items, from) { menu = { items, from }; renderMenu(); }
function closeMenu() { menu = null; renderMenu(); }
function renderMenu() {
  const panel = document.getElementById("panel");
  panel.querySelector(".menu")?.remove();
  if (!menu) return;
  const el = document.createElement("div");
  el.className = "menu"; el.setAttribute("role", "menu");
  el.innerHTML = menu.items.map((m, i) => m === "-" ? "<hr>" : `<button class="it" role="menuitem" data-menu="${i}" ${m.enabled === false ? "disabled" : ""}>${m.checked ? I.menuTick : ""}<span>${esc(m.title)}</span>${m.detail !== undefined ? `<span class="d">${esc(m.detail)}</span>` : ""}</button>`).join("");
  panel.append(el);
  const P = panel.getBoundingClientRect(), A = menu.from.getBoundingClientRect(), H = el.offsetHeight, W = el.offsetWidth;
  let top = A.bottom - P.top + 4;
  if (top + H > P.height) top = A.top - P.top - H - 4;
  el.style.top = Math.max(4, top) + "px";
  el.style.left = Math.min(Math.max(4, A.right - P.left - W), P.width - W - 4) + "px";
}
const DO = {
  backUp, verify, eject, retry, pickBackup, moveExtras, copyUpdate, hdrMerge, hdrChoose, hdrRetry,
  beginTag, push, pop,
  pushDays: () => push("days"),
  startUpdate() { note = null; act("/api/update").then(say); },
  commitTag: (d, t) => setTag(d, t),
  toggleLogin: () => setLogin(!loginOn),
  quit: () => call("quit"),
  backUpFrom() { backUp(); popAll(); },
  tickDay(ids, on) { setChoice(ids, on); render(); },
  toggleFile(id) { setChoice([id], !isOn(id)); render(); },
  toggleSet(id) { hdr.selected.has(id) ? hdr.selected.delete(id) : hdr.selected.add(id); render(); },
  revealSet(id, done) { if (done) hdrReveal(id); },
  hdrUseBackup: () => hdrSetFolder(s.dest),
  hdrShow() { if (hdr.lastMerged !== null) hdrReveal(hdr.lastMerged); },
  hdrShowOrDone() { if (hdr.lastMerged !== null) hdrReveal(hdr.lastMerged); else { hdrFinish(); render(); } },
  hdrDone() { hdrFinish(); pop(); },
  moreMenu(from) {
    const r = job().result, days = r.days || [];
    const pn = choice.files.filter(f => f.kind !== "video").reduce((n, f) => n + fileCount(f), 0);
    const vn = choice.files.filter(f => f.kind === "video").reduce((n, f) => n + fileCount(f), 0);
    const items = [{ title: "Everything", detail: r.new_files, checked: everything(), run() { choice.chosen = null; render(); } }];
    if (pn > 0 && vn > 0) items.push(
      { title: "Photos Only", detail: pn, run() { only(f => f.kind !== "video"); render(); } },
      { title: "Videos Only", detail: vn, run() { only(f => f.kind === "video"); render(); } });
    items.push("-", { title: "Choose Files…", run: () => push("days") }, "-");
    if (days.length === 1) items.push({ title: days[0].tag ? "Change Tag…" : "Add Tag…", run: () => beginTag(days[0].key, days[0].tag) });
    else items.push({ title: "Add Tags…", run: () => push("days") });
    openMenu(items, from);
  },
  destMenu(from) {
    const items = (s.recent_dests || []).map(p => ({ title: placeName(p), checked: p === s.dest, run: () => useBackup(p) }));
    items.push("-", { title: "Choose Folder…", run: pickBackup },
      { title: `Show in ${s.file_manager}`, enabled: !!s.dest_exists, run: () => call("show_folder", { path: s.dest }) });
    openMenu(items, from);
  },
  daysMenu(from) {
    const pn = choice.files.filter(f => f.kind !== "video"), vn = choice.files.filter(f => f.kind === "video");
    const sum = l => l.reduce((n, f) => n + fileCount(f), 0);
    openMenu([
      { title: "Select Everything", checked: everything(), run() { choice.chosen = null; render(); } },
      { title: "Select Nothing", checked: picked().size === 0, run() { choice.chosen = new Set(); render(); } },
      { title: "Photos Only", detail: sum(pn), enabled: pn.length > 0, run() { only(f => f.kind !== "video"); render(); } },
      { title: "Videos Only", detail: sum(vn), enabled: vn.length > 0, run() { only(f => f.kind === "video"); render(); } },
      "-", { title: "Files left out stay on the card and show as new next time.", enabled: false },
    ], from);
  },
  filesMenu(from) {
    const ids = choice.files.filter(f => f.day === path[path.length - 1].arg).map(f => f.id);
    openMenu([{ title: "Select All", run() { setChoice(ids, true); render(); } }, { title: "Select None", run() { setChoice(ids, false); render(); } }], from);
  },
  hdrOptions(from) {
    const sets = hdr.sets || [], busy = s.hdr_job?.state === "running";
    openMenu([
      { title: "Select New Sets", run() { hdr.selected = new Set(sets.filter(x => !x.done).map(x => x.id)); render(); } },
      { title: "Select All", run() { hdr.selected = new Set(sets.map(x => x.id)); render(); } },
      { title: "Select None", run() { hdr.selected = new Set(); render(); } },
      "-", { title: "Also Save a 16-bit TIFF", checked: hdr.tiff, run() { hdr.tiff = !hdr.tiff; } },
      "-", { title: "Look Again", enabled: !busy && !!s.hdr_folder_exists, run() { hdr.sets = null; hdrScan(); render(); } },
    ], from);
  },
  hdrFolderMenu(from) {
    const items = [{ title: "Choose Another Folder…", run: hdrChoose }];
    if (s.dest && s.dest !== s.hdr_folder) items.push({ title: "Use Backup Folder", run: () => hdrSetFolder(s.dest) });
    items.push("-", { title: `Show in ${s.file_manager}`, enabled: !!s.hdr_folder_exists, run: () => call("show_folder", { path: s.hdr_folder }) });
    openMenu(items, from);
  },
};

// ---- pages sliding, and drawing
const stage = () => document.getElementById("stage");
function pageHTML(p) { return p.name === "hdr" ? hdrPage() : p.name === "days" ? daysPage() : filesPage(p.arg); }
function push(name, arg) {
  closeMenu(); editing = null;
  const p = { name, arg };
  path.push(p);
  if (name === "hdr") hdrOpen();
  if (name === "files") loadThumbs(choice.files.filter(f => f.day === arg && f.kind !== "video").map(f => f.id));
  const el = document.createElement("div");
  el.className = "pg over right"; el.innerHTML = pageHTML(p);
  stage().append(el);
  el.getBoundingClientRect();
  el.classList.remove("right");
  const under = el.previousElementSibling;
  under.classList.add("left");
}
function pop() {
  closeMenu(); editing = null;
  if (!path.length) return;
  path.pop();
  const pgs = stage().children, el = pgs[pgs.length - 1], under = pgs[pgs.length - 2];
  el.classList.add("right"); el.dataset.leaving = "1"; under.classList.remove("left");
  setTimeout(() => el.remove(), 330);
}
function popAll() {
  closeMenu();
  path = [];
  [...stage().children].slice(1).forEach(el => { el.classList.add("right"); el.dataset.leaving = "1"; setTimeout(() => el.remove(), 330); });
  stage().children[0].classList.remove("left");
}
/** Bring a live element in line with new markup, leaving what didn't change alone (so typing,
    scrolling and animations carry on through each look at the engine). */
function morph(el, html) {
  const next = document.createElement(el.tagName);
  next.innerHTML = html;
  morphChildren(el, next);
}
function morphChildren(a, b) {
  const an = [...a.childNodes], bn = [...b.childNodes];
  bn.forEach((n, i) => {
    const o = an[i];
    if (!o) return a.append(n);
    if (o.nodeType !== n.nodeType || o.nodeName !== n.nodeName) return o.replaceWith(n);
    if (n.nodeType === 3) { if (o.nodeValue !== n.nodeValue) o.nodeValue = n.nodeValue; return; }
    if (n.nodeType !== 1) return;
    [...o.attributes].forEach(x => { if (!n.hasAttribute(x.name)) o.removeAttribute(x.name); });
    [...n.attributes].forEach(x => { if (o.getAttribute(x.name) !== x.value) o.setAttribute(x.name, x.value); });
    morphChildren(o, n);
  });
  an.slice(bn.length).forEach(n => n.remove());
}
let lastHeight = 0;
function render() {
  const pgs = [...stage().children].filter(e => !e.dataset.leaving);
  morph(pgs[0], backupPage());
  path.forEach((p, i) => { if (pgs[i + 1]) morph(pgs[i + 1], pageHTML(p)); });
  const h = pgs[0].offsetHeight;
  stage().style.height = h + "px";
  if (h !== lastHeight) { lastHeight = h; call("fit", { height: h + 34 }); }
}

// ---- the liquid ring: its level eases toward the engine's figure
function wave(level, phase, amp) {
  const y = 40 * (1 - level);
  let d = `M0 ${y + Math.sin(phase) * amp}`;
  for (let x = 2; x <= 40; x += 2) d += `L${x} ${y + Math.sin(phase + x / 6) * amp}`;
  return d + "L40 40L0 40Z";
}
let shown = 0;
function frame(t) {
  const r = document.querySelector(".ring");
  if (r) {
    const want = +r.dataset.ring;
    shown = want < shown ? want : shown + (want - shown) * .06;
    r.querySelector(".w1").setAttribute("d", wave(shown, t / 1000 * 1.7 + 2.1, 1.6));
    r.querySelector(".w2").setAttribute("d", wave(shown, t / 1000 * 2.6, 1.3));
    r.querySelector(".arc").setAttribute("stroke-dashoffset", 100 * (1 - Math.max(.01, shown)));
    r.querySelector("em").textContent = Math.round(want * 100) + "%";
  } else shown = 0;
  requestAnimationFrame(frame);
}

// ---- events
document.addEventListener("click", e => {
  const mi = e.target.closest("[data-menu]");
  if (mi) { const m = menu.items[+mi.dataset.menu]; closeMenu(); m.run?.(); return; }
  if (menu && !e.target.closest(".menu")) closeMenu();
  const b = e.target.closest("[data-do]");
  if (!b || b.disabled) return;
  const name = b.dataset.do, args = JSON.parse(b.dataset.args);
  e.preventDefault();
  if (name.endsWith("Menu") || name === "hdrOptions") DO[name](b);
  else DO[name](...args);
});
document.addEventListener("input", e => {
  if (e.target.matches("[data-tagin]")) { tagText = e.target.value; render(); }
});
document.addEventListener("keydown", e => {
  if (e.target.matches?.("[data-tagin]")) {
    if (e.key === "Enter") setTag(e.target.dataset.day, e.target.value);
    if (e.key === "Escape") { editing = null; render(); e.stopPropagation(); }
    return;
  }
  if (e.key === "Escape") {
    if (menu) closeMenu(); else if (path.length) pop(); else call("hide_panel");
  }
  if (e.key === "F5" || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "r")) e.preventDefault();
});
document.addEventListener("contextmenu", e => { if (!e.target.matches("input")) e.preventDefault(); });
window.addEventListener("focus", async () => { loginOn = await call("login_get") ?? loginOn; refresh(); });
window.addEventListener("blur", () => { if (menu) closeMenu(); });

// ---- the little window that says a card went in
function showToast(q) {
  document.body.className = "toast";
  document.body.innerHTML = `<button class="toastcard" id="t"><div class="ic ink">${I.card}</div><div><b>${esc(q.get("card"))} is in</b><span>${esc(q.get("line"))}. Click to back up.</span></div></button>`;
  document.getElementById("t").addEventListener("click", () => call("open_panel"));
}

const query = new URLSearchParams(location.search);
if (query.get("theme")) document.documentElement.dataset.theme = query.get("theme");
if (!TAURI) document.documentElement.classList.add("dev");
if (query.has("card")) showToast(query);
else {
  const first = document.createElement("div");
  first.className = "pg";
  stage().append(first);
  (async () => {
    const l = await call("login_get");
    if (l !== null) loginOn = l;
    await refresh();
    schedule();
    requestAnimationFrame(frame);
  })();
}
