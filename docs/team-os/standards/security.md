# Standard: Security for AI-Generated Code

**When to use this:** Any change touching user input handling, authentication, file access, external calls, or data storage.

AI coding tools are fast and fluent. They are also statistically likely to reproduce the most common vulnerability patterns in their training data. This checklist exists to catch the patterns that appear most often in AI-generated code.

---

## The short list (check every PR)

**Injection**
- [ ] No user input concatenated into SQL — use parameterised queries or an ORM
- [ ] No user input passed to `os.system`, `subprocess`, `exec`, `eval`, or `child_process`
- [ ] No user-controlled strings rendered in templates without escaping

**File access**
- [ ] File paths from user input are resolved to an absolute path and verified to stay within the intended directory before reading or writing
```python
# Safe pattern
resolved = (base_dir / user_path).resolve()
resolved.relative_to(base_dir.resolve())  # raises ValueError if outside
```

**Secrets**
- [ ] No API keys, tokens, or passwords in source code or committed config files
- [ ] Secrets come from environment variables, not hardcoded defaults
- [ ] Secrets are not logged, not returned in error responses, not included in API responses

**Cryptography**
- [ ] No MD5 or SHA-1 for password hashing or signatures — use SHA-256+ or bcrypt/argon2
- [ ] No `verify=False` on HTTPS calls, no `rejectUnauthorized: false`
- [ ] No `Math.random()` or `random.random()` for security-sensitive values — use `secrets` module or `crypto.randomBytes`

**Sensitive data**
- [ ] PII (email, names, IDs) is not logged at INFO or DEBUG level
- [ ] Error responses don't include stack traces, internal paths, or SQL errors
- [ ] API responses don't include fields the caller shouldn't see (check your serialiser excludes)

---

## The patterns AI tools get wrong most often

### SQL injection via f-strings

AI tools frequently generate this:
```python
# WRONG — SQL injection
query = f"SELECT * FROM users WHERE email = '{email}'"
db.execute(query)
```

The correct pattern:
```python
# RIGHT — parameterised
db.execute(text("SELECT * FROM users WHERE email = :email"), {"email": email})
# or with ORM
db.query(User).filter(User.email == email)
```

### Path traversal

AI tools often skip the bounds check:
```python
# WRONG — path traversal
file_path = base_dir / user_filename
content = file_path.read_text()
```

The correct pattern:
```python
# RIGHT — resolved and bounded
file_path = (base_dir / user_filename).resolve()
file_path.relative_to(base_dir.resolve())  # raises ValueError if escaping
content = file_path.read_text()
```

### Secrets in defaults

```python
# WRONG — secret in default
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
```

If this ships to production (and it will), the "change me" doesn't get changed. No default for secrets — fail loudly if the env var is missing:
```python
# RIGHT — no default
SECRET_KEY = os.environ["SECRET_KEY"]  # raises KeyError if not set
```

### Over-broad CORS

```python
# WRONG — allows any origin on an authenticated endpoint
app.add_middleware(CORSMiddleware, allow_origins=["*"])
```

Authenticated endpoints need explicit origins. `allow_origins=["*"]` is only appropriate for truly public, unauthenticated APIs.

---

## For AI agents specifically

When an agent generates code that:
- Takes user input and uses it in a database query → verify it's parameterised
- Reads or writes files using a user-supplied path → verify it's bounded
- Makes an outbound HTTP call with a URL from user input → verify it's to an allowlisted domain
- Returns data about a resource → verify the caller is authorised to see that resource

These are the four injection classes that appear repeatedly in AI-generated code. Check for all four on every PR that touches user input.

---

## What to do when you find a vulnerability

1. Don't fix it in the open PR — the vulnerability is now in git history
2. If it's in a PR that hasn't merged: add the fix and mark the finding in the PR description
3. If it's in production code: assess blast radius first, then patch, then disclose internally
4. Add the pattern to this standards file so the next agent (or engineer) doesn't repeat it

---

## When Layer 2 helps

These checks happen at PR review time. Conduct AI Security Loop scans every PR for these patterns automatically and posts findings as a PR review comment — with severity, file/line, and a suggested fix. Critical findings create a fix issue and trigger Autopilot.

`conductai.ai/security-loop`
