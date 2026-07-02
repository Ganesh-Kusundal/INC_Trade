#!/usr/bin/env bash
# collect.sh — Automated metric collection for Codebuff's metric-historian
# Run this periodically (daily, or after significant changes) to track quality trends
# Usage: bash .qoder/metrics/collect.sh
# Output: Creates timestamped entries in .qoder/metrics/

set -euo pipefail

METRICS_DIR=".qoder/metrics"
DATE=$(date +%Y%m%d)
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Ensure metrics directory exists
mkdir -p "$METRICS_DIR"

echo "Collecting metrics for $DATE..."

# --- 1. Test Coverage ---
if command -v pytest &>/dev/null; then
    COVERAGE=$(pytest --cov --cov-report=term-missing 2>/dev/null | grep "TOTAL" | awk '{print $4}' | sed 's/%//' || echo "0")
else
    COVERAGE="0"
fi
echo "  test_coverage: ${COVERAGE}%"

# --- 2. Module Coupling (cross-layer imports in brokers/common) ---
COMMON_FILE="brokers/common/broker_port.py"
if [ -f "$COMMON_FILE" ]; then
    CROSS_BROKER_IMPORTS=$(grep -c "from brokers.dhan\|from brokers.upstox" "$COMMON_FILE" 2>/dev/null || echo "0")
else
    CROSS_BROKER_IMPORTS="0"
fi
echo "  cross_broker_imports: $CROSS_BROKER_IMPORTS"

# --- 3. Circular Dependencies ---
# Check for circular imports using a simple heuristic: A imports B imports A
CIRCULAR=$(python3 -c "
import ast, glob, sys
edges = set()
for f in glob.glob('brokers/**/*.py', recursive=True)+glob.glob('domain/**/*.py', recursive=True):
    try:
        with open(f) as fh:
            tree = ast.parse(fh.read())
        module = f.replace('/', '.').replace('.py','')
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                edges.add((module, node.module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    edges.add((module, alias.name))
    except:
        pass
# Simple cycle detection
visited = set()
def dfs(node, path):
    if node in path:
        idx = path.index(node)
        print(' -> '.join(path[idx:] + [node]))
        return 1
    if node in visited:
        return 0
    visited.add(node)
    count = 0
    for (src, dst) in edges:
        if src == node and dst in [e[0] for e in edges]:
            count += dfs(dst, path + [node])
    return count
cycles = sum(dfs(n, []) for n in set([e[0] for e in edges]) | set([e[1] for e in edges]))
print(cycles)
" 2>/dev/null || echo "0")
echo "  circular_deps: $CIRCULAR"

# --- 4. File count ---
FILE_COUNT=$(find . -name "*.py" -not -path "./.venv/*" -not -path "./venv/*" -not -path "./.qoder/*" -not -path "./node_modules/*" | wc -l)
TEST_COUNT=$(find . -name "test_*.py" -not -path "./.venv/*" -not -path "./venv/*" -not -path "./node_modules/*" | wc -l)
echo "  py_files: $FILE_COUNT"
echo "  test_files: $TEST_COUNT"

# --- 5. Error handling coverage ---
TOTAL_FUNCTIONS=$(grep -r "def " --include="*.py" brokers/ domain/ application/ 2>/dev/null | grep -v "test_" | grep -v "__pycache__" | wc -l || echo "0")
TYPED_ERRORS=$(grep -r "raise " --include="*.py" brokers/ 2>/dev/null | grep -E "(Error|Exception)\(" | wc -l || echo "0")
if [ "$TOTAL_FUNCTIONS" -gt 0 ]; then
    ERROR_PCT=$((TYPED_ERRORS * 100 / TOTAL_FUNCTIONS))
else
    ERROR_PCT=0
fi
echo "  error_handling_pct: ${ERROR_PCT}%"

# --- 6. Memory entries ---
MEMORY_COUNT=$(find .qoder/memory/ -name "*.md" 2>/dev/null | wc -l)
echo "  memory_entries: $MEMORY_COUNT"

# --- 7. Coupling score for auto-optimize ---
if [ -f "$COMMON_FILE" ]; then
    COUPLING_SCORE=$((100 - CROSS_BROKER_IMPORTS * 10))
    if [ $COUPLING_SCORE -lt 0 ]; then COUPLING_SCORE=0; fi
else
    COUPLING_SCORE=0
fi
echo "  coupling_score: $COUPLING_SCORE"

# --- Write snapshot ---
SNAPSHOT_FILE="$METRICS_DIR/snapshot-$DATE.json"
cat > "$SNAPSHOT_FILE" <<EOF
{
    "date": "$TIMESTAMP",
    "metrics": {
        "test_coverage_pct": $COVERAGE,
        "cross_broker_imports": $CROSS_BROKER_IMPORTS,
        "circular_dependencies": $CIRCULAR,
        "py_files": $FILE_COUNT,
        "test_files": $TEST_COUNT,
        "error_handling_pct": $ERROR_PCT,
        "memory_entries": $MEMORY_COUNT,
        "coupling_score": $COUPLING_SCORE
    }
}
EOF

echo "Snapshot saved to $SNAPSHOT_FILE"
echo ""
echo "=== Current Metrics Summary ==="
echo "Coverage:       ${COVERAGE}%"
echo "Coupling:       ${COUPLING_SCORE}/100 (${CROSS_BROKER_IMPORTS} cross-broker imports)"
echo "Cyclic deps:    ${CIRCULAR}"
echo "Python files:   ${FILE_COUNT} (${TEST_COUNT} test files)"
echo "Error handling: ${ERROR_PCT}%"
echo "Memory entries: ${MEMORY_COUNT}"
echo ""
echo "Done. Run 'python3 .qoder/metrics/trend.py' for trend analysis."
