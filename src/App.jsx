import { useEffect, useMemo, useState } from "react";

const BUCKET_LABELS = {
  operationality: "Opé",
  architecture: "Archi",
  quality: "Qual",
  traceability: "Traca",
};

const DATA_URL = import.meta.env.DEV ? "/knowledge_base/data.json" : "./data.json";

function scoreClass(percent) {
  if (percent >= 70) return "ok";
  if (percent >= 40) return "warn";
  return "ko";
}

function statusClass(status) {
  if (status === "ADMIS") return "ok";
  if (status === "ECHEC") return "ko";
  return "na";
}

function formatBucket(entry, bucketKey) {
  const bucket = entry.bucket_scores?.[bucketKey] ?? {};
  const normalized = Number(bucket.normalized_score ?? 0);
  const weight = Number(bucket.weight ?? 0);
  const percent = weight ? Math.round((normalized / weight) * 100) : 0;
  return { normalized, weight, percent };
}

function Tooltip({ tooltip }) {
  if (!tooltip) return null;

  return (
    <div className="tooltip-panel" style={{ left: tooltip.x, top: tooltip.y }}>
      <div className="tooltip-title">{tooltip.label}</div>
      <pre>{tooltip.content}</pre>
    </div>
  );
}

function DetailCard({ onHideTooltip, onShowTooltip, onUpdateTooltipPosition, section }) {
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
                  onBlur={onHideTooltip}
                  onFocus={(event) => onShowTooltip(item.label, item.tooltip, event)}
                  onMouseEnter={(event) => onShowTooltip(item.label, item.tooltip, event)}
                  onMouseLeave={onHideTooltip}
                  onMouseMove={onUpdateTooltipPosition}
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

function EntryRow({ entry, expanded, onHideTooltip, onShowTooltip, onToggle, onUpdateTooltipPosition }) {
  return (
    <>
      <tr className={`summary-row ${expanded ? "expanded" : ""}`} onClick={onToggle}>
        <td className="agent-cell">{entry.agent}</td>
        <td className="mono">{entry.session_id || "—"}</td>
        <td className="mono">{(entry.audit_started_at || "").slice(0, 16) || "—"}</td>
        <td className={`score ${scoreClass(entry.score_percentage)}`}>{entry.score_percentage}%</td>
        <td>
          <div className="bucket-list">
            {Object.keys(BUCKET_LABELS).map((bucketKey) => {
              const bucket = formatBucket(entry, bucketKey);
              return (
                <span
                  className={`bucket ${scoreClass(bucket.percent)}`}
                  key={bucketKey}
                  title={`${bucket.normalized.toFixed(1)}/${bucket.weight}`}
                >
                  {BUCKET_LABELS[bucketKey]} {bucket.percent}%
                </span>
              );
            })}
          </div>
        </td>
        <td>
          <div className="badge-list">
            <span className={`badge ${statusClass(entry.admission_status)}`}>{entry.admission_status}</span>
            {entry.score_capped ? <span className="badge warn">CAPÉ</span> : null}
            {entry.skip_dynamic ? <span className="badge na">-DYN</span> : null}
          </div>
        </td>
        <td className="mono">{(entry.scoring_model || "").replace("indicator_fibonacci_v1", "fib_v1")}</td>
      </tr>
      {expanded ? (
        <tr className="detail-row">
          <td colSpan={7}>
            <div className="detail-grid">
              {entry.sections.map((section) => (
                <DetailCard
                  key={`${entry.id}-${section.title}`}
                  onHideTooltip={onHideTooltip}
                  onShowTooltip={onShowTooltip}
                  onUpdateTooltipPosition={onUpdateTooltipPosition}
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

function SummaryCards({ entries }) {
  const agents = new Set(entries.map((entry) => entry.agent));
  const admitted = entries.filter((entry) => entry.admission_status === "ADMIS").length;
  const average = entries.length
    ? Math.round((entries.reduce((sum, entry) => sum + entry.score_percentage, 0) / entries.length) * 10) / 10
    : 0;
  const best = entries.length ? Math.max(...entries.map((entry) => entry.score_percentage)) : 0;

  const cards = [
    { label: "Audits", value: entries.length },
    { label: "Agents", value: agents.size },
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
  const [selectedAgents, setSelectedAgents] = useState([]);
  const [selectedStatus, setSelectedStatus] = useState("");
  const [minimumScore, setMinimumScore] = useState(0);
  const [expandedIds, setExpandedIds] = useState(() => new Set());
  const [sort, setSort] = useState({ field: "audit_started_at", direction: "desc" });
  const [tooltip, setTooltip] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setStatus("loading");
      try {
        const response = await fetch(DATA_URL, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (cancelled) return;
        setEntries(payload);
        setSelectedAgents([...new Set(payload.map((entry) => entry.agent))]);
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

  const allAgents = useMemo(() => [...new Set(entries.map((entry) => entry.agent))].sort(), [entries]);

  const filteredEntries = useMemo(() => {
    const allSelected = selectedAgents.length === allAgents.length;
    const next = entries.filter((entry) => {
      const agentOk = allSelected || selectedAgents.includes(entry.agent);
      const statusOk = !selectedStatus || entry.admission_status === selectedStatus;
      const scoreOk = Number(entry.score_percentage) >= minimumScore;
      return agentOk && statusOk && scoreOk;
    });

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
  }, [allAgents.length, entries, minimumScore, selectedAgents, selectedStatus, sort]);

  function toggleAgent(agent) {
    setSelectedAgents((current) =>
      current.includes(agent) ? current.filter((value) => value !== agent) : [...current, agent].sort(),
    );
  }

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

  function resetFilters() {
    setSelectedAgents(allAgents);
    setSelectedStatus("");
    setMinimumScore(0);
  }

  function onShowTooltip(label, content, event) {
    const rect = event.currentTarget.getBoundingClientRect();
    setTooltip({
      label,
      content,
      x: rect.right + 12,
      y: rect.top + window.scrollY - 4,
    });
  }

  function onUpdateTooltipPosition(event) {
    setTooltip((current) => {
      if (!current) return current;
      return {
        ...current,
        x: event.clientX + 18,
        y: event.clientY + 18,
      };
    });
  }

  function onHideTooltip() {
    setTooltip(null);
  }

  return (
    <main className="page-shell">
      <Tooltip tooltip={tooltip} />
      <header className="hero">
        <div>
          <p className="eyebrow">Hexa-AI Benchmark</p>
          <h1>Knowledge Base</h1>
          <p className="hero-copy">Base statique d’audits, enrichie par les rapports JSON et Markdown.</p>
        </div>
        <div className="hero-meta">
          <span>{entries.length} audit(s)</span>
          <span>{allAgents.length} agent(s)</span>
        </div>
      </header>

      {status === "loading" ? <section className="panel">Chargement de `data.json`…</section> : null}
      {status === "error" ? <section className="panel error">Impossible de charger la KB: {error}</section> : null}

      {status === "ready" ? (
        <>
          <SummaryCards entries={entries} />

          <section className="panel filters">
            <div className="filter-group">
              <span className="filter-label">Agents</span>
              <div className="chip-list">
                {allAgents.map((agent) => {
                  const active = selectedAgents.includes(agent);
                  return (
                    <button
                      className={`chip ${active ? "active" : ""}`}
                      key={agent}
                      onClick={() => toggleAgent(agent)}
                      type="button"
                    >
                      {agent}
                    </button>
                  );
                })}
              </div>
            </div>

            <label className="stacked-field">
              <span className="filter-label">Statut</span>
              <select value={selectedStatus} onChange={(event) => setSelectedStatus(event.target.value)}>
                <option value="">Tous</option>
                <option value="ADMIS">ADMIS</option>
                <option value="ECHEC">ÉCHEC</option>
              </select>
            </label>

            <label className="stacked-field">
              <span className="filter-label">Score minimal</span>
              <input
                max="100"
                min="0"
                onChange={(event) => setMinimumScore(Number(event.target.value))}
                type="range"
                value={minimumScore}
              />
              <span className="muted">{minimumScore}%</span>
            </label>

            <button className="ghost-button" onClick={resetFilters} type="button">
              Réinitialiser
            </button>
          </section>

          <section className="panel table-panel">
            <div className="table-header">
              <strong>{filteredEntries.length} résultat(s)</strong>
            </div>
            <table>
              <thead>
                <tr>
                  <th onClick={() => updateSort("agent")}>Agent</th>
                  <th onClick={() => updateSort("session_id")}>Session</th>
                  <th onClick={() => updateSort("audit_started_at")}>Date</th>
                  <th onClick={() => updateSort("score_percentage")}>Score %</th>
                  <th>Buckets</th>
                  <th>Statut</th>
                  <th>Scoring</th>
                </tr>
              </thead>
              <tbody>
                {filteredEntries.map((entry) => (
                  <EntryRow
                    entry={entry}
                    expanded={expandedIds.has(entry.id)}
                    key={entry.id}
                    onHideTooltip={onHideTooltip}
                    onShowTooltip={onShowTooltip}
                    onToggle={() => toggleExpanded(entry.id)}
                    onUpdateTooltipPosition={onUpdateTooltipPosition}
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
