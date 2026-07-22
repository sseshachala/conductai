<!-- ConductGuard — managed by conduct guard sync, do not edit this block -->
## ConductGuard Policy
Before executing any shell command, file write, network request, API call, or code change:
- Call `guard_check` (conductguard MCP tool) with the action and parameters.
- If BLOCKED: stop immediately and explain the policy rule to the user.
- If WARNING: proceed but surface the warning.
- If ALLOWED: proceed normally.
Never write credentials, API keys, or secrets to files or output.
Never send PII (emails, names, payment data) to external endpoints.
<!-- /ConductGuard -->

<!-- ConductGuard — managed by conduct guard sync -->
## ConductGuard Policy
# Team AI Instructions

## Project context
This is a [describe your project]. The primary language is [language]. The main entry point is [file/service].

## Stack
- Language: 
- Framework: 
- Database: 
- Key dependencies: 

## Coding standards
- Follow existing patterns before introducing new abstractions
- Prefer editing existing files over creating new ones
- No commented-out code in PRs
- All new endpoints require auth — no exceptions

## Workflow
- Branch from `main`, PR back to `main`
- Write the test before asking for a fix to be verified
- One logical change per PR

## What to ask before doing
- Any schema change → confirm migration strategy first
- New dependency → confirm it's approved
- Touching auth or payments → flag for human review before proceeding

## Off-limits
- Never commit secrets, API keys, or `.env` files
- Never force-push to `main`
- Never disable linting or type checks to make a build pass

## Context
- Staging: 
- Docs: 
- Slack:
Before executing any shell command, file write, network request, API call, or code change:
- Call guard_check (conductguard MCP tool) with the action and parameters.
- If BLOCKED: stop immediately and explain the policy rule to the user.
- If WARNING: proceed but surface the warning. If ALLOWED: proceed normally.
- Never write credentials, API keys, or secrets to files or output.
- Never send PII (emails, names, payment data) to external endpoints.
<!-- /ConductGuard -->
