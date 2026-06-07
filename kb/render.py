import json
from typing import Any, Dict, List, Optional

from .markdown_parser import truncate


def item(label: str, value: str, cls: Optional[str] = None, tooltip: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"label": label, "value": value, "cls": cls}
    if tooltip:
        payload["tooltip"] = tooltip
    return payload


def bool_item(label: str, val: Optional[bool], tooltip: Optional[str] = None) -> Dict[str, Any]:
    if val is None:
        return item(label, "—", "na", tooltip)
    return item(label, "✓", "ok", tooltip) if val else item(label, "✗", "ko", tooltip)


def status_item(label: str, status: Optional[str], tooltip: Optional[str] = None) -> Dict[str, Any]:
    cls = {"OK": "ok", "KO": "ko", "SKIPPED": "skip", "SUCCESS": "ok", "FAILED": "ko"}.get(status or "", "na")
    return item(label, status or "?", cls, tooltip)


def section(title: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"title": title, "items": items}


def section_scores(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    labels = {
        "operationality": "Opérationnalité",
        "architecture": "Architecture",
        "quality": "Qualité logicielle",
        "traceability": "Traçabilité",
    }
    items = []
    for key, label in labels.items():
        bucket = entry["bucket_scores"].get(key, {})
        norm = float(bucket.get("normalized_score", 0))
        weight = float(bucket.get("weight", 0))
        pct = round(norm / weight * 100) if weight else 0
        cls = "ok" if pct >= 70 else "warn" if pct >= 40 else "ko"
        items.append(item(label, f"{norm:.1f} / {weight} ({pct}%)", cls))
    if entry.get("score_capped"):
        caps = ", ".join(entry.get("score_caps") or [])
        tt_caps = (entry.get("_tooltips") or {}).get("score_caps")
        items.append(item("Cap appliqué", caps, "warn", tt_caps))
    items.append(item("Modèle scoring", entry["scoring_model"].replace("indicator_fibonacci_", "fib_")))
    return section("Score détaillé", items)


def first_trace_finding(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    report = entry.get("report_markdown") or {}
    for finding in report.get("top_findings") or []:
        code = str(finding.get("code") or "")
        phase = str(finding.get("phase") or "").lower()
        if code.startswith("3-") or "traçabilité" in phase or "traceability" in phase:
            return finding
    return None


def fmt_score(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "0"
    return str(int(numeric)) if numeric.is_integer() else f"{numeric:.1f}"


def trace_indicator_tooltip(indicator: Dict[str, Any]) -> str:
    lines = [
        str(indicator.get("step") or ""),
        f"Code: {indicator.get('code') or ''}",
        f"Statut: {indicator.get('status') or '?'}",
        f"Score: {fmt_score(indicator.get('score'))}/{fmt_score(indicator.get('max_score'))}",
    ]
    if indicator.get("measured_value") is not None:
        lines.append(f"Valeur mesurée: {indicator.get('measured_value')}")
    if indicator.get("remarks"):
        lines.append(f"Remarques: {indicator.get('remarks')}")

    details = indicator.get("details") or {}
    if details:
        detail_lines = []
        for key, value in details.items():
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            if isinstance(value, dict):
                value = json.dumps(value, ensure_ascii=False)
            detail_lines.append(f"{key}: {value}")
        if detail_lines:
            lines.append("Détails:")
            lines.extend(detail_lines)

    return "\n".join(line for line in lines if line)


def trace_indicator_label(indicator: Dict[str, Any]) -> str:
    code = str(indicator.get("code") or "")
    name = str(indicator.get("name") or "")
    if code == "3-1-1" and name == "Fichier audit_trace.json":
        name = "Validation audit_trace.json"
    return f"{code} {name}".strip()


def section_trace_diagnostic(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    bucket = (entry.get("bucket_scores") or {}).get("traceability", {})
    trace_metrics = entry.get("trace_metrics") or {}
    trace_indicators = entry.get("traceability_indicators") or []
    has_bucket = bool(bucket)
    has_metrics = any(value is not None for value in trace_metrics.values())
    if not has_bucket and not has_metrics and not trace_indicators:
        return None

    norm = float(bucket.get("normalized_score", 0) or 0)
    weight = float(bucket.get("weight", 0) or 0)
    pct = round(norm / weight * 100) if weight else 0
    cls = "ok" if pct >= 70 else "warn" if pct >= 40 else "ko"

    items = [item("Score trace", f"{norm:.1f} / {weight:.1f} ({pct}%)" if weight else f"{norm:.1f}", cls)]

    for indicator in trace_indicators:
        status = str(indicator.get("status") or "?")
        status_cls = {"OK": "ok", "KO": "ko", "SKIPPED": "skip", "FAILED": "ko", "PARTIEL": "warn"}.get(status, "na")
        score = f"{fmt_score(indicator.get('score'))}/{fmt_score(indicator.get('max_score'))}"
        label = trace_indicator_label(indicator)
        items.append(item(truncate(label, 52), f"{status} · {score}", status_cls, trace_indicator_tooltip(indicator)))

    if not trace_indicators:
        trace_error = (entry.get("_tooltips") or {}).get("trace_errors")
        trace_finding = first_trace_finding(entry)
        if trace_error:
            first_error = trace_error.splitlines()[0]
            items.append(item("Trace", truncate(first_error, 72), "ko", trace_error))
        elif trace_finding:
            remarks = trace_finding.get("remarks") or trace_finding.get("status") or "à vérifier"
            items.append(
                item(
                    "Trace",
                    truncate(str(remarks), 72),
                    "ko" if trace_finding.get("kind") == "failed" else "warn",
                    trace_finding.get("tooltip"),
                )
            )

    return section("Détail traçabilité", items)


def section_pipeline(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    make_targets = entry.get("make_targets")
    if not make_targets:
        return None
    tooltips = (entry.get("_tooltips") or {}).get("make", {})
    items = [status_item(f"make {target}", status, tooltips.get(target)) for target, status in make_targets.items()]
    docker = entry.get("docker") or {}
    waited = f" ({docker['waited_s']}s)" if docker.get("waited_s") is not None else ""
    items.append(status_item(f"docker start{waited}", docker.get("status", "?"), tooltips.get("docker")))
    return section("Pipeline", items)


def section_stats(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    stats = entry.get("stats")
    if not stats:
        return None
    items = []
    if stats.get("files") is not None:
        items.append(item("Fichiers", f'{stats["files"]} ({stats.get("ts_files")} .ts)'))
    if stats.get("lines") is not None:
        items.append(item("Lignes TS", str(stats["lines"])))
    if stats.get("test_files") is not None:
        items.append(item("Fichiers test", str(stats["test_files"])))
    tests_pass, tests_fail = stats.get("tests_pass") or 0, stats.get("tests_fail") or 0
    if tests_pass or tests_fail:
        value = f"{tests_pass} ✓" + (f" / {tests_fail} ✗" if tests_fail else "")
        items.append(item("Tests exécutés", value, "ko" if tests_fail else "ok"))
    coverage = stats.get("coverage")
    if coverage is not None:
        cls = "ok" if coverage >= 80 else "warn" if coverage >= 60 else "ko"
        items.append(item("Coverage", f"{coverage}%", cls))
    return section("Stats projet", items) if items else None


def section_checks(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    hexa = entry.get("hexagonal") or {}
    auth = entry.get("auth_static") or {}
    injection = entry.get("injection") or {}
    dual_persistence = entry.get("dual_persistence") or {}
    tooltips = entry.get("_tooltips") or {}
    if not any([hexa, auth, injection, dual_persistence]):
        return None

    items = []
    if hexa:
        violations = hexa.get("violations", 0)
        rules = f'{hexa.get("rules_ok")}/{hexa.get("rules_total")} règles'
        value = rules + (f" ({violations} viol.)" if violations else "")
        items.append(item("Hexagonal", value, "ok" if hexa.get("status") == "OK" else "ko", tooltips.get("hexa_violations")))
    if auth:
        items.extend(
            [
                bool_item("JWT library", auth.get("jwt")),
                bool_item("Auth mutations", auth.get("mutations")),
                bool_item(
                    "Auth guard",
                    auth.get("guard"),
                    None
                    if auth.get("guard")
                    else "Pattern attendu: isAuthenticated|authGuard|AuthGuard|verifyToken|@Authorized — non détecté dans src/",
                ),
                bool_item("Password hash", auth.get("hashing")),
            ]
        )
    if injection:
        items.extend(
            [
                bool_item("No direct new", injection.get("no_direct"), tooltips.get("inj_violations")),
                bool_item("@injectable", injection.get("injectable")),
                bool_item("@inject param", injection.get("inject")),
                bool_item("Ctor inject", injection.get("ctor_deps")),
            ]
        )
    if dual_persistence:
        items.extend(
            [
                bool_item("Mongoose installé", dual_persistence.get("mongoose")),
                bool_item("SQL ORM installé", dual_persistence.get("sql_orm")),
                bool_item("Mongo (tasks)", dual_persistence.get("mongoose_tasks")),
                bool_item("SQL (users)", dual_persistence.get("sql_users")),
                bool_item("Adapters séparés", dual_persistence.get("adapters")),
            ]
        )
    return section("Checks statiques", items)


def section_e2e(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tooltips = (entry.get("_tooltips") or {}).get("e2e", {})
    if entry.get("skip_dynamic"):
        return section("E2E", [item("Phase dynamique", "ignorée (--skip-dynamic)", "skip")])

    e2e_steps = entry.get("e2e_steps") or {}
    auth_e2e_steps = entry.get("auth_e2e_steps") or {}
    if not e2e_steps and not auth_e2e_steps:
        docker = entry.get("docker") or {}
        make_tooltips = (entry.get("_tooltips") or {}).get("make", {})
        docker_status = docker.get("status") or "NON_EXECUTE"
        cls = "ok" if docker_status == "OK" else "ko" if docker_status == "KO" else "skip"
        detail = make_tooltips.get("docker")
        label = "Runtime GraphQL" if docker_status == "KO" else "Scénario E2E"
        value = docker_status if docker_status != "NON_EXECUTE" else "non exécuté"
        return section("E2E", [item(label, value, cls, detail)])

    items = [bool_item(step, ok, tooltips.get(step)) for step, ok in e2e_steps.items()]
    items.extend(
        [bool_item(step.replace("Auth: ", ""), ok, tooltips.get(step)) for step, ok in auth_e2e_steps.items()]
    )
    return section("E2E", items) if items else None


def section_trace(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    trace_metrics = entry.get("trace_metrics")
    if not trace_metrics or trace_metrics.get("turns") is None:
        return None
    items = []
    if entry.get("agent"):
        items.append(item("Livrable", str(entry["agent"])))
    if entry.get("prompt_version"):
        items.append(item("Prompt version", str(entry["prompt_version"])))
    if trace_metrics.get("phases") is not None:
        items.append(item("Phases", str(trace_metrics["phases"])))
    turns = trace_metrics.get("turns")
    if turns is not None:
        cls = "ok" if 5 <= turns <= 15 else "warn" if 2 <= turns <= 25 else "ko"
        items.append(item("Turns", str(int(turns)), cls))
    tools = trace_metrics.get("tools")
    if tools is not None:
        cls = "ok" if 20 <= tools <= 60 else "warn" if 10 <= tools <= 100 else "ko"
        items.append(item("Tool calls", str(int(tools)), cls))
    wall_s = trace_metrics.get("wall_s")
    if wall_s is not None:
        cls = "ok" if 600 <= wall_s <= 1800 else "warn" if 300 <= wall_s <= 3600 else "ko"
        items.append(item("Wall time", f"{round(wall_s / 60, 1)} min", cls))
    if trace_metrics.get("errors"):
        tt_trace = (entry.get("_tooltips") or {}).get("trace_errors")
        items.append(item("Erreurs trace", str(trace_metrics["errors"]), "ko", tt_trace))
    return section("Trace session", items)


def section_bonuses(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    bonuses = entry.get("bonuses") or []
    maluses = entry.get("maluses") or []
    if not bonuses and not maluses:
        return None
    items = [item(bonus["reason"][:50], "✓ obtenu" if bonus["ok"] else "absent", "ok" if bonus["ok"] else "na") for bonus in bonuses]
    items.extend(
        [
            item(malus["reason"][:50], "! détecté" if malus["detected"] else "✓ non détecté", "ko" if malus["detected"] else "ok")
            for malus in maluses
        ]
    )
    return section("Bonus / Malus", items)


def section_report(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    report = entry.get("report_markdown") or {}
    findings = report.get("top_findings") or []
    summary = report.get("summary_metrics") or {}
    if not report and not findings:
        return None

    items = []
    if report.get("source_file"):
        report_name = report["source_file"].split("/")[-1]
        items.append(item("Rapport MD", "rapport", tooltip=report_name))
    final_score = summary.get("Pourcentage final du score net")
    if final_score:
        items.append(item("Score rapport", final_score))
    for idx, finding in enumerate(findings[:4], start=1):
        title = finding.get("indicator") or finding.get("code") or f"Constat {idx}"
        items.append(
            item(
                f"Constat {idx}",
                truncate(f"{title} — {finding.get('remarks') or finding.get('status') or 'à vérifier'}", 92),
                "ko" if finding.get("kind") == "failed" else "warn",
                finding.get("tooltip"),
            )
        )
    return section("Synthèse rapport", items) if items else None


SECTION_EXTRACTORS = [
    section_scores,
    section_trace_diagnostic,
    section_pipeline,
    section_stats,
    section_checks,
    section_e2e,
    section_trace,
    section_bonuses,
    section_report,
]


def build_sections(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    sections = [section_data for extractor in SECTION_EXTRACTORS for section_data in [extractor(entry)] if section_data]
    if entry["scoring_model"] == "legacy":
        sections.append(
            section(
                "Note",
                [
                    item("Format", "legacy — checks détaillés non disponibles", "na"),
                    item("Conseil", "Relancer l'audit pour le détail complet", "na"),
                ],
            )
        )
    return sections


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hexa-AI Benchmark — Knowledge Base</title>
<style>
:root{
  --ok:#16a34a;--ok-bg:#dcfce7;--ok-bd:#bbf7d0;
  --warn:#b45309;--warn-bg:#fef3c7;--warn-bd:#fde68a;
  --ko:#dc2626;--ko-bg:#fee2e2;--ko-bd:#fecaca;
  --na:#6b7280;--na-bg:#f3f4f6;
  --border:#e5e7eb;--bg:#f8fafc;--card:#fff;
  --text:#111827;--muted:#6b7280;--hbg:#1e293b;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text)}
header{background:var(--hbg);color:#f1f5f9;padding:1.25rem 2rem;display:flex;justify-content:space-between;align-items:center}
header h1{font-size:1.15rem;font-weight:700}
header .sub{font-size:.75rem;color:#94a3b8;margin-top:.15rem}
.wrap{max-width:1380px;margin:0 auto;padding:1.5rem 2rem}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:.875rem;margin-bottom:1.5rem}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:1rem 1.25rem}
.card .val{font-size:1.9rem;font-weight:700;line-height:1.1}
.card .lbl{font-size:.72rem;color:var(--muted);margin-top:.2rem;text-transform:uppercase;letter-spacing:.04em}
.toolbar{display:flex;gap:.625rem;margin-bottom:1rem;flex-wrap:wrap;align-items:center}
.toolbar select{border:1px solid var(--border);border-radius:6px;padding:.375rem .65rem;font-size:.825rem;background:var(--card)}
.toolbar input[type=range]{width:100px;cursor:pointer}
.toolbar .rlbl{font-size:.8rem;color:var(--muted)}
.toolbar button{border:1px solid var(--border);border-radius:6px;padding:.375rem .75rem;font-size:.825rem;background:var(--card);cursor:pointer}
.toolbar button:hover{background:var(--bg)}
#count{margin-left:auto;font-size:.775rem;color:var(--muted)}
table{width:100%;border-collapse:collapse;background:var(--card);border-radius:8px;border:1px solid var(--border);overflow:hidden}
th{background:#f1f5f9;padding:.55rem .75rem;font-size:.72rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;text-align:left;cursor:pointer;user-select:none;white-space:nowrap}
th:hover{background:#e2e8f0}
td{padding:.6rem .75rem;font-size:.85rem;border-top:1px solid var(--border);vertical-align:middle}
.sr{cursor:pointer}.sr:hover td{background:#f8fafc}
.sr td:first-child::before{content:'▸ ';color:var(--muted);font-size:.7rem}
.sr.open td:first-child::before{content:'▾ ';color:var(--text)}
.dr td{padding:0;background:#fafbfc}
.detail-grid{display:flex;flex-wrap:wrap;gap:.75rem;padding:1rem 1rem 1rem 2.5rem}
.dcard{background:var(--card);border:1px solid var(--border);border-radius:7px;padding:.75rem 1rem;min-width:195px;max-width:270px;flex:0 0 auto}
.dcard-title{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:.5rem;padding-bottom:.35rem;border-bottom:1px solid var(--border)}
.kv{display:flex;justify-content:space-between;align-items:center;gap:.5rem;padding:.18rem 0;font-size:.8rem}
.kv-lbl{color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:130px}
.kv-val{font-weight:500;white-space:nowrap}
.ok{color:var(--ok)}.warn{color:var(--warn)}.ko{color:var(--ko)}.na{color:var(--na)}
.score{font-weight:700;font-size:.9rem}
.bucket{display:inline-block;font-size:.7rem;font-weight:600;padding:.12rem .35rem;border-radius:3px;margin:1px;border:1px solid}
.bucket.ok{color:var(--ok);border-color:var(--ok-bd);background:var(--ok-bg)}
.bucket.warn{color:var(--warn);border-color:var(--warn-bd);background:var(--warn-bg)}
.bucket.ko{color:var(--ko);border-color:var(--ko-bd);background:var(--ko-bg)}
.badge{display:inline-block;font-size:.68rem;font-weight:600;padding:.12rem .4rem;border-radius:4px}
.badge.ok{background:var(--ok-bg);color:var(--ok)}.badge.ko{background:var(--ko-bg);color:var(--ko)}
.badge.warn{background:var(--warn-bg);color:var(--warn)}.badge.na{background:var(--na-bg);color:var(--na)}
.mono{font-family:'SF Mono','Fira Code',monospace;font-size:.78rem}
.muted{color:var(--muted)}.buckets{white-space:nowrap}
.dropdown{position:relative;display:inline-block}
.dropdown-btn{border:1px solid var(--border);border-radius:6px;padding:.375rem .65rem;font-size:.825rem;background:var(--card);cursor:pointer;white-space:nowrap;min-width:140px;text-align:left}
.dropdown-btn:after{content:' ▾';opacity:.5;float:right;margin-left:.5rem}
.dropdown-menu{display:none;position:absolute;top:100%;left:0;z-index:99;background:var(--card);border:1px solid var(--border);border-radius:6px;min-width:200px;max-height:260px;overflow-y:auto;box-shadow:0 4px 12px rgba(0,0,0,.08);padding:.25rem 0}
.dropdown-menu.open{display:block}
.dropdown-menu label{display:flex;align-items:center;gap:.5rem;padding:.35rem .75rem;font-size:.825rem;cursor:pointer;white-space:nowrap}
.dropdown-menu label:hover{background:var(--bg)}
.dropdown-menu input[type=checkbox]{cursor:pointer}
.sep{height:1px;background:var(--border);margin:.25rem 0}
.info-btn{display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;border-radius:50%;font-size:.65rem;font-weight:700;border:1px solid;cursor:pointer;margin-left:.35rem;vertical-align:middle;line-height:1;background:transparent;flex-shrink:0}
.info-btn.ok{color:var(--ok);border-color:var(--ok)}
.info-btn.ko{color:var(--ko);border-color:var(--ko)}
.info-btn.warn{color:var(--warn);border-color:var(--warn)}
.info-btn.na,.info-btn.skip{color:var(--na);border-color:var(--na)}
.info-btn:not([class*=ok]):not([class*=ko]):not([class*=warn]){color:var(--muted);border-color:var(--border)}
#tt-panel{display:none;position:fixed;z-index:999;background:#1e293b;color:#e2e8f0;border-radius:8px;
  padding:1rem 1.1rem;max-width:520px;min-width:220px;font-size:.78rem;line-height:1.55;
  box-shadow:0 8px 24px rgba(0,0,0,.35);pointer-events:none}
#tt-panel pre{white-space:pre-wrap;word-break:break-all;margin:0;font-family:'SF Mono','Fira Code',monospace;font-size:.75rem}
#tt-panel .tt-title{font-weight:700;font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:#94a3b8;margin-bottom:.5rem}
</style>
</head>
<body>
<header>
  <div>
    <h1>Hexa-AI Benchmark — Knowledge Base</h1>
    <div class="sub" id="hdr-sub"></div>
  </div>
</header>
<div id="tt-panel"></div>
<div class="wrap">
  <div class="cards" id="summary-cards"></div>
  <div class="toolbar"><span id="count"></span></div>
  <table>
    <thead><tr id="thead-row"></tr></thead>
    <tbody id="tbody"></tbody>
  </table>
</div>

<script>
var ENTRIES = /*ENTRIES_JSON*/;

function esc(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function sc(pct){ return pct>=70?'ok':pct>=40?'warn':'ko'; }
function fmtDuration(seconds){var n=parseFloat(seconds); if(!isFinite(n)||n<=0) return '—'; return (Math.round((n/60)*10)/10)+' min';}
function bucketHtml(e){
  var labels={operationality:'Opé',architecture:'Archi',quality:'Qual',traceability:'Traca'};
  var out='';
  for(var k in labels){
    var b=(e.bucket_scores||{})[k]||{};
    var norm=parseFloat(b.normalized_score)||0;
    var w=parseFloat(b.weight)||0;
    var pct=w?Math.round(norm/w*100):0;
    out+='<span class="bucket '+sc(pct)+'" title="'+norm.toFixed(1)+'/'+w+'">'+labels[k]+'&nbsp;'+pct+'%</span>';
  }
  return out;
}
function badgesHtml(e){
  var b='<span class="badge '+(e.admission_status==='ADMIS'?'ok':'ko')+'">'+(e.admission_status==='ADMIS'?'ADMIS':'ÉCHEC')+'</span>';
  if(e.score_capped) b+=' <span class="badge warn" title="'+esc((e.score_caps||[]).join(' | '))+'">CAPÉ</span>';
  if(e.skip_dynamic) b+=' <span class="badge na">-DYN</span>';
  return b;
}
var _ttPanel=null;
function _ensurePanel(){if(!_ttPanel)_ttPanel=document.getElementById('tt-panel');}
function showTT(e,label,text){_ensurePanel();_ttPanel.innerHTML='<div class="tt-title">'+esc(label)+'</div><pre>'+esc(text)+'</pre>';_ttPanel.style.display='block';moveTT(e);}
function moveTT(e){_ensurePanel();var x=e.clientX+14,y=e.clientY+14;var pw=_ttPanel.offsetWidth,ph=_ttPanel.offsetHeight;if(x+pw>window.innerWidth-8) x=e.clientX-pw-8;if(y+ph>window.innerHeight-8) y=e.clientY-ph-8;_ttPanel.style.left=x+'px';_ttPanel.style.top=y+'px';}
function hideTT(){_ensurePanel();_ttPanel.style.display='none';}
document.addEventListener('mousemove',function(e){if(_ttPanel&&_ttPanel.style.display==='block')moveTT(e);});
function renderSections(sections){
  return (sections||[]).map(function(sec){
    var items=sec.items.map(function(it){
      var cls=it.cls?(' '+it.cls):''; var btn='';
      if(it.tooltip){
        var btnCls=it.cls||''; var safeLabel=esc(it.label).replace(/'/g,'&#39;'); var safeText=esc(it.tooltip).replace(/'/g,'&#39;');
        btn='<button class="info-btn '+btnCls+'" onmouseenter="showTT(event,\''+safeLabel+'\',\''+safeText+'\')" onmouseleave="hideTT()" onclick="event.stopPropagation()" title="Détails">ⓘ</button>';
      }
      return '<div class="kv"><span class="kv-lbl">'+esc(it.label)+btn+'</span><span class="kv-val'+cls+'">'+esc(it.value)+'</span></div>';
    }).join('');
    return '<div class="dcol"><div class="dcard"><div class="dcard-title">'+esc(sec.title)+'</div>'+items+'</div></div>';
  }).join('');
}
var COLS=[{label:'Modèle',sort:true,field:'model'},{label:'Effort',sort:true,field:'effort'},{label:'Session',sort:true,field:'session_id'},{label:'Date',sort:true,field:'audit_started_at'},{label:'Duration',sort:true,field:'duration_seconds'},{label:'Score %',sort:true,field:'score_percentage'},{label:'Buckets',sort:false,field:null}];
var _dir={};
function buildTable(){
  var thead=document.getElementById('thead-row');
  thead.innerHTML=COLS.map(function(c,i){return c.sort?'<th onclick="sortT('+i+')">'+c.label+' <span style="opacity:.4">↕</span></th>':'<th>'+c.label+'</th>';}).join('');
  var tb=document.getElementById('tbody');
  tb.innerHTML=ENTRIES.map(function(e,i){
    var score=e.score_percentage; var date=(e.audit_started_at||'').slice(0,16)||'—'; var model=e.model||e.agent||'—'; var effort=e.effort||'—';
    var summary='<tr class="sr" data-idx="'+i+'" data-agent="'+esc(model)+'" data-status="'+esc(e.admission_status)+'" data-score="'+score+'" onclick="toggle('+i+')"><td><strong>'+esc(model)+'</strong></td><td class="mono">'+esc(effort)+'</td><td class="mono">'+(e.session_id||'—')+'</td><td class="mono">'+date+'</td><td class="mono">'+fmtDuration(e.duration_seconds)+'</td><td class="score '+sc(score)+'">'+score+'%</td><td class="buckets">'+bucketHtml(e)+'</td></tr>';
    var detail='<tr class="dr" id="dr-'+i+'" style="display:none"><td colspan="7"><div class="detail-grid">'+renderSections(e.sections)+'</div></td></tr>';
    return summary+detail;
  }).join('');
}
function toggle(i){var dr=document.getElementById('dr-'+i); var open=dr.style.display===''; dr.style.display=open?'none':''; var sr=dr.previousElementSibling; if(sr) sr.classList.toggle('open',!open);}
function updateCount(){document.getElementById('count').textContent=ENTRIES.length+' résultat(s)';}
function sortT(col){
  var field=COLS[col].field; if(!field) return; var tb=document.getElementById('tbody'); var pairs=[]; Array.from(tb.querySelectorAll('.sr')).forEach(function(sr){pairs.push({sr:sr,dr:document.getElementById('dr-'+sr.dataset.idx)});});
  var dir=(_dir[col]===1)?-1:1; _dir[col]=dir;
  pairs.sort(function(a,b){var av=ENTRIES[parseInt(a.sr.dataset.idx)][field]||''; var bv=ENTRIES[parseInt(b.sr.dataset.idx)][field]||''; var numRe=/^-?\d+(?:\.\d+)?$/; if(numRe.test(String(av).trim())&&numRe.test(String(bv).trim())){return(parseFloat(av)-parseFloat(bv))*dir;} return String(av).localeCompare(String(bv))*dir;});
  pairs.forEach(function(p){tb.appendChild(p.sr); if(p.dr) tb.appendChild(p.dr);});
}
function buildSummaryCards(){
  var total=ENTRIES.length; var agents=[...new Set(ENTRIES.map(function(e){return e.model||e.agent;}))]; var admis=ENTRIES.filter(function(e){return e.admission_status==='ADMIS';}).length;
  var avg=total?Math.round(ENTRIES.reduce(function(s,e){return s+e.score_percentage;},0)/total*10)/10:0; var best=total?Math.max.apply(null,ENTRIES.map(function(e){return e.score_percentage;})):0;
  document.getElementById('summary-cards').innerHTML=[{val:total,lbl:'Audits'},{val:agents.length,lbl:'Modèles'},{val:'<span style="color:var(--ok)">'+admis+'</span>',lbl:'Admis ≥ 60%'},{val:avg+'%',lbl:'Score moyen'},{val:'<span style="color:var(--ok)">'+best+'%</span>',lbl:'Meilleur score'}].map(function(c){return '<div class="card"><div class="val">'+c.val+'</div><div class="lbl">'+c.lbl+'</div></div>';}).join('');
  var now=new Date().toLocaleString('fr-FR',{dateStyle:'short',timeStyle:'short'}); document.getElementById('hdr-sub').textContent='Générée le '+now+' · '+total+' audit(s) · '+agents.length+' modèle(s)';
}
buildSummaryCards(); buildTable(); updateCount();
</script>
</body>
</html>
"""


def build_html(entries: List[Dict[str, Any]]) -> str:
    entries_json = json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    return HTML_TEMPLATE.replace("/*ENTRIES_JSON*/", entries_json)
