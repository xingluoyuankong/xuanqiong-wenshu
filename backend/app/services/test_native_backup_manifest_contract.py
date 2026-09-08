"""Native MySQL backup package contracts. Executes copied Bash, never live services.

The fixture clients record argv/env, synthesize SQL from actual dump flags, and
model the existing rollback consumer. This is not a real MySQL restore test.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "fixture password $pw # spaces ; 'quote'"
SCRIPTS = ("run_migrations.sh", "deploy_docker.sh", "rollback.sh")

# Launched by isolated Bash client shims with the current pytest Python runtime.
STUB = r'''
import hashlib, json, os, pathlib, sys
root = pathlib.Path(os.environ['FIXTURE_ROOT'])
tool, args = sys.argv[1], sys.argv[2:]
env = os.environ
entry = {'tool':tool, 'args':args, 'umask':env.get('FIXTURE_UMASK')}
if tool in ('mysql','mysqldump'):
    entry['password_matches'] = env.get('MYSQL_PWD') == env['EXPECTED_PASSWORD']
    if not entry['password_matches']:
        raise RuntimeError('client did not receive exact MYSQL_PWD')
with (root/'events.jsonl').open('a',encoding='utf-8') as out:
    out.write(json.dumps(entry)+'\n')
def package_ready():
    dumps = list((root/'backups').glob('*.sql'))
    assert len(dumps)==1, 'exactly one backup before schema write'
    file=dumps[0]
    assert pathlib.Path(str(file)+'.sha256').read_text().strip()==hashlib.sha256(file.read_bytes()).hexdigest(), 'manifest checksum before schema write'
    assert pathlib.Path(str(file)+'.database').read_text().strip()==env['MYSQL_DATABASE'], 'manifest database before schema write'
    assert pathlib.Path(str(file)+'.provider').read_text().strip()=='mysql', 'manifest provider before schema write'
def dump(db):
    print('-- fixture logical SQL')
    if '--add-drop-database' in args and '--databases' in args:
        print('DROP DATABASE IF EXISTS `'+db+'`;')
    if '--databases' in args:
        print('CREATE DATABASE `'+db+'`;\nUSE `'+db+'`;')
    print('CREATE TABLE sentinel (v TEXT);')
    print("INSERT INTO sentinel VALUES ('"+env.get('DUMP_VARIANT','first')+"');")
if tool=='mysqldump':
    mode=env.get('DUMP_MODE','ok')
    if mode=='partial':
        print('-- partial')
        sys.exit(74)
    if mode=='empty': sys.exit(0)
    dump(args[-1])
elif tool=='mysql':
    if '-e' in args:
        sys.exit(72 if env.get('MYSQL_FAIL')=='1' else 0)
    # Legacy SQL call. Test may require manifest to be ready at first schema write.
    sys.stdin.read()
    if env.get('REQUIRE_READY')=='1': package_ready()
    (root/'legacy-ran').touch()
elif tool=='python':
    if 'upgrade' in args:
        if env.get('REQUIRE_READY')=='1': package_ready()
        (root/'migration-ran').touch()
    sys.exit(78 if env.get('PYTHON_FAIL')=='1' else 0)
elif tool=='sha256sum':
    mode=env.get('HASH_MODE','ok')
    if mode=='fail': sys.exit(79)
    if mode=='partial-fail':
        print('a'*64+'  ignored'); sys.exit(79)
    if mode=='malformed': print('not-a-digest'); sys.exit(0)
    if mode=='empty': sys.exit(0)
    raw=args[-1]
    # Git Bash can expose Windows TEMP as /tmp rather than /c/... .
    # Resolve relative to the actual shell workspace, not guessed drive aliases.
    if raw.startswith('/'):
        relative=pathlib.PurePosixPath(raw).relative_to(pathlib.PurePosixPath(env['FIXTURE_POSIX_ROOT']))
        file=root.joinpath(*relative.parts)
    else:
        file=pathlib.Path(raw)
    print(hashlib.sha256(file.read_bytes()).hexdigest()+'  '+str(file))
elif tool=='docker':
    text=' '.join(args)
    if args==['compose','version']: phase='version'
    elif args==['info']: phase='info'
    elif args[:1]==['pull']: phase='pull'
    elif args[:2]==['image','inspect']: phase='image'
    elif args[-2:]==['config','--quiet']: phase='config'
    elif 'mysqldump' in text: phase='backup'
    elif '--execute=' in text: phase='db_probe'
    elif 'exec mysql ' in text: phase='restore'
    elif 'stop' in args: phase='stop'
    elif 'build' in args: phase='build'
    elif 'up' in args and args[-1]=='db': phase='db'
    elif 'up' in args: phase='start'
    else: raise RuntimeError('Unexpected Docker command: '+text)
    with (root/'phases.jsonl').open('a') as out: out.write(json.dumps({'phase':phase,'args':args})+'\n')
    if phase=='backup':
        if env.get('TAMPER_AFTER_CHECK')=='1':
            (root/env['ROLLBACK_BACKUP']).write_text('-- changed caller path')
        print('-- safety backup\nDROP DATABASE IF EXISTS `novel_test`;\nCREATE DATABASE `novel_test`;\nUSE `novel_test`;')
    if phase=='restore':
        payload=sys.stdin.buffer.read()
        (root/'restore-attempt.sql').write_bytes(payload)
        # Minimal model: a restore without a selected DB needs a self-contained SQL package.
        for part in (b'DROP DATABASE',b'CREATE DATABASE',b'USE `'):
            if part not in payload:
                print('fixture: SQL lacks database restore context',file=sys.stderr)
                sys.exit(81)
        (root/'restored.sql').write_bytes(payload)
'''


def _bash():
    git = shutil.which("git")
    if git:
        candidate = Path(git).resolve().parent.parent / "bin/bash.exe"
        if candidate.is_file():
            return str(candidate)
    if os.name != "nt" and shutil.which("bash"):
        return shutil.which("bash")
    pytest.fail("Git Bash (Windows) or Bash (POSIX) required")


def _write(path, text):
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def _env_file(path, values):
    _write(path, "".join(key + "='" + value.replace("'", "'\"'\"'") + "'\n" for key, value in values.items()))


def _workspace(path):
    path.mkdir(parents=True, exist_ok=True)
    for folder in ("bin", "deploy/scripts", "backend/db/migrations"):
        (path / folder).mkdir(parents=True)
    for name in SCRIPTS:
        _write(path / "deploy/scripts" / name, (ROOT / "deploy/scripts" / name).read_text(encoding="utf-8"))
    _write(path / "backend/alembic.ini", "[alembic]\n")
    _write(path / "deploy/docker-compose.yml", "services: {}\n")
    for name in ("add_novel_kit_features.sql", "add_deep_optimization_features.sql"):
        _write(path / "backend/db/migrations" / name, "-- fixture legacy SQL\n")
    _write(path / "stub.py", STUB)
    for tool in ("mysql", "mysqldump", "python", "sha256sum", "docker"):
        _write(path / "bin" / tool, '#!/usr/bin/env bash\nset -eu\nexport FIXTURE_UMASK="$(umask)"\n'
               f'exec "$FIXTURE_PYTHON" "$FIXTURE_ROOT/stub.py" {tool} "$@"\n')
    # Preserve real mktemp behavior; inject a sidecar filesystem error after allocation.
    _write(path / "bin/mktemp", '#!/usr/bin/env bash\nset -eu\n'
           'file=$(/usr/bin/mktemp "$@")\n'
           'if [[ -n "${FAIL_SIDECAR:-}" ]]; then mkdir -- "$file$FAIL_SIDECAR"; fi\n'
           'printf "%s\\n" "$file"\n')
    _write(path / "bin/date", '#!/usr/bin/env bash\nprintf "%s\\n" "20260907_180825"\n')
    return path


def _values(**overrides):
    return {"MYSQL_HOST": "external-db.invalid", "MYSQL_PORT": "3306", "MYSQL_USER": "fixture_user",
            "MYSQL_PASSWORD": PASSWORD, "MYSQL_DATABASE": "novel_test", **overrides}


def _process_env(path, overrides):
    keep = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE", "USERPROFILE", "HOME"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env.update(FIXTURE_ROOT=str(path), FIXTURE_PYTHON=sys.executable, EXPECTED_PASSWORD=PASSWORD,
               PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", MSYS_NO_PATHCONV="1",
               DOCKER_HOST="tcp://127.0.0.1:1", TEMP=str(path), TMP=str(path), TMPDIR=str(path))
    env.update(overrides)
    return env


def _run(path, script="run_migrations.sh", args=(), **overrides):
    # PATH is set inside Bash so Windows/MSYS path-list translation is not assumed.
    preamble = ('umask 0022; export FIXTURE_POSIX_ROOT="$PWD"; export PATH="$PWD/bin:$PATH"; hash -r; '
                'for tool in docker mysql mysqldump python sha256sum mktemp; do '
                '[[ "$(command -v "$tool")" == "$PWD/bin/$tool" ]] || exit 99; done; ')
    result = subprocess.run([_bash(), "--noprofile", "--norc", "-c",
                             preamble + 'exec bash "deploy/scripts/$1" "${@:2}"', "--", script, *args],
                            cwd=path, env=_process_env(path, overrides), capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=30)
    if folder := os.environ.get("NATIVE_MANIFEST_EVIDENCE"):
        evidence = Path(folder)
        evidence.mkdir(parents=True, exist_ok=True)
        index = len(list(evidence.glob("call-*.json"))) + 1
        data = {"test": os.environ.get("PYTEST_CURRENT_TEST", ""), "workspace": str(path), "script": script,
                "args": list(args), "exit_code": result.returncode, "stdout": result.stdout,
                "stderr": result.stderr, "events": _events(path), "phases": _phases(path)}
        (evidence / f"call-{index:04}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _native(path, args=(), values=None, **overrides):
    _env_file(path / "backend/.env", _values() if values is None else values)
    return _run(path, args=args, PYTHON_BIN="python", **overrides)


def _events(path):
    file = path / "events.jsonl"
    return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines()] if file.exists() else []


def _phases(path):
    file = path / "phases.jsonl"
    return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []


def _backups(path):
    return sorted((path / "backups").glob("*.sql"))


def _assert_package(file, database="novel_test"):
    assert file.is_file() and file.stat().st_size > 0
    expected = {".sha256": hashlib.sha256(file.read_bytes()).hexdigest(), ".database": database, ".provider": "mysql"}
    for suffix, value in expected.items():
        sidecar = Path(str(file) + suffix)
        assert sidecar.is_file(), f"missing manifest {suffix}"
        assert sidecar.read_text().strip() == value, f"incorrect {suffix}"
    for part in (b"DROP DATABASE", b"CREATE DATABASE", b"USE `"):
        assert part in file.read_bytes(), "SQL needs database context, not just sidecars"


def _assert_success(path, result, database="novel_test"):
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(_backups(path)) == 1
    file = _backups(path)[0]
    _assert_package(file, database)
    return file


def _rollback(path, file, provider="mysql", host="external-db.invalid", **overrides):
    values = _values(MYSQL_HOST=host)
    values.update(DB_PROVIDER=provider, SECRET_KEY="fixture-secret", ADMIN_DEFAULT_PASSWORD="fixture-admin")
    if host == "db":
        values["MYSQL_ROOT_PASSWORD"] = "fixture-root"
    _env_file(path / "deploy/.env", values)
    return _run(path, script="rollback.sh", CONFIRM_ROLLBACK="RESTORE_DATABASE",
                ROLLBACK_BACKUP=file.relative_to(path).as_posix(),
                ROLLBACK_IMAGE="example/novel@sha256:" + "a" * 64, BACKUP_DIR="rollback-backups", **overrides)


def _assert_no_schema_writes(path):
    assert not (path / "migration-ran").exists()
    assert not (path / "legacy-ran").exists()


def _assert_private(path, files):
    dumps = [e for e in _events(path) if e["tool"] == "mysqldump"]
    assert dumps and all(int(e["umask"], 8) == 0o077 for e in dumps), "producer must set private umask"
    # NTFS chmod reports emulated bits, not POSIX confidentiality. Exercise the
    # actual umask on Windows and additionally verify real mode bits on POSIX.
    if os.name != "nt":
        assert all(file.stat().st_mode & 0o077 == 0 for file in files)


def test_r01_native_produces_complete_package(tmp_path):
    path = _workspace(tmp_path)
    _assert_success(path, _native(path))


def test_r02_dump_options_and_database_context(tmp_path):
    path = _workspace(tmp_path)
    result = _native(path)
    assert result.returncode == 0, result.stderr
    args = next(e["args"] for e in _events(path) if e["tool"] == "mysqldump")
    assert {"--single-transaction", "--routines", "--events", "--triggers", "--hex-blob", "--databases", "--add-drop-database"} <= set(args)
    assert args[-1] == "novel_test"
    assert b"USE `novel_test`" in _backups(path)[0].read_bytes()


@pytest.mark.parametrize("host", ["db", "external-db.invalid"])
def test_r03_producer_to_unchanged_rollback(tmp_path, host):
    path = _workspace(tmp_path)
    file = _assert_success(path, _native(path))
    original = file.read_bytes()
    result = _rollback(path, file, host=host)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (path / "restored.sql").read_bytes() == original
    phases = [e["phase"] for e in _phases(path)]
    assert phases == ["version", "info", "config", "pull", "image", "config", "build",
                      "db" if host == "db" else "db_probe", "stop", "backup", "restore", "start"]
    for name in ("rollback.sh", "deploy_docker.sh"):
        assert (path / "deploy/scripts" / name).read_text() == (ROOT / "deploy/scripts" / name).read_text()


def test_r04_sidecars_alone_do_not_make_database_restore_format(tmp_path):
    path = _workspace(tmp_path)
    text = (path / "deploy/scripts/run_migrations.sh").read_text()
    for flag in ("--add-drop-database", "--databases"):
        text = text.replace(flag, "")
    _write(path / "deploy/scripts/run_migrations.sh", text)
    result = _native(path)
    assert result.returncode == 0, result.stderr
    file = _backups(path)[0]
    # Artificial sidecars only demonstrate why metadata alone is insufficient.
    for suffix, value in {".sha256": hashlib.sha256(file.read_bytes()).hexdigest(), ".database": "novel_test", ".provider": "mysql"}.items():
        _write(Path(str(file) + suffix), value + "\n")
    with pytest.raises(AssertionError, match="database context"):
        _assert_package(file)
    result = _rollback(path, file)
    assert result.returncode == 81 and not (path / "restored.sql").exists()
    phases = [e["phase"] for e in _phases(path)]
    assert phases[-2:] == ["restore", "stop"] and "start" not in phases


@pytest.mark.parametrize("mode", ["partial", "empty"])
def test_r05_failed_or_empty_dump_blocks_manifest_and_migration(tmp_path, mode):
    path = _workspace(tmp_path)
    result = _native(path, DUMP_MODE=mode)
    assert result.returncode != 0
    _assert_no_schema_writes(path)
    assert not list((path / "backups").glob("*.provider"))
    assert "Backup complete." not in result.stdout


@pytest.mark.parametrize("mode", ["fail", "partial-fail", "malformed", "empty"])
def test_r06_hash_failure_blocks_manifest_and_migration(tmp_path, mode):
    path = _workspace(tmp_path)
    result = _native(path, HASH_MODE=mode)
    assert result.returncode != 0
    _assert_no_schema_writes(path)
    assert not list((path / "backups").glob("*.provider"))
    assert "Backup complete." not in result.stdout


@pytest.mark.parametrize("suffix", [".sha256", ".database", ".provider"])
def test_r06_sidecar_filesystem_error_blocks_migration(tmp_path, suffix):
    path = _workspace(tmp_path)
    result = _native(path, FAIL_SIDECAR=suffix)
    assert result.returncode != 0
    _assert_no_schema_writes(path)
    assert any(Path(str(file) + suffix).is_dir() for file in _backups(path)), "failure injection must actually run"
    assert not any(Path(str(file) + ".provider").is_file() for file in _backups(path))
    assert "Backup complete." not in result.stdout


def test_r07_same_second_keeps_both_private_packages(tmp_path):
    path = _workspace(tmp_path)
    first = _native(path)
    assert first.returncode == 0, first.stderr
    file = _backups(path)[0]
    original = file.read_bytes()
    second = _native(path, DUMP_VARIANT="second")
    assert second.returncode == 0, second.stderr
    files = _backups(path)
    assert len(files) == 2, "same-second backup overwrote existing artifact"
    assert file.read_bytes() == original
    assert len({f.read_bytes() for f in files}) == 2
    for file in files:
        _assert_package(file)
    _assert_private(path, list((path / "backups").iterdir()))


def test_r07_private_umask_before_dump(tmp_path):
    path = _workspace(tmp_path)
    _native(path)
    _assert_private(path, list((path / "backups").iterdir()))


@pytest.mark.parametrize("database", ["", "mysql", "MYSQL", "sys", "information_schema", "performance_schema", "bad-name", "../escape", "with space", "9novel", "a\nother", "x" * 65])
def test_r08_invalid_database_identity_fails_before_clients(tmp_path, database):
    path = _workspace(tmp_path)
    result = _native(path, values=_values(MYSQL_DATABASE=database))
    assert result.returncode != 0
    assert _events(path) == [], "identity validation must precede clients"
    assert not (path / "backups").exists()


@pytest.mark.parametrize("database", ["Novel_2026", "x", "x" * 64, None])
def test_r08_valid_and_unset_database_identity(tmp_path, database):
    path = _workspace(tmp_path)
    values = _values()
    if database is None:
        values.pop("MYSQL_DATABASE")
    else:
        values["MYSQL_DATABASE"] = database
    expected = database or "xuanqiong_wenshu"
    # Fixture dumper needs the effective default too; the real client receives it in argv.
    result = _native(path, values=values)
    _assert_success(path, result, expected)


def test_r09_dry_run_calls_reads_only(tmp_path):
    path = _workspace(tmp_path)
    result = _native(path, args=("--dry-run",))
    assert result.returncode == 0, result.stderr
    events = _events(path)
    assert [e["tool"] for e in events] == ["mysql", "mysql", "python", "python"]
    assert [e["args"][-1] for e in events[-2:]] == ["current", "heads"]
    assert not (path / "backups").exists()
    _assert_no_schema_writes(path)


@pytest.mark.parametrize("suffix", [".sha256", ".database", ".provider"])
@pytest.mark.parametrize("damage", ["missing", "empty", "wrong"])
def test_r10_consumer_rejects_each_sidecar_damage(tmp_path, suffix, damage):
    path = _workspace(tmp_path)
    file = _assert_success(path, _native(path))
    sidecar = Path(str(file) + suffix)
    if damage == "missing":
        sidecar.unlink()
    else:
        _write(sidecar, "" if damage == "empty" else "wrong\n")
    result = _rollback(path, file)
    assert result.returncode != 0
    assert [e["phase"] for e in _phases(path)] == ["version", "info", "config"]
    assert not (path / "restored.sql").exists()


@pytest.mark.parametrize("damage", ["body", "hash-with-filename", "uppercase-hash"])
def test_r10_corrupt_body_or_digest_format(tmp_path, damage):
    path = _workspace(tmp_path)
    file = _assert_success(path, _native(path))
    sidecar = Path(str(file) + ".sha256")
    if damage == "body":
        file.write_bytes(b"tampered")
    else:
        text = sidecar.read_text().strip()
        _write(sidecar, text.upper() if damage == "uppercase-hash" else text + "  backup.sql")
    result = _rollback(path, file)
    assert result.returncode != 0
    assert [e["phase"] for e in _phases(path)] == ["version", "info", "config"]


def test_r11_verified_snapshot_survives_caller_mutation(tmp_path):
    path = _workspace(tmp_path)
    file = _assert_success(path, _native(path))
    original = file.read_bytes()
    result = _rollback(path, file, TAMPER_AFTER_CHECK="1")
    assert result.returncode == 0, result.stderr
    assert file.read_bytes() != original
    assert (path / "restored.sql").read_bytes() == original


def test_r12_external_mysql_has_no_internal_db_profile(tmp_path):
    path = _workspace(tmp_path)
    file = _assert_success(path, _native(path))
    result = _rollback(path, file)
    assert result.returncode == 0, result.stderr
    phases = _phases(path)
    assert "db" not in [e["phase"] for e in phases]
    assert all("--profile mysql" not in " ".join(e["args"]) for e in phases)


def test_r13_mysql_package_rejected_by_sqlite_consumer(tmp_path):
    path = _workspace(tmp_path)
    file = _assert_success(path, _native(path))
    _write(Path(str(file) + ".database"), "/app/storage/xuanqiong_wenshu.db\n")
    result = _rollback(path, file, provider="sqlite")
    assert result.returncode != 0 and "provider identity mismatch" in result.stderr
    assert [e["phase"] for e in _phases(path)] == ["version", "info", "config"]


def test_r14_client_passwords_only_in_environment(tmp_path):
    path = _workspace(tmp_path)
    result = _native(path)
    assert result.returncode == 0, result.stderr
    events = _events(path)
    clients = [e for e in events if e["tool"] in ("mysql", "mysqldump")]
    assert clients and all(e["password_matches"] for e in clients)
    assert PASSWORD not in result.stdout + result.stderr + json.dumps(events)
    assert all(not arg.startswith(("-p", "--password")) for e in clients for arg in e["args"])


@pytest.mark.parametrize("legacy", ["true", "false"])
def test_r15_manifest_valid_at_first_schema_write(tmp_path, legacy):
    path = _workspace(tmp_path)
    result = _native(path, REQUIRE_READY="1", APPLY_LEGACY_SQL=legacy)
    _assert_success(path, result)
    assert (path / "migration-ran").exists()
    assert (path / "legacy-ran").exists() == (legacy == "true")


@pytest.mark.parametrize("mutation", ["remove-hash", "remove-database", "remove-provider", "remove-databases", "remove-drop", "late-manifest", "swallow-hash", "nonprivate", "timestamp-name", "mutable-restore"])
def test_isolated_mutations_are_detected(tmp_path, mutation):
    path = _workspace(tmp_path)
    target = path / "deploy/scripts/run_migrations.sh"
    text = target.read_text()
    original = text
    env = {}
    if mutation.startswith("remove-") and mutation.split("-", 1)[1] in ("hash", "database", "provider"):
        suffix = {"hash": ".sha256", "database": ".database", "provider": ".provider"}[mutation.split("-", 1)[1]]
        text = "\n".join(line for line in text.splitlines() if not (line.strip().startswith("printf ") and f'$BACKUP_FILE{suffix}' in line)) + "\n"
    elif mutation == "remove-databases":
        text = text.replace('--databases ', '')
    elif mutation == "remove-drop":
        text = text.replace('--add-drop-database ', '')
    elif mutation == "late-manifest":
        start = text.index('BACKUP_HASH=')
        end = text.index('echo "Backup complete."')
        block = text[start:end]
        text = text[:start] + text[end:] + "\n" + block
        env['REQUIRE_READY'] = '1'
    elif mutation == "swallow-hash":
        text = text.replace('BACKUP_HASH="$(sha256sum "$BACKUP_FILE" | awk \'{print $1}\')"', 'BACKUP_HASH="$(sha256sum "$BACKUP_FILE" | awk \'{print $1}\')" || true')
        env['HASH_MODE'] = 'partial-fail'
    elif mutation == "nonprivate":
        text = text.replace('umask 077', 'umask 022')
    elif mutation == "timestamp-name":
        text = text.replace('BACKUP_FILE="$(mktemp "$BACKUP_DIR/${DB_NAME}_before_alembic_XXXXXXXX.sql")"', 'BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_before_alembic_$(date +%Y%m%d_%H%M%S).sql"')
    elif mutation == "mutable-restore":
        file = _assert_success(path, _native(path))
        original_bytes = file.read_bytes()
        target = path / "deploy/scripts/rollback.sh"
        original = target.read_text()
        text = original.replace("' < \"$RESTORE_SNAPSHOT\"", "' < \"$ROLLBACK_BACKUP\"")
        assert text != original
        _write(target, text)
        result = _rollback(path, file, TAMPER_AFTER_CHECK="1")
        with pytest.raises(AssertionError):
            assert result.returncode == 0 and (path / "restored.sql").read_bytes() == original_bytes
        return
    assert text != original, f"mutation did not modify actual implementation: {mutation}"
    _write(target, text)
    result = _native(path, **env)
    with pytest.raises(AssertionError):
        if mutation == "swallow-hash":
            assert result.returncode != 0 and not (path / "migration-ran").exists()
        elif mutation == "nonprivate":
            _assert_private(path, list((path / "backups").iterdir()))
        elif mutation == "timestamp-name":
            assert result.returncode == 0
            first = _backups(path)[0].read_bytes()
            second = _native(path, DUMP_VARIANT="second")
            assert second.returncode == 0 and len(_backups(path)) == 2 and any(f.read_bytes() == first for f in _backups(path))
        else:
            _assert_success(path, result)


@pytest.mark.parametrize("posix_root", ["/tmp/pytest alias/中文", "/d/workspace/中文", "/c/Users/example/AppData/Local/Temp/test"])
def test_hash_fixture_resolves_recorded_posix_workspace_alias(tmp_path, posix_root):
    """Bash /tmp and drive aliases must resolve to the same actual fixture bytes."""
    _workspace(tmp_path)
    backup = tmp_path / "backups" / "payload.sql"
    backup.parent.mkdir()
    backup.write_bytes(b"fixture-blob-\x00\xff")
    env = _process_env(tmp_path, {"FIXTURE_POSIX_ROOT": posix_root})
    result = subprocess.run([sys.executable, str(tmp_path / "stub.py"), "sha256sum",
                             posix_root + "/backups/payload.sql"],
                            cwd=tmp_path, env=env, capture_output=True, text=True,
                            encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split()[0] == hashlib.sha256(backup.read_bytes()).hexdigest()
