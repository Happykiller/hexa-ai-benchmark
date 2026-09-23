import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const BUCKET_LABELS = {
  operationality: "Opé",
  architecture: "Archi",
  quality: "Qual",
  traceability: "Traca",
  cost: "Coût",
};

// Deux sites construits depuis ce même code : la Todo List (défaut) et le benchmark Blender
// (`vite build -c vite.blender.config.js`, qui fixe VITE_KB_VARIANT=blender).
const VARIANT = import.meta.env.VITE_KB_VARIANT === "blender" ? "blender" : "todo";
const SITE = {
  todo: { dir: "knowledge_base", title: "Hexa-AI Benchmark", prompt: "le prompt d'évaluation" },
  blender: { dir: "knowledge_base_blender", title: "Hexa-AI Benchmark — Blender 3D", prompt: "l'énoncé du défi" },
}[VARIANT];
const BASE_URL = import.meta.env.DEV ? `/${SITE.dir}/` : "./";
const DATA_URL = `${BASE_URL}data.json`;
const PROMPT_URL = `${BASE_URL}evaluation_prompt.md`;

// Piliers d'une entrée, dans l'ordre du rapport : libellé court porté par l'entrée (KB
// Blender) ou, pour les entrées Todo publiées avant, la table BUCKET_LABELS.
function bucketKeys(entry) {
  return Object.keys(entry.bucket_scores || {}).filter((key) => bucketLabel(entry, key));
}

function bucketLabel(entry, key) {
  return entry.bucket_scores?.[key]?.short || BUCKET_LABELS[key];
}

// knowledge_base/data.js (écrit par kb/builder.py) embarque entrées + énoncé dans un <script>
// classique : c'est ce qui permet d'ouvrir index.html en file://, où tout fetch est bloqué.
// Sans lui (mode dev, ancien build), on retombe sur le fetch HTTP.
const EMBEDDED = typeof window !== "undefined" ? window.__HEXA_KB__ : undefined;

if (typeof document !== "undefined") document.title = `${SITE.title} KB`;

async function loadPrompt() {
  if (typeof EMBEDDED?.prompt === "string") return EMBEDDED.prompt;
  const r = await fetch(PROMPT_URL);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.text();
}

function parseMarkdown(text) {
  const escHtml = (s) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  function inlineFmt(s) {
    return escHtml(s)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>");
  }

  const lines = text.split("\n");
  let html = "";
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    let m;

    if (line.startsWith("```")) {
      i++;
      let code = "";
      while (i < lines.length && !lines[i].startsWith("```")) {
        code += lines[i] + "\n";
        i++;
      }
      i++;
      html += `<pre class="md-pre"><code>${escHtml(code.trimEnd())}</code></pre>`;
      continue;
    }

    if ((m = line.match(/^### (.+)/))) { html += `<h3 class="md-h3">${inlineFmt(m[1])}</h3>`; i++; continue; }
    if ((m = line.match(/^## (.+)/)))  { html += `<h2 class="md-h2">${inlineFmt(m[1])}</h2>`; i++; continue; }
    if ((m = line.match(/^# (.+)/)))   { html += `<h1 class="md-h1">${inlineFmt(m[1])}</h1>`; i++; continue; }

    if (line.match(/^---+$/)) { html += '<hr class="md-hr">'; i++; continue; }

    if (line.startsWith("|")) {
      const tableLines = [];
      while (i < lines.length && lines[i].startsWith("|")) { tableLines.push(lines[i]); i++; }
      if (tableLines.length >= 2) {
        const splitRow = (row) => row.split("|").slice(1, -1).map((c) => c.trim());
        const headers = splitRow(tableLines[0]);
        html += '<table class="md-table"><thead><tr>';
        headers.forEach((h) => { html += `<th>${inlineFmt(h)}</th>`; });
        html += "</tr></thead><tbody>";
        for (let j = 2; j < tableLines.length; j++) {
          html += "<tr>";
          splitRow(tableLines[j]).forEach((c) => { html += `<td>${inlineFmt(c)}</td>`; });
          html += "</tr>";
        }
        html += "</tbody></table>";
      }
      continue;
    }

    if (line.match(/^[-*] /)) {
      html += '<ul class="md-ul">';
      while (i < lines.length && lines[i].match(/^[-*] /)) {
        html += `<li>${inlineFmt(lines[i].slice(2))}</li>`;
        i++;
      }
      html += "</ul>";
      continue;
    }

    if (line.match(/^\d+\. /)) {
      html += '<ol class="md-ol">';
      while (i < lines.length && lines[i].match(/^\d+\. /)) {
        html += `<li>${inlineFmt(lines[i].replace(/^\d+\. /, ""))}</li>`;
        i++;
      }
      html += "</ol>";
      continue;
    }

    if (line.trim() === "") { i++; continue; }

    html += `<p class="md-p">${inlineFmt(line)}</p>`;
    i++;
  }

  return html;
}

function PromptModal({ onClose }) {
  const [content, setContent] = useState(null);
  const [error, setError] = useState(null);
  const overlayRef = useRef(null);

  useEffect(() => {
    loadPrompt()
      .then(setContent)
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  function handleOverlayClick(e) {
    if (e.target === overlayRef.current) onClose();
  }

  return (
    <div className="prompt-overlay" ref={overlayRef} onClick={handleOverlayClick}>
      <div className="prompt-modal">
        <div className="prompt-modal-header">
          <span className="prompt-modal-title">{VARIANT === "blender" ? "Énoncé du défi" : "Prompt d'évaluation"}</span>
          <button className="prompt-close" onClick={onClose} aria-label="Fermer">✕</button>
        </div>
        <div className="prompt-modal-body">
          {error ? (
            <p style={{ color: "var(--ko)" }}>Impossible de charger le prompt : {error}</p>
          ) : content === null ? (
            <p style={{ color: "var(--muted)" }}>Chargement…</p>
          ) : (
            <div
              className="md-body"
              dangerouslySetInnerHTML={{ __html: parseMarkdown(content) }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function scoreClass(percent) {
  if (percent >= 70) return "ok";
  if (percent >= 40) return "warn";
  return "ko";
}

function formatBucket(entry, bucketKey) {
  const bucket = entry.bucket_scores?.[bucketKey] ?? {};
  const normalized = Number(bucket.normalized_score ?? 0);
  const weight = Number(bucket.weight ?? 0);
  const percent = weight ? Math.round((normalized / weight) * 100) : 0;
  return { normalized, weight, percent };
}

function formatDuration(seconds) {
  const numeric = Number(seconds);
  if (!Number.isFinite(numeric) || numeric <= 0) return "—";
  const minutes = numeric / 60;
  return `${Math.round(minutes * 10) / 10} min`;
}

const LOG_ERROR_RE = /\b(error|fatal|exception|cannot|not found|failed|throw|undefined|null pointer|ENOENT|MODULE_NOT_FOUND)\b/i;
const LOG_WARN_RE  = /\b(warn|warning|deprecated|obsolete|partiel|skipped)\b/i;
const LOG_OK_RE    = /\b(healthy|started|created|ok|success|passed|admis|✓)\b/i;
const KV_RE        = /^([a-zA-Z_][a-zA-Z0-9_]*)=(.*)$/;
const CONTAINER_RE = /^([a-zA-Z0-9_.-]+-\d+\s+\|\s?)(.*)/;
const VIOLATION_RE = /^(.+\.[a-z]+)\s+[—–-]+\s+(.+?)\s+\(import:\s+(.+)\)$/;
const FILEPATH_RE  = /((?:src|dist|app|lib|node_modules)\/[^\s,)]+)/g;

function lineClass(text) {
  if (LOG_ERROR_RE.test(text)) return "ll-err";
  if (LOG_WARN_RE.test(text))  return "ll-warn";
  if (LOG_OK_RE.test(text))    return "ll-ok";
  return "";
}

function highlightText(text) {
  const parts = [];
  let last = 0;
  let m;
  const re = new RegExp(FILEPATH_RE.source, "g");
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(<span key={last}>{text.slice(last, m.index)}</span>);
    parts.push(<span key={m.index} className="ll-path">{m[0]}</span>);
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(<span key={last}>{text.slice(last)}</span>);
  return parts.length ? parts : text;
}

function LogLine({ line, index }) {
  // Blank line → small gap
  if (!line.trim()) return <div className="ll-blank" />;

  // Section separator: --- label ---
  if (/^---/.test(line)) {
    const label = line.replace(/^-+\s*/, "").replace(/\s*-+$/, "").trim();
    return <div className="ll-sep">{label && <span className="ll-sep-label">{label}</span>}</div>;
  }

  // Stack trace "    at ..."
  if (/^\s{2,}at /.test(line)) {
    return <div className="ll-stack">{line}</div>;
  }

  // Container log "api-1  | content"
  const cm = line.match(CONTAINER_RE);
  if (cm) {
    const rest = cm[2];
    return (
      <div className={`ll ll-container ${lineClass(rest)}`}>
        <span className="ll-svc">{cm[1]}</span>
        <span className="ll-msg">{highlightText(rest)}</span>
      </div>
    );
  }

  // Hexagonal violation "src/file.ts — reason (import: pattern)"
  const vm = line.match(VIOLATION_RE);
  if (vm) {
    return (
      <div className="ll ll-violation">
        <span className="ll-path">{vm[1]}</span>
        <span className="ll-vsep"> — </span>
        <span className="ll-vreason">{vm[2]}</span>
        <span className="ll-vsep"> · import: </span>
        <span className="ll-vpattern">{vm[3]}</span>
      </div>
    );
  }

  // key=value line
  const kv = line.trim().match(KV_RE);
  if (kv && !line.includes(" ")) {
    const valClass = /^0$/.test(kv[2]) ? "ll-ok" : /^[1-9]/.test(kv[2]) ? "ll-err" : "";
    return (
      <div className="ll ll-kv">
        <span className="ll-key">{kv[1]}</span>
        <span className="ll-eq">=</span>
        <span className={`ll-val ${valClass}`}>{kv[2]}</span>
      </div>
    );
  }

  // Generic line
  return (
    <div className={`ll ${lineClass(line)}`}>
      {highlightText(line)}
    </div>
  );
}

function LogContent({ content }) {
  const lines = content.split("\n");
  // trim trailing blank lines
  while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
  return (
    <div className="log-viewer">
      {lines.map((line, i) => <LogLine key={i} line={line} index={i} />)}
    </div>
  );
}

function InfoModal({ label, content, onClose }) {
  const overlayRef = useRef(null);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="prompt-overlay" ref={overlayRef} onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}>
      <div className="prompt-modal">
        <div className="prompt-modal-header">
          <span className="prompt-modal-title">{label}</span>
          <button className="prompt-close" onClick={onClose} aria-label="Fermer">✕</button>
        </div>
        <div className="prompt-modal-body">
          <LogContent content={content} />
        </div>
      </div>
    </div>
  );
}

function DetailCard({ onOpenInfo, section }) {
  return (
    <section className="detail-card">
      <h3>{section.title}</h3>
      <div className="detail-items">
        {section.items.map((item) => (
          <div className="detail-item" key={`${section.title}-${item.label}`}>
            <span className="detail-label-wrap">
              <span className="detail-label">{item.label}</span>
              {item.tooltip ? (
                <button
                  aria-label={`Détails: ${item.label}`}
                  className={`info-icon ${item.cls || ""}`}
                  onClick={(e) => { e.stopPropagation(); onOpenInfo(item.label, item.tooltip); }}
                  type="button"
                >
                  i
                </button>
              ) : null}
            </span>
            <span className={`detail-value ${item.cls || ""}`}>{item.value}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function MediaFigure({ item, className = "" }) {
  if (!item) return <div className="media-item empty" />;
  const src = `${BASE_URL}${item.src}`;
  return (
    <figure className={`media-item ${item.kind} ${className}`}>
      {item.kind === "video" ? (
        <video autoPlay controls loop muted playsInline src={src} />
      ) : (
        <a href={src} rel="noreferrer" target="_blank">
          <img alt={item.label} loading="lazy" src={src} />
        </a>
      )}
      <figcaption>{item.label}</figcaption>
    </figure>
  );
}

// Visuels d'un audit Blender, groupés pour comparer : par vue, l'attendu (vignette du
// turnaround), le rendu de l'auditeur et la superposition des silhouettes ; puis les vidéos.
function MediaStrip({ entry }) {
  const byFile = (name) => entry.media.find((item) => item.file === name);
  const planche = entry.media.find((item) => item.shared);
  const rows = ["front", "side", "back"]
    .map((view) => [byFile(`concept_${view}.jpg`), byFile(`view_${view}.jpg`), byFile(`silhouette_${view}.png`)])
    .filter((row) => row.some(Boolean));
  const videos = entry.media.filter((item) => item.kind === "video");
  const sheets = entry.media.filter((item) => item.kind === "sheet");
  return (
    <div className="media-block" onClick={(e) => e.stopPropagation()}>
      {rows.length ? (
        <div className="media-compare">
          {planche ? <MediaFigure className="planche" item={planche} /> : null}
          {rows.flat().map((item, index) => (
            <MediaFigure item={item} key={item?.src || `empty-${index}`} />
          ))}
        </div>
      ) : null}
      {videos.length ? (
        <div className="media-videos">
          {videos.map((item) => <MediaFigure item={item} key={item.src} />)}
        </div>
      ) : null}
      {sheets.length ? (
        <details className="media-sheets">
          <summary>Images clés des animations</summary>
          {sheets.map((item) => <MediaFigure item={item} key={item.src} />)}
        </details>
      ) : null}
    </div>
  );
}

function EntryRow({ entry, expanded, onOpenInfo, onToggle }) {
  const model = entry.model || entry.agent || "—";
  const effort = entry.effort || "—";

  return (
    <>
      <tr className={`summary-row ${expanded ? "expanded" : ""}`} onClick={onToggle}>
        <td className="agent-cell">{model}</td>
        <td className="mono">{effort}</td>
        <td className="mono">{entry.session_id || "—"}</td>
        <td className="mono">{(entry.audit_started_at || "").slice(0, 16) || "—"}</td>
        <td className="mono">{formatDuration(entry.trace_metrics?.wall_s)}</td>
        <td className={`score ${scoreClass(entry.score_percentage)}`}>{entry.score_percentage}%</td>
        <td>
          <div className="bucket-list">
            {bucketKeys(entry).map((bucketKey) => {
              const bucket = formatBucket(entry, bucketKey);
              return (
                <span
                  className={`bucket ${scoreClass(bucket.percent)}`}
                  key={bucketKey}
                >
                  {bucketLabel(entry, bucketKey)} {bucket.percent}%
                </span>
              );
            })}
          </div>
        </td>
      </tr>
      {expanded ? (
        <tr className="detail-row">
          <td colSpan={7}>
            {entry.media?.length ? <MediaStrip entry={entry} /> : null}
            <div className="detail-grid">
              {entry.sections.map((section) => (
                <DetailCard
                  key={`${entry.id}-${section.title}`}
                  onOpenInfo={onOpenInfo}
                  section={section}
                />
              ))}
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

function fmtDatetime(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
}

function buildExportHTML(entries, promptContent, datetime) {
  const entriesJson = JSON.stringify(entries);
  const promptHtml = promptContent ? parseMarkdown(promptContent) : "";


  const css = `
:root{--ok:#1b7f54;--warn:#a15a08;--ko:#bf2f21;--na:#6e6458;--accent:#1f4f8f;
  --bg:#f2efe8;--paper:#fffdf8;--paper2:#fff9ee;--ink:#1d1a16;--muted:#6e6458;--line:#ddd0be;}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Georgia,"Palatino Linotype",serif;background:var(--bg);color:var(--ink);padding:28px 20px 60px}
.shell{max-width:1380px;margin:0 auto}
header{display:flex;align-items:baseline;gap:16px;margin-bottom:28px;padding-bottom:16px;border-bottom:1px solid var(--line)}
h1{font-size:clamp(28px,4vw,52px);line-height:1}
.sub{font-size:13px;color:var(--muted);font-family:monospace}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:24px}
.scard{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:14px 18px}
.sval{font-size:28px;font-weight:700;line-height:1;margin-bottom:6px}
.slbl{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
table{width:100%;border-collapse:collapse;background:var(--paper);border-radius:14px;border:1px solid var(--line);overflow:hidden;margin-bottom:20px}
th{background:#f1ede4;padding:10px 12px;font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;text-align:left;cursor:pointer;user-select:none;white-space:nowrap}
th:hover{background:#e8e2d8}
td{padding:10px 12px;font-size:14px;border-top:1px solid var(--line);vertical-align:middle}
.sr{cursor:pointer}.sr:hover td{background:rgba(255,249,238,.7)}.sr.open td{background:rgba(31,79,143,.05)}
.sr td:first-child::before{content:"▸ ";color:var(--muted);font-size:.7rem}
.sr.open td:first-child::before{content:"▾ "}
.dr td{padding:0;background:#fafaf7}
.dgrid{display:flex;flex-wrap:wrap;gap:10px;padding:12px 12px 14px 28px}
.dcard{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:12px 14px;min-width:190px;max-width:260px;flex:0 0 auto}
.dcard-t{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.kv{display:flex;justify-content:space-between;gap:8px;padding:3px 0;font-size:12px}
.kl{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:130px}
.kv{display:flex;justify-content:space-between;gap:8px;padding:3px 0;font-size:12px;align-items:center}
.kv code{font-size:11px;background:rgba(31,79,143,.08);color:var(--accent);padding:1px 4px;border-radius:3px}
.ok{color:var(--ok)}.warn{color:var(--warn)}.ko{color:var(--ko)}.na{color:var(--na)}
.score{font-weight:700;font-size:15px}
.bucket{display:inline-block;font-size:11px;font-weight:700;padding:2px 6px;border-radius:4px;margin:1px;border:1px solid}
.bucket.ok{color:var(--ok);border-color:#bbf7d0;background:#dcfce7}
.bucket.warn{color:var(--warn);border-color:#fde68a;background:#fef3c7}
.bucket.ko{color:var(--ko);border-color:#fecaca;background:#fee2e2}
.mono{font-family:"SFMono-Regular","Consolas",monospace;font-size:12px}
.badge{display:inline-block;font-size:11px;font-weight:700;padding:3px 8px;border-radius:6px}
.badge.ok{background:#dcfce7;color:var(--ok)}.badge.ko{background:#fee2e2;color:var(--ko)}.badge.warn{background:#fef3c7;color:var(--warn)}
.info-btn{display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;border-radius:50%;font-size:10px;font-weight:700;border:1px solid;cursor:pointer;margin-left:4px;background:transparent;flex-shrink:0;vertical-align:middle}
.info-btn.ok{color:var(--ok);border-color:var(--ok)}.info-btn.ko{color:var(--ko);border-color:var(--ko)}.info-btn.warn{color:var(--warn);border-color:var(--warn)}.info-btn.na,.info-btn.skip{color:var(--na);border-color:var(--line)}
#tt{display:none;position:fixed;z-index:999;background:#1d1a16;color:#e8dfc8;border-radius:10px;padding:12px 14px;max-width:480px;min-width:200px;font-size:12px;line-height:1.5;box-shadow:0 8px 24px rgba(0,0,0,.35);pointer-events:none}
#tt pre{white-space:pre-wrap;word-break:break-all;margin:0;font-family:monospace;font-size:11px}
#tt .tt-t{font-weight:700;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#a89070;margin-bottom:6px}
details.prompt-section{margin-top:32px;border:1px solid var(--line);border-radius:16px;overflow:hidden}
details.prompt-section summary{padding:16px 22px;cursor:pointer;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);background:var(--paper);user-select:none;list-style:none;display:flex;align-items:center;gap:10px}
details.prompt-section summary::before{content:"▸";font-size:.75rem}
details.prompt-section[open] summary::before{content:"▾"}
details.prompt-section summary:hover{background:var(--paper2)}
.prompt-body{padding:28px 32px;background:var(--paper);border-top:1px solid var(--line);max-height:70vh;overflow-y:auto}
.md-h1{font-size:22px;margin:0 0 14px}.md-h2{font-size:17px;margin:24px 0 10px;padding-bottom:5px;border-bottom:1px solid var(--line)}.md-h3{font-size:14px;margin:16px 0 6px;color:var(--accent)}
.md-p{margin:0 0 10px;font-size:14px;line-height:1.65}
.md-hr{border:none;border-top:1px solid var(--line);margin:20px 0}
.md-body code{font-family:monospace;font-size:12px;padding:1px 5px;border-radius:4px;background:rgba(31,79,143,.08);color:var(--accent)}
.md-pre{margin:12px 0;padding:14px 18px;background:#1d1a16;border-radius:10px;overflow-x:auto}
.md-pre code{background:none;padding:0;color:#e8dfc8;font-size:12px;line-height:1.5}
.md-table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}
.md-table th,.md-table td{padding:7px 10px;border:1px solid var(--line);text-align:left;vertical-align:top}
.md-table th{background:rgba(31,79,143,.06);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);cursor:default}
.md-ul,.md-ol{margin:4px 0 10px 18px;padding:0;font-size:14px}.md-ul li,.md-ol li{margin-bottom:3px}
`;

  const js = `
var E=${entriesJson};
var BL=${JSON.stringify(BUCKET_LABELS)};
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function sc(p){return p>=70?'ok':p>=40?'warn':'ko';}
function fmtD(s){var n=parseFloat(s);if(!isFinite(n)||n<=0)return '—';return(Math.round(n/60*10)/10)+' min';}
function bkts(e){var o='';for(var k in (e.bucket_scores||{})){var b=e.bucket_scores[k];var lbl=b.short||BL[k];if(!lbl)continue;var n=parseFloat(b.normalized_score)||0;var w=parseFloat(b.weight)||0;var p=w?Math.round(n/w*100):0;o+='<span class="bucket '+sc(p)+'" title="'+n.toFixed(1)+'/'+w+'">'+lbl+'&nbsp;'+p+'%</span>';}return o;}
var _tt=null;
function showTT(el,lbl,txt){_tt=document.getElementById('tt');_tt.innerHTML='<div class="tt-t">'+esc(lbl)+'</div><pre>'+esc(txt)+'</pre>';_tt.style.display='block';var r=el.getBoundingClientRect();_tt.style.left=(r.right+10)+'px';_tt.style.top=(r.top+window.scrollY-4)+'px';}
function hideTT(){if(_tt)_tt.style.display='none';}
document.addEventListener('mousemove',function(e){if(_tt&&_tt.style.display==='block'){var x=e.clientX+14,y=e.clientY+14;var pw=_tt.offsetWidth,ph=_tt.offsetHeight;if(x+pw>window.innerWidth-8)x=e.clientX-pw-8;if(y+ph>window.innerHeight-8)y=e.clientY-ph-8;_tt.style.left=x+'px';_tt.style.top=(y+window.scrollY)+'px';}});
function renderSecs(secs){return(secs||[]).map(function(s){var items=s.items.map(function(it){var cls=it.cls?' '+it.cls:'';var btn='';if(it.tooltip){var sl=esc(it.label).replace(/'/g,"&#39;");var st=esc(it.tooltip).replace(/'/g,"&#39;");btn='<button class="info-btn '+(it.cls||'')+'" onmouseenter="showTT(this,\\''+sl+'\\',\\''+st+'\\');" onmouseleave="hideTT()">ⓘ</button>';}return'<div class="kv"><span class="kl">'+esc(it.label)+btn+'</span><span class="kv-val'+cls+'">'+esc(it.value)+'</span></div>';}).join('');return'<div class="dcard"><div class="dcard-t">'+esc(s.title)+'</div>'+items+'</div>';}).join('');}
var _dir={};
function sort(col,field){var tb=document.getElementById('tb');var rows=[];Array.from(tb.querySelectorAll('.sr')).forEach(function(sr){rows.push({sr:sr,dr:document.getElementById('dr-'+sr.dataset.i)});});var d=(_dir[col]===1)?-1:1;_dir[col]=d;rows.sort(function(a,b){var av=E[+a.sr.dataset.i][field]||'';var bv=E[+b.sr.dataset.i][field]||'';var r=/^-?\\d+(?:\\.\\d+)?$/;if(r.test(String(av))&&r.test(String(bv)))return(parseFloat(av)-parseFloat(bv))*d;return String(av).localeCompare(String(bv))*d;});rows.forEach(function(r){tb.appendChild(r.sr);if(r.dr)tb.appendChild(r.dr);});}
function toggle(i){var dr=document.getElementById('dr-'+i);var open=dr.style.display==='';dr.style.display=open?'none':'';var sr=dr.previousElementSibling;if(sr)sr.classList.toggle('open',!open);}
function buildSummary(){var total=E.length;var admis=E.filter(function(e){return e.admission_status==='ADMIS';}).length;var avg=total?Math.round(E.reduce(function(s,e){return s+e.score_percentage;},0)/total*10)/10:0;var best=total?Math.max.apply(null,E.map(function(e){return e.score_percentage;})):0;var models=[...new Set(E.map(function(e){return e.model||e.agent;}))];return[{v:total,l:'Audits'},{v:models.length,l:'Modèles'},{v:'<span class="ok">'+admis+'</span>',l:'Admis ≥ 60%'},{v:avg+'%',l:'Score moyen'},{v:'<span class="ok">'+best+'%</span>',l:'Meilleur score'}].map(function(c){return'<div class="scard"><div class="sval">'+c.v+'</div><div class="slbl">'+c.l+'</div></div>';}).join('');}
function buildTable(){var tb=document.getElementById('tb');tb.innerHTML=E.map(function(e,i){var sc_=e.score_percentage;var date=(e.audit_started_at||'').slice(0,16)||'—';var model=esc(e.model||e.agent||'—');var summary='<tr class="sr" data-i="'+i+'" onclick="toggle('+i+')"><td><strong>'+model+'</strong></td><td class="mono">'+esc(e.effort||'—')+'</td><td class="mono">'+(e.session_id||'—')+'</td><td class="mono">'+date+'</td><td class="mono">'+fmtD(e.duration_seconds)+'</td><td class="score '+sc(sc_)+'">'+sc_+'%</td><td>'+bkts(e)+'</td></tr>';var detail='<tr class="dr" id="dr-'+i+'" style="display:none"><td colspan="7"><div class="dgrid">'+renderSecs(e.sections)+'</div></td></tr>';return summary+detail;}).join('');}
document.getElementById('summary').innerHTML=buildSummary();
buildTable();
document.getElementById('cnt').textContent=E.length+' résultat(s)';
`;

  const promptSection = promptHtml
    ? `<details class="prompt-section"><summary>📄 Prompt d'évaluation</summary><div class="prompt-body"><div class="md-body">${promptHtml}</div></div></details>`
    : "";

  return `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${SITE.title} KB — ${datetime}</title>
<style>${css}</style>
</head>
<body>
<div id="tt"></div>
<div class="shell">
  <header>
    <h1>${SITE.title}</h1>
    <span class="sub">KB export · ${datetime}</span>
  </header>
  <div class="summary" id="summary"></div>
  <p style="font-size:13px;color:var(--muted);margin-bottom:12px" id="cnt"></p>
  <table>
    <thead><tr>
      <th onclick="sort(0,'model')">Modèle ↕</th>
      <th onclick="sort(1,'effort')">Effort ↕</th>
      <th onclick="sort(2,'session_id')">Session ↕</th>
      <th onclick="sort(3,'audit_started_at')">Date ↕</th>
      <th onclick="sort(4,'duration_seconds')">Durée ↕</th>
      <th onclick="sort(5,'score_percentage')">Score % ↕</th>
      <th>Buckets</th>
    </tr></thead>
    <tbody id="tb"></tbody>
  </table>
  ${promptSection}
</div>
<script>${js}</script>
</body>
</html>`;
}

function SummaryCards({ entries }) {
  const models = new Set(entries.map((entry) => entry.model || entry.agent));
  const admitted = entries.filter((entry) => entry.admission_status === "ADMIS").length;
  const average = entries.length
    ? Math.round((entries.reduce((sum, entry) => sum + entry.score_percentage, 0) / entries.length) * 10) / 10
    : 0;
  const best = entries.length ? Math.max(...entries.map((entry) => entry.score_percentage)) : 0;

  const cards = [
    { label: "Audits", value: entries.length },
    { label: "Modèles", value: models.size },
    { label: "Admis ≥ 60%", value: admitted, className: "ok" },
    { label: "Score moyen", value: `${average}%` },
    { label: "Meilleur score", value: `${best}%`, className: "ok" },
  ];

  return (
    <div className="summary-cards">
      {cards.map((card) => (
        <article className="summary-card" key={card.label}>
          <div className={`summary-value ${card.className || ""}`}>{card.value}</div>
          <div className="summary-label">{card.label}</div>
        </article>
      ))}
    </div>
  );
}

export function App() {
  const [entries, setEntries] = useState([]);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  // Une ancre #<id d'entrée> dans l'URL ouvre ce run : lien partageable vers un audit.
  const [expandedIds, setExpandedIds] = useState(() => {
    const anchor = typeof window !== "undefined" ? decodeURIComponent(window.location.hash.slice(1)) : "";
    return new Set(anchor ? [anchor] : []);
  });
  const [sort, setSort] = useState({ field: "audit_started_at", direction: "desc" });
  const [infoModal, setInfoModal] = useState(null);
  const [promptOpen, setPromptOpen] = useState(false);
  const closePrompt = useCallback(() => setPromptOpen(false), []);
  const [exporting, setExporting] = useState(false);

  async function handleExport() {
    setExporting(true);
    try {
      let promptContent = "";
      try {
        promptContent = await loadPrompt();
      } catch {}
      const now = new Date();
      const datetime = fmtDatetime(now);
      const html = buildExportHTML(entries, promptContent, datetime);
      const blob = new Blob([html], { type: "text/html;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `hexa-ai-benchmark-kb-${datetime}.html`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setStatus("loading");
      try {
        let payload = EMBEDDED?.entries;
        if (!Array.isArray(payload)) {
          const response = await fetch(DATA_URL, { cache: "no-store" });
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          payload = await response.json();
        }
        if (cancelled) return;
        setEntries(payload);
        setStatus("ready");
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const allModels = useMemo(() => [...new Set(entries.map((entry) => entry.model || entry.agent))].sort(), [entries]);

  const sortedEntries = useMemo(() => {
    const next = [...entries];

    next.sort((left, right) => {
      const leftValue = left[sort.field] ?? "";
      const rightValue = right[sort.field] ?? "";
      const leftNum = Number(leftValue);
      const rightNum = Number(rightValue);
      const bothNumeric = !Number.isNaN(leftNum) && !Number.isNaN(rightNum) && `${leftValue}` !== "" && `${rightValue}` !== "";
      const result = bothNumeric
        ? leftNum - rightNum
        : String(leftValue).localeCompare(String(rightValue));
      return sort.direction === "asc" ? result : -result;
    });

    return next;
  }, [entries, sort]);

  function toggleExpanded(entryId) {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(entryId)) next.delete(entryId);
      else next.add(entryId);
      return next;
    });
  }

  function updateSort(field) {
    setSort((current) =>
      current.field === field
        ? { field, direction: current.direction === "asc" ? "desc" : "asc" }
        : { field, direction: "desc" },
    );
  }

  const closeInfoModal = useCallback(() => setInfoModal(null), []);

  return (
    <main className="page-shell">
      {infoModal && <InfoModal label={infoModal.label} content={infoModal.content} onClose={closeInfoModal} />}
      {promptOpen && <PromptModal onClose={closePrompt} />}
      <header className="hero">
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <button
            className="prompt-trigger"
            onClick={() => setPromptOpen(true)}
            title={`Voir ${SITE.prompt}`}
            aria-label={`Voir ${SITE.prompt}`}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
              <polyline points="10 9 9 9 8 9"/>
            </svg>
          </button>
          <button
            className="prompt-trigger"
            onClick={handleExport}
            disabled={exporting || entries.length === 0}
            title="Exporter en HTML autonome"
            aria-label="Exporter en HTML autonome"
          >
            {exporting ? (
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.5 }}>
                <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
              </svg>
            ) : (
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
            )}
          </button>
          <h1>{SITE.title}</h1>
        </div>
      </header>

      {status === "loading" ? <section className="panel">Chargement de `data.json`…</section> : null}
      {status === "error" ? <section className="panel error">Impossible de charger la KB: {error}</section> : null}

      {status === "ready" ? (
        <>
          <section className="panel table-panel">
            <table>
              <thead>
                <tr>
                  <th onClick={() => updateSort("model")}>Modèle</th>
                  <th onClick={() => updateSort("effort")}>Effort</th>
                  <th onClick={() => updateSort("session_id")}>Session</th>
                  <th onClick={() => updateSort("audit_started_at")}>Date</th>
                  <th onClick={() => updateSort("duration_seconds")}>Duration</th>
                  <th onClick={() => updateSort("score_percentage")}>Score %</th>
                  <th>Buckets</th>
                </tr>
              </thead>
              <tbody>
                {sortedEntries.map((entry) => (
                  <EntryRow
                    entry={entry}
                    expanded={expandedIds.has(entry.id)}
                    key={entry.id}
                    onOpenInfo={(label, content) => setInfoModal({ label, content })}
                    onToggle={() => toggleExpanded(entry.id)}
                  />
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : null}
    </main>
  );
}
