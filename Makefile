# ==========================================
# MENJALANKAN & MENGHENTIKAN LAYANAN
# ==========================================
up:
	docker compose up -d neo4j kb-api streamlit-ui

stop:
	docker compose stop

reset:
	docker compose down -v


# ==========================================
# LOADER & DATABASE 
# ==========================================
load-run:
	docker compose run --rm loader

load-build:
	docker compose build loader

load-build-nocache:
	docker compose build --no-cache loader

load-schema-loader:
	docker compose run --rm loader python -m scripts.run_schema

load-local-db:
	docker compose --profile local-db up -d neo4j

load-schema-api:
	docker compose run --rm kb-api python -m scripts.run_schema

load-ingest-api:
	docker compose run --rm kb-api python -m scripts.run_ingest

load-ingest-noseed:
	docker compose run --rm kb-api python -m scripts.run_ingest --no-seed

seed-docker:
	docker compose run --rm kb-api python -m scripts.generate_seed_qa


# ==========================================
# LOGS & MONITORING
# ==========================================
cek-log:
	docker compose logs kb-api -f

cek-log-tail:
	docker compose logs --tail 50 kb-api


# ==========================================
# BUILD & RECREATE CONTAINER
# ==========================================
builder-klasik:
	docker-compose up -d

recreate:
	docker compose up -d --force-recreate

remove-dlu:
	docker compose down --remove-orphans
	docker compose --profile local-db down --remove-orphans

streamlit-build:
	docker compose build streamlit-ui
	docker compose up -d

streamlit-restart:
	docker compose restart streamlit-ui


# ==========================================
# SKRIP PYTHON LOKAL & TESTING
# ==========================================
seed:
	python -m scripts.generate_seed_qa

schema:
	python -m scripts.run_schema

ingest:
	python -m scripts.run_ingest

test:
	python -m pytest -q tests

streamlit:
	streamlit run ui/app.py


# ==========================================
# TROUBLESHOOTING & MAINTENANCE
# ==========================================
hapus-plugin-korup:
	Remove-Item -Force "$$env:USERPROFILE\.docker\cli-plugins\docker-buildx.exe" -ErrorAction SilentlyContinue
```````````
fix-network:
	docker rm -f arcana-neo4j
	docker network prune -f

wsl-shutdown:
	wsl --shutdown

wsl-akses:
	wsl 
	cd ~/kb
	ls
	top


# ==========================================
# DATABASE (CYPHER QUERY)
# ==========================================
 "MATCH (n) DETACH DELETE n;" 