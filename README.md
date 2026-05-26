# conduct-cli

Official CLI for [Conduct AI](https://conductai.ai) — install AI agents, manage projects, and run end-to-end tests from the terminal.

## Install

```bash
pip install conduct-cli
```

## Quick start

```bash
# Authenticate (one-time)
conduct login \
  --server https://api.conductai.ai \
  --api-key cond_live_xxx \
  --workspace <workspace-id>

# Browse available agents
conduct playbooks

# Create a project and install all agents in one shot
conduct install-all --project DevOps --repo owner/repo

# List installed agents
conduct agents

# Run a test trigger on any agent
conduct test "PR Reviewer"
conduct test --all
```

## Commands

| Command | Description |
|---------|-------------|
| `conduct login` | Save connection config to `~/.conduct/config.json` |
| `conduct projects` | List all projects |
| `conduct create project <name>` | Create a project |
| `conduct delete project <name>` | Delete a project and all its agents |
| `conduct reset project <name>` | Delete all agents in a project (clean slate) |
| `conduct playbooks` | Browse available playbooks |
| `conduct playbooks <slug>` | Show required inputs for a playbook |
| `conduct install <slug>` | Install one agent from a playbook |
| `conduct install-all` | Install all 12 playbooks into a project |
| `conduct agents` | List all installed agents |
| `conduct test <name>` | Fire test trigger on an agent and stream results |
| `conduct test --all` | Test every playbook-based agent |

## Authentication

Generate an API key from **Settings → API Keys** in the Conduct AI dashboard. Keys start with `cond_live_` and are stored as SHA-256 hashes — the plaintext is shown only once.

```bash
conduct login --server https://api.conductai.ai --api-key cond_live_xxx --workspace <id>
```

## Install all agents

```bash
# Installs all 12 playbooks into a project, pointed at your GitHub repo
conduct install-all --project DevOps --repo myorg/myrepo
```

If the project doesn't exist it's created automatically. Use `--input key=value` to override any playbook input.

## Test agents

```bash
# Test a single agent (fires synthetic test payload, streams run events)
conduct test "Autopilot Quick"

# Test all playbook-based agents in sequence
conduct test --all
```

Exit code is `0` if all pass, `1` if any fail — works in CI.

## Links

- Dashboard: [conductai.ai](https://conductai.ai)
- Docs: [conductai.ai/docs](https://conductai.ai/docs)
- Issues: [github.com/sseshachala/conductai/issues](https://github.com/sseshachala/conductai/issues)
