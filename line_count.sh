#!/bin/bash
# Count LifePilot source lines by module
cd "$(dirname "$0")" || exit 1

echo "LifePilot line count"
echo "================================"
echo ""

# ── src/ modules (Python) ──────────────────────────
echo "  src/"
echo "  ────────────────────────────"

for dir in agents db llm mcp memory tools; do
  count=$(find "src/$dir" -name "*.py" -exec cat {} + 2>/dev/null | wc -l)
  printf "    %-16s %5s lines\n" "$dir/" "$count"
done

src_root=$(cat src/__init__.py src/bot.py 2>/dev/null | wc -l)
printf "    %-16s %5s lines\n" "(root)" "$src_root"

src_total=$(find src -name "*.py" -exec cat {} + 2>/dev/null | wc -l)
echo "  ────────────────────────────"
printf "    %-16s %5s lines\n" "src total" "$src_total"

echo ""

# ── config/ (YAML) ─────────────────────────────────
echo "  config/"
echo "  ────────────────────────────"
config_count=$(find config -name "*.yaml" -o -name "*.yml" 2>/dev/null | xargs cat 2>/dev/null | wc -l)
printf "    %-16s %5s lines\n" "yaml" "$config_count"

echo ""

# ── skills/ (Markdown) ─────────────────────────────
echo "  skills/"
echo "  ────────────────────────────"
skills_count=$(find skills -name "*.md" -exec cat {} + 2>/dev/null | wc -l)
printf "    %-16s %5s lines\n" "md" "$skills_count"

echo ""

# ── tests/ ──────────────────────────────────────────
echo "  tests/"
echo "  ────────────────────────────"
tests_count=$(find tests -name "*.py" -exec cat {} + 2>/dev/null | wc -l)
printf "    %-16s %5s lines\n" "python" "$tests_count"

echo ""

# ── root-level files ────────────────────────────────
echo "  root files"
echo "  ────────────────────────────"

for f in Dockerfile docker-compose.yml requirements.txt setup.sh start.sh .gitignore .env.example README.md; do
  if [ -f "$f" ]; then
    c=$(wc -l < "$f")
    printf "    %-24s %5s lines\n" "$f" "$c"
  fi
done

echo ""

# ── grand total ─────────────────────────────────────
echo "  ================================"
py_total=$(find . -name "*.py" ! -path "./.git/*" -exec cat {} + 2>/dev/null | wc -l)
all_total=$(find . \( -name "*.py" -o -name "*.yaml" -o -name "*.yml" -o -name "*.md" -o -name "*.sh" -o -name "*.txt" -o -name "Dockerfile" -o -name "docker-compose.yml" \) ! -path "./.git/*" -exec cat {} + 2>/dev/null | wc -l)
printf "  Python total:       %5s lines\n" "$py_total"
printf "  All files total:    %5s lines\n" "$all_total"
echo ""
