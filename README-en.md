# Xuanqiong Wenshu

Xuanqiong Wenshu is a local-first writing assistant for long-form fiction. It provides project blueprints, a chapter writing desk, multi-profile LLM configuration, writing skills, clue tracking, and knowledge graph features.

> This README has been cleaned up and aligned with the current repository. Old repository promotion content, QR codes, external screenshots, hosted demo links, and inherited repository references have been removed.

## Main features

- Project, blueprint, character, location, and faction management
- Writing desk: chapter generation, version comparison, patch diff, and memory management
- LLM settings: multi-profile config, health check, source trace, and auto-switch
- Writing skills: catalog, install / uninstall, and execution suggestions
- Auxiliary analysis: clue tracking, emotion curve, knowledge graph, and Token Budget

## Formal local startup

```powershell
./start.ps1
```

Default ports:

- Frontend: `http://127.0.0.1:5174`
- Backend: `http://127.0.0.1:8013`

Stop services:

```powershell
./stop.ps1
```

## Verification

```powershell
./verify.ps1 quick
./verify.ps1 smoke
./verify.ps1 full
```

Notes:

- `quick`: frontend build + critical backend pytest
- `smoke`: runtime checks on the formal local ports
- `full`: broader end-to-end regression

### Recent verification and diagnostics output improvements

The current verification toolchain has been tightened up in the following ways:

- `verify.ps1`, `tools/smoke_api_routes.py`, and `tools/smoke_llm_settings_health.py` now use clearer localized console messaging
- the smoke route checker no longer fabricates `00000000-0000-0000-0000-000000000000` style placeholder IDs to hit resource-dependent endpoints that are expected to 404
- routes that require real resource identities are now explicitly reported as skipped with a reason, instead of generating misleading noise
- `start.ps1`, `verify.ps1`, `tools/start_local_mysql.ps1`, and related verification scripts were adjusted to improve UTF-8 behavior on Windows PowerShell and reduce garbled Chinese output
- common standalone scripts such as `backend/scripts/diagnose_llm_connectivity.py`, `backend/scripts/backfill_relationship_meta_markers.py`, and `backend/scripts/migrate_sqlite_to_mysql.py` were also updated to use clearer localized output

The goal of these changes is to keep real failures visible, make skip reasons understandable, and prevent noisy verification output from hiding the real issue.

## Backend development

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8013 --reload
```

Recommended backend test command:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest app/services/test_phase4_integration.py
```

## Frontend development

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5174
```

## Docker deployment

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

## LLM configuration and diagnosis

Runtime priority:

1. User `llm_configs`
2. System `system_configs`
3. `.env / env fallback`

Common diagnostic command:

```bash
python backend/scripts/diagnose_llm_connectivity.py --user-id <user-id>
```

Read-only source trace endpoint:

- `GET /api/llm-config/source-trace`

Notes:

- Diagnostic endpoints only return masked key information
- Do not commit `.env`, databases, backups, logs, or test artifacts

## Code navigation

Start here:

- `docs/code-index/README.md`
- `docs/code-index/functional-zones.md`
- `docs/code-index/auto-file-index.md`
- `docs/code-index/auto-file-index.json`

Refresh the index:

```powershell
python tools/generate_code_index.py
```

## Current notes

### Backend validation environment

- Run backend commands from `backend/` so `backend/.env` loads correctly.
- Use the project virtualenv for backend tests: `backend/.venv/Scripts/python.exe`.
- Avoid global `pytest` or Anaconda Python for backend tests.

### Definition of done

A feature is not considered done unless at least these checks pass:

1. Backend import / startup works
2. `Base.metadata.create_all()` covers new ORM models
3. Frontend and backend routes are aligned
4. Smoke tests pass
5. Frontend build passes

### Common pitfalls

- After adding ORM models, also update `backend/app/models/__init__.py`.
- Project routes should use `/api/projects/{project_id}/...`.
- `clue_tracker` static routes must be defined before `/{clue_id}`.
- Dialog `@updated` callbacks in shell components must point to real methods in the current component.

### Verified commands

```powershell
./verify.ps1 quick
./start.ps1
./verify.ps1 smoke
./verify.ps1 full

# or run manually
npm --prefix frontend run build
cd backend
.\.venv\Scripts\python.exe -m pytest app/services/test_phase4_integration.py
cd ..
backend\.venv\Scripts\python.exe tools/smoke_api_routes.py
backend\.venv\Scripts\python.exe tools/smoke_llm_settings_health.py
```

### Recommended usage order

1. `./start.ps1`
2. `./verify.ps1 smoke`
3. If backend or critical flows changed, run `./verify.ps1 full`
4. Finish with `./stop.ps1`

## Key entry points

- Backend entry: `backend/app/main.py`
- Frontend entry: `frontend/src/main.ts`
- Writing pipeline: `backend/app/services/pipeline_orchestrator.py`
- LLM gateway: `backend/app/services/llm_service.py`
- Writing skills: `backend/app/services/writing_skills_service.py`
- Settings UI: `frontend/src/components/LLMSettings.vue`
- Writing desk UI: `frontend/src/components/writing-desk/`

## Repository

Current repository:

- `https://github.com/xingluoyuankong/xuanqiong-wenshu`

Exclude these from commits:

- `.env`
- database files
- backup files
- logs
- temporary outputs
- test artifacts

## License

MIT
