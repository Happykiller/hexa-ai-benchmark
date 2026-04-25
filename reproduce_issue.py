
import json
import os
import sys

# Add the project root to sys.path to import modules
sys.path.append('/home/admin/sandbox/hexa-ai-benchmark')
sys.path.append('/home/admin/sandbox/hexa-ai-benchmark/auditor')

from auditor.main import TraceabilityValidator, _build_trace_metrics

path = 'livrables/20260424_1000_gemini-2.0-flash_0.7/'
traceability = TraceabilityValidator(path).validate()
trace_metrics = _build_trace_metrics(traceability)

print(f"Traceability status: {traceability['status']}")
print(f"Trace Metrics: {json.dumps(trace_metrics, indent=2)}")
