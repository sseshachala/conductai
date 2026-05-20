cd ~/projects/marshal

# 1. Rebuild api + worker + web because deps changed
docker compose build api worker web

# 2. Bring everything up
docker compose up -d

# 3. Apply the new 0004 migration
docker compose exec api alembic upgrade head

# 4. Seed the test workspace + dummy creds + 2 smoke workflows
docker compose exec api python seed_test_user.py

# 5. Run the 62 unit tests inside the container (the canonical env)
docker compose exec api pytest tests/ -v

# 6. Run the API smoke from the host
bash apps/api/tests/smoke_api.sh

# 7. Open the canvas in a browser
open http://localhost:3000/workflows/22222222-2222-2222-2222-222222222222
