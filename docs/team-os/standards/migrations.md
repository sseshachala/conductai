# Standard: Database Migrations

**When to use this:** Any change that adds, modifies, or removes tables, columns, indexes, or constraints.

AI tools are good at writing migrations. They are bad at reasoning about what happens to the 10 million rows already in the table when that migration runs.

---

## The rules

**One change per migration.**
Bundling unrelated schema changes into one migration makes rollback impossible and incident diagnosis harder. If you need to add a column and an index, those can be in one migration. If you're adding a column and renaming an unrelated table, those are two migrations.

**Test the migration locally before pushing.**
Run `alembic upgrade head` (or your equivalent) against a copy of production schema before opening the PR. The first time a migration should fail is not on the deploy.

**Define `downgrade()`.**
Even if you never plan to run it on production, define it. It's the proof that you've thought about the reverse. An undefined downgrade is a migration you can't recover from.

**Destructive changes are staged.**
Dropping a column or table follows a two-deploy process:
1. Deploy 1: stop writing to the column/table in application code
2. Deploy 2: drop the column/table in the migration

Running the drop before stopping the writes means production errors during Deploy 1 while you wait for rollout. The two-deploy pattern avoids this.

---

## The checklist

- [ ] Migration is a single focused change
- [ ] `alembic upgrade head` tested locally against a schema that matches production
- [ ] `downgrade()` is defined and reverses the change cleanly
- [ ] If adding a NOT NULL column to an existing table: a default is provided, or the column is added nullable first and the NOT NULL constraint added in a follow-up migration after backfill
- [ ] If dropping a column or table: application code has already stopped writing to it in a previous deploy

---

## The patterns AI tools get wrong

### NOT NULL without a default on an existing table

```python
# WRONG — fails on any table with existing rows
op.add_column('users', sa.Column('status', sa.String(), nullable=False))
```

Two safe options:

**Option A — provide a server default:**
```python
op.add_column('users', sa.Column(
    'status', sa.String(), nullable=False, server_default='active'
))
```

**Option B — nullable first, then constrain:**
```python
# Migration 1
op.add_column('users', sa.Column('status', sa.String(), nullable=True))
# Migration 2 (after backfill)
op.alter_column('users', 'status', nullable=False)
```

### Index creation blocking the table

```python
# WRONG — locks the table on large datasets
op.create_index('ix_users_email', 'users', ['email'])
```

Use `postgresql_concurrently=True` for large tables:
```python
# RIGHT — non-blocking
op.create_index('ix_users_email', 'users', ['email'], postgresql_concurrently=True)
# Note: requires autocommit — wrap in op.execute('COMMIT') if needed
```

### Skipping downgrade

```python
def downgrade() -> None:
    pass  # WRONG — this migration cannot be reversed
```

Even if you won't run it, define it:
```python
def downgrade() -> None:
    op.drop_column('users', 'status')
```

---

## Running migrations safely in production

```bash
# 1. Check what will run
alembic history --verbose

# 2. Dry run — show the SQL without executing
alembic upgrade head --sql

# 3. Apply
alembic upgrade head

# 4. Verify the schema matches models
{{ your schema sync check command }}
```

If step 2 shows anything unexpected — stop, review, do not proceed.

---

## When Layer 2 helps

Migrations are one of the highest-risk changes an AI agent can make. Conduct AI can be configured to require human approval for any task that touches migration files before the agent runs — so no migration reaches `alembic upgrade` without a pair of human eyes.

`conductai.ai` — approval gates for high-risk agent actions
