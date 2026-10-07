#!/usr/bin/env bash
# Run every example (or the ones you name) in its own throwaway env via `uv`.
# Separate envs because current CrewAI and OpenAI Agents pin incompatible `openai` majors.
#
#   ./run_all.sh                       # live_smoke + all five agents
#   ./run_all.sh smoke                 # no LLM: every adapter vs your live policy
#   ./run_all.sh langchain crewai      # just these
#
# Needs: uv, CONDUCT_AGENT_TOKEN (falls back to ~/.conduct/config.json from `conduct login`),
# and an LLM: ANTHROPIC_API_KEY or OPENAI_API_KEY, or the Conduct Gateway
# (set *_BASE_URL + DEMO_PROVIDER + DEMO_MODEL=cond-<code>-<alias>; see README).
set -euo pipefail
cd "$(dirname "$0")"

CFG="$HOME/.conduct/config.json"
if [[ -z "${CONDUCT_AGENT_TOKEN:-}" && -f "$CFG" ]]; then
  CONDUCT_AGENT_TOKEN=$(python3 -c "import json;print(json.load(open('$CFG'))['agent_token'])")
  CONDUCT_WORKSPACE_ID=${CONDUCT_WORKSPACE_ID:-$(python3 -c "import json;print(json.load(open('$CFG')).get('workspace_id',''))")}
  export CONDUCT_AGENT_TOKEN CONDUCT_WORKSPACE_ID
fi
: "${CONDUCT_AGENT_TOKEN:?set CONDUCT_AGENT_TOKEN or run 'conduct login'}"

run() {  # run <extras> <script> [extra pip packages...]
  local extras=$1 script=$2; shift 2
  local withs=(); for p in "$@"; do withs+=(--with "$p"); done
  echo; echo "=== $script"
  uv run --quiet --no-project --python 3.12 --with-editable "..[$extras]" ${withs[@]+"${withs[@]}"} python "$script" \
    || echo "!!! $script failed"
}

targets=("$@"); [[ ${#targets[@]} -eq 0 ]] && targets=(smoke claude openai langchain adk crewai)
for t in "${targets[@]}"; do
  case $t in
    smoke)     run claude,openai,langchain,adk live_smoke.py
               run crewai live_smoke.py ;;
    claude)    run claude claude_agent_sdk_example.py ;;
    openai)    run openai openai_agents_example.py "openai-agents[litellm]" ;;
    langchain) run langchain langchain_example.py langchain-anthropic langchain-openai ;;
    adk)       run adk adk_example.py litellm ;;
    crewai)    run crewai crewai_example.py "crewai[anthropic]" "crewai[litellm]" ;;
    *) echo "unknown example: $t (smoke|claude|openai|langchain|adk|crewai)"; exit 2 ;;
  esac
done
