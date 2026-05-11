BASE_SCORE_BUCKETS = {
    "operationality": {
        "label": "Operationnalite",
        "weight": 50,
        "selectors": [{"phase": 1}],
    },
    "architecture": {
        "label": "Architecture",
        "weight": 25,
        "selectors": [{"phase": 2, "steps": [1, 4, 5, 6]}],
    },
    "quality": {
        "label": "Qualite logicielle",
        "weight": 15,
        "selectors": [{"phase": 2, "steps": [2, 3]}],
    },
    "traceability": {
        "label": "Discipline et tracabilite",
        "weight": 10,
        "selectors": [{"phase": 3}],
    },
}


BONUS_MALUS_SCORE_CONFIG = {
    "phase_number": 4,
    "phase_label": "Bonus / Malus",
    "bonus_cap": 5,
    "malus_cap": -10,
}


TRACE_SCORING_CONFIG = {
    "total_turns": {
        "phase_number": 3,
        "phase_label": "Traçabilité",
        "step_number": 2,
        "step_label": "Efficacité de la session (audit_trace.json)",
        "name": "Nombre total d'échanges (turns)",
        "description": "Nombre total de tours de parole User <-> Agent",
        "bands_label": "5..15=100%, 2..25=50%, else=0%",
        "weight": 5,
        "bands": [
            {"min": 5, "max": 15, "score_ratio": 1.0, "status": "OK", "label": "excellent"},
            {"min": 2, "max": 25, "score_ratio": 0.5, "status": "PARTIEL", "label": "acceptable"},
        ],
    },
    "total_tool_calls": {
        "phase_number": 3,
        "phase_label": "Traçabilité",
        "step_number": 2,
        "step_label": "Efficacité de la session (audit_trace.json)",
        "name": "Nombre total d'appels d'outils",
        "description": "Nombre total d'actions effectuées (shell, fs, etc.)",
        "bands_label": "20..60=100%, 10..100=50%, else=0%",
        "weight": 3,
        "bands": [
            {"min": 20, "max": 60, "score_ratio": 1.0, "status": "OK", "label": "target"},
            {"min": 10, "max": 100, "score_ratio": 0.5, "status": "PARTIEL", "label": "tolerated"},
        ],
    },
    "total_wall_time_seconds": {
        "phase_number": 3,
        "phase_label": "Traçabilité",
        "step_number": 2,
        "step_label": "Efficacité de la session (audit_trace.json)",
        "name": "Temps réel total (secondes)",
        "description": "Temps total d'horloge en secondes",
        "bands_label": "600..1800=100%, 300..3600=50%, else=0%",
        "weight": 2,
        "bands": [
            {"min": 600, "max": 1800, "score_ratio": 1.0, "status": "OK", "label": "target"},
            {"min": 300, "max": 3600, "score_ratio": 0.5, "status": "PARTIEL", "label": "tolerated"},
        ],
    },
}


TECHNICAL_STATS_SCORING_CONFIG = {
    "total_files": {
        "phase_number": 5,
        "phase_label": "Statistiques techniques",
        "step_number": 1,
        "step_label": "Mesures du codebase",
        "name": "Nombre total de fichiers",
        "description": "count(files)",
        "bands_label": "30..120=100%, 15..160=50%, else=0%",
        "weight": 1,
        "bands": [
            {"min": 30, "max": 120, "score_ratio": 1.0, "status": "OK", "label": "target"},
            {"min": 15, "max": 160, "score_ratio": 0.5, "status": "PARTIEL", "label": "tolerated"},
        ],
    },
    "total_ts_files": {
        "phase_number": 5,
        "phase_label": "Statistiques techniques",
        "step_number": 1,
        "step_label": "Mesures du codebase",
        "name": "Nombre total de fichiers TS/TSX",
        "description": "count(.ts, .tsx)",
        "bands_label": "20..80=100%, 10..110=50%, else=0%",
        "weight": 1,
        "bands": [
            {"min": 20, "max": 80, "score_ratio": 1.0, "status": "OK", "label": "target"},
            {"min": 10, "max": 110, "score_ratio": 0.5, "status": "PARTIEL", "label": "tolerated"},
        ],
    },
    "total_lines": {
        "phase_number": 5,
        "phase_label": "Statistiques techniques",
        "step_number": 1,
        "step_label": "Mesures du codebase",
        "name": "Nombre total de lignes TS/TSX",
        "description": "sum(lines in .ts/.tsx files)",
        "bands_label": "1000..5000=100%, 500..7000=50%, else=0%",
        "weight": 1,
        "bands": [
            {"min": 1000, "max": 5000, "score_ratio": 1.0, "status": "OK", "label": "target"},
            {"min": 500, "max": 7000, "score_ratio": 0.5, "status": "PARTIEL", "label": "tolerated"},
        ],
    },
    "total_tests": {
        "phase_number": 5,
        "phase_label": "Statistiques techniques",
        "step_number": 1,
        "step_label": "Mesures du codebase",
        "name": "Nombre de fichiers de test",
        "description": "count(.test.ts, .spec.ts, or files in tests/)",
        "bands_label": "10..50=100%, 5..70=50%, else=0%",
        "weight": 1,
        "bands": [
            {"min": 10, "max": 50, "score_ratio": 1.0, "status": "OK", "label": "target"},
            {"min": 5, "max": 70, "score_ratio": 0.5, "status": "PARTIEL", "label": "tolerated"},
        ],
    },
    "total_size_kb": {
        "phase_number": 5,
        "phase_label": "Statistiques techniques",
        "step_number": 1,
        "step_label": "Mesures du codebase",
        "name": "Taille totale du projet (KB)",
        "description": "sum(file_size_bytes)/1024",
        "bands_label": "50..2048=100%, 20..3072=50%, else=0%",
        "weight": 1,
        "bands": [
            {"min": 50, "max": 2048, "score_ratio": 1.0, "status": "OK", "label": "target"},
            {"min": 20, "max": 3072, "score_ratio": 0.5, "status": "PARTIEL", "label": "tolerated"},
        ],
    },
}
