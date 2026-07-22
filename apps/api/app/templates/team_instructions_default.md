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
