"""F04/F07 contracts: real Compose parsing and isolated shell execution only.

No Docker daemon is contacted: the only real Docker subcommand is compose config.
Shell probes shadow Docker/MySQL entrypoints; all writable state lives in tmp_path.
Optional STAGE13_DEPLOY_EVIDENCE captures fixture-only subprocess evidence.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
DEPLOY = ROOT / "deploy"
APP_SERVICES = {"app", "agent-worker", "agent-command-worker"}
CREDENTIALS = {
    "SECRET_KEY": "stage13-fixture-secret-not-for-deployment",
    "ADMIN_DEFAULT_PASSWORD": "stage13-fixture-admin",
}
MYSQL_CREDENTIALS = {
    "MYSQL_PASSWORD": "fixture app $pw # with spaces; not-a-command",
    "MYSQL_ROOT_PASSWORD": "fixture root $pw # with spaces; not-a-command",
}
CASES = [
    ("sqlite-default", "sqlite", "db", (), APP_SERVICES),
    ("sqlite-maintenance", "sqlite", "db", ("maintenance",), APP_SERVICES | {"migrate"}),
    ("profile-only-mysql", "sqlite", "db", ("mysql",), APP_SERVICES | {"db"}),
    ("internal-mysql", "mysql", "db", ("maintenance", "mysql"), APP_SERVICES | {"migrate", "db"}),
    ("external-mysql", "mysql", "external-db.invalid", ("maintenance",), APP_SERVICES | {"migrate"}),
]


def _record(name: str, data: dict) -> None:
    if folder := os.environ.get("STAGE13_DEPLOY_EVIDENCE"):
        path = Path(folder)
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _environment() -> dict[str, str]:
    env = os.environ.copy()
    text = (DEPLOY / "docker-compose.yml").read_text(encoding="utf-8")
    names = set(re.findall(r"\$\{([A-Z_][A-Z_0-9]*)", text))
    names.update(re.findall(r"^([A-Z_][A-Z_0-9]*)=", (DEPLOY / ".env.example").read_text(encoding="utf-8"), re.M))
    names.update({"DATABASE_URL", "BACKUP_DIR", "HEALTH_TIMEOUT", "RUN_MIGRATIONS", "BASH_ENV", "ENV"})
    for key in list(env):
        if key in names or key.startswith(("MYSQL_", "COMPOSE_", "DOCKER_", "BASH_FUNC_")):
            env.pop(key, None)
    env.update(DOCKER_HOST="tcp://127.0.0.1:1", COMPOSE_DISABLE_ENV_FILE="1", MSYS_NO_PATHCONV="1")
    return env


def _bash() -> str:
    if git := shutil.which("git"):
        candidate = Path(git).resolve().parent.parent / "bin/bash.exe"
        if candidate.is_file():
            return str(candidate)
    if os.name != "nt" and (bash := shutil.which("bash")):
        return bash
    pytest.fail("Git Bash (Windows) or Bash (POSIX) is required for entry contracts")


def _run(args: list[str], cwd: Path, env: dict[str, str], name: str) -> subprocess.CompletedProcess:
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30)
    _record(name, {"argv": args, "cwd": str(cwd), "exit_code": result.returncode,
                   "stdout": result.stdout, "stderr": result.stderr})
    return result


def _compose(workspace: Path, profiles=(), values=None, source: str | None = None, name="compose", env_text=""):
    workspace.mkdir(parents=True, exist_ok=True)
    file = workspace / "docker-compose.yml"
    file.write_text(source if source is not None else (DEPLOY / file.name).read_text(encoding="utf-8"), encoding="utf-8")
    # Explicit empty env file prevents loading the operator's real deploy/.env.
    env_file = workspace / ".env"
    env_file.write_text(env_text, encoding="utf-8")
    docker = shutil.which("docker")
    assert docker, "Docker Compose CLI is required; no daemon is needed"
    args = [docker, "compose", "--project-name", "stage13-entry-contract", "--env-file", str(env_file), "-f", str(file)]
    for profile in profiles:
        args += ["--profile", profile]
    args += ["config", "--format", "json"]
    env = _environment()
    if not env_text:
        env.update(CREDENTIALS)
    env.update(values or {})
    return _run(args, workspace, env, name)


def _model(result):
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def mysql_model(tmp_path_factory):
    return _model(_compose(tmp_path_factory.mktemp("mysql-config"), ("mysql", "maintenance"),
                           {"DB_PROVIDER": "mysql", **MYSQL_CREDENTIALS}, name="valid-mysql-model"))


def _assert_entry_document(text: str) -> None:
    assert not re.search(r"docker compose[^\n]*\bup\b", text), "direct compose up bypasses release orchestration"
    assert "cp deploy/.env.example deploy/.env" in text, "copy must be relative to repository root"
    assert text.count("bash deploy/scripts/deploy_docker.sh") >= 3, "all three documented paths must use release entry"
    assert "DB_PROVIDER=mysql" in text and "MYSQL_HOST=db" in text
    assert "MYSQL_HOST=host.docker.internal" in text
    assert "MYSQL_ROOT_PASSWORD" in text


def test_example_routes_all_deployments_through_release_entry():
    _assert_entry_document((DEPLOY / ".env.example").read_text(encoding="utf-8"))


def _source_example(tmp_path: Path, text: str, name="source-example"):
    file = tmp_path / "example.env"
    file.write_text(text, encoding="utf-8", newline="\n")
    return _run([_bash(), "--noprofile", "--norc", "-c",
                 'set -euo pipefail; set -a; source ./example.env; set +a; '
                 'printf "SOURCE_OK\\n%s\\n%s\\n" "$SECRET_KEY" "$DB_PROVIDER"'],
                tmp_path, _environment(), name)


def test_example_is_sourceable_with_strict_shell(tmp_path):
    result = _source_example(tmp_path, (DEPLOY / ".env.example").read_text(encoding="utf-8"))
    assert result.returncode == 0, result.stderr
    assert "SOURCE_OK" in result.stdout and "sqlite" in result.stdout


@pytest.mark.parametrize("provider,host,profiles", [
    ("sqlite", "db", ("maintenance",)),
    ("mysql", "db", ("maintenance", "mysql")),
    ("mysql", "external-db.invalid", ("maintenance",)),
], ids=["sqlite", "internal-mysql", "external-mysql"])
def test_example_values_agree_between_bash_and_compose(tmp_path, provider, host, profiles):
    text = (DEPLOY / ".env.example").read_text(encoding="utf-8")
    text = re.sub(r"^DB_PROVIDER=.*$", f"DB_PROVIDER={provider}", text, flags=re.M)
    text = re.sub(r"^MYSQL_HOST=.*$", f"MYSQL_HOST={host}", text, flags=re.M)
    passwords = MYSQL_CREDENTIALS if host == "db" else {"MYSQL_PASSWORD": MYSQL_CREDENTIALS["MYSQL_PASSWORD"]}
    if provider == "mysql":
        for key, value in passwords.items():
            text = re.sub(rf"^{key}=.*$", f"{key}='{value}'", text, flags=re.M)
    result = _source_example(tmp_path, text, name=f"example-source-{provider}-{host}")
    assert result.returncode == 0, result.stderr
    model = _model(_compose(tmp_path / "compose", profiles, name=f"example-config-{provider}-{host}", env_text=text))
    app = model["services"]["app"]["environment"]
    assert _container_shell(app["SECRET_KEY"]) == result.stdout.splitlines()[1]
    assert app["DB_PROVIDER"] == result.stdout.splitlines()[2] == provider
    assert app["MYSQL_HOST"] == host
    assert _container_shell(app["MYSQL_PASSWORD"]) == (MYSQL_CREDENTIALS["MYSQL_PASSWORD"] if provider == "mysql" else "")
    assert ("db" in model["services"]) == (provider == "mysql" and host == "db")


def _assert_no_defaults(text: str):
    db = text.split("\n  db:\n", 1)[1]
    for name in MYSQL_CREDENTIALS:
        assert f"{name}: ${{{name}:-}}" in db, f"{name} must have no baked-in password or global required interpolation"


def test_mysql_has_no_baked_in_passwords_or_global_required_interpolation():
    _assert_no_defaults((DEPLOY / "docker-compose.yml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,provider,host,profiles,expected", CASES, ids=[case[0] for case in CASES])
def test_five_compose_configs(tmp_path, name, provider, host, profiles, expected):
    values = {"DB_PROVIDER": provider, "MYSQL_HOST": host}
    # SQLite cases intentionally omit both passwords unless mysql profile is active.
    if "mysql" in profiles:
        values.update(MYSQL_CREDENTIALS)
    elif provider == "mysql":
        values["MYSQL_PASSWORD"] = MYSQL_CREDENTIALS["MYSQL_PASSWORD"]
    model = _model(_compose(tmp_path, profiles, values, name=f"matrix-{name}"))
    assert set(model["services"]) == expected
    for service in expected - {"db"}:
        env = model["services"][service]["environment"]
        assert env["DB_PROVIDER"] == provider
        assert env["MYSQL_HOST"] == host
        assert _container_shell(env["MYSQL_PASSWORD"]) == values.get("MYSQL_PASSWORD", "")
    if "db" in expected:
        assert _container_shell(model["services"]["db"]["environment"]["MYSQL_PASSWORD"]) == values["MYSQL_PASSWORD"]
        assert _container_shell(model["services"]["db"]["environment"]["MYSQL_ROOT_PASSWORD"]) == values["MYSQL_ROOT_PASSWORD"]
    _record(f"matrix-summary-{name}", {"provider": provider, "profiles": profiles, "services": sorted(expected), "runtime_tested": False})


def _stub(workspace: Path, name: str, body: str):
    folder = workspace / "bin"
    folder.mkdir(exist_ok=True)
    file = folder / name
    file.write_text("#!/usr/bin/env bash\nset -eu\n" + body, encoding="utf-8", newline="\n")
    file.chmod(0o755)


def _shell(workspace: Path, program: str, values: dict, args=(), name="shell"):
    env = _environment()
    env.update(values)
    preamble = 'export PATH="$PWD/bin:$PATH"; hash -r; '
    return _run([_bash(), "--noprofile", "--norc", "-c", preamble + program, "--", *args], workspace, env, name)


def _container_shell(text: str) -> str:
    # Compose config serializes escaped dollars; the container receives one dollar.
    return text.replace("$$", "$")


def _health(workspace: Path, db: dict, values: dict, name="health", client_exit=0):
    test = db["healthcheck"]["test"]
    assert test[0] == "CMD-SHELL", "healthcheck must read credentials in the container shell"
    assert len(test) == 2
    _stub(workspace, "mysql", 'printf "%s\\n" "$@" > mysql.args\nprintf "%s" "${MYSQL_PWD-}" > mysql.pwd\nexit ' + str(client_exit) + '\n')
    return _shell(workspace, _container_shell(test[1]), values, name=name)


def _assert_health_uses_environment(db):
    test = db["healthcheck"]["test"]
    assert test[0] == "CMD-SHELL", "CLI password interpolation is not a container-env healthcheck"
    command = _container_shell(test[1])
    assert "MYSQL_PWD=" in command and "${MYSQL_ROOT_PASSWORD" in command
    assert "SELECT 1" in command and "mysqladmin" not in command, "ping alone does not prove authentication"
    assert not re.search(r"(?:^|\s)(?:-p|--password)(?:\S|\s|$)", command)
    assert not any(password in command for password in MYSQL_CREDENTIALS.values())


def test_healthcheck_resolves_container_env_without_password_argv(tmp_path, mysql_model):
    db = mysql_model["services"]["db"]
    _assert_health_uses_environment(db)
    # Deliberately differs from Compose parsing env, including shell metacharacters.
    password = "container-only $secret # ' quote ; spaced"
    result = _health(tmp_path, db, {"MYSQL_ROOT_PASSWORD": password})
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "mysql.pwd").read_text(encoding="utf-8") == password
    args = (tmp_path / "mysql.args").read_text(encoding="utf-8").splitlines()
    assert "--execute=SELECT 1" in args and "--user=root" in args
    assert not any(arg.startswith(("-p", "--password")) for arg in args)
    assert password not in result.stdout + result.stderr + "\n".join(args)


@pytest.mark.parametrize("missing", [True, False], ids=["missing", "empty"])
def test_healthcheck_root_credential_fail_closed(tmp_path, mysql_model, missing):
    result = _health(tmp_path, mysql_model["services"]["db"], {} if missing else {"MYSQL_ROOT_PASSWORD": ""}, name=f"health-root-{missing}")
    assert result.returncode != 0
    assert not (tmp_path / "mysql.args").exists(), "client must not run with empty credentials"


def test_healthcheck_propagates_authentication_failure(tmp_path, mysql_model):
    result = _health(tmp_path, mysql_model["services"]["db"], MYSQL_CREDENTIALS, name="health-auth-failure", client_exit=23)
    assert result.returncode == 23


def _entrypoint(workspace: Path, db: dict, values: dict, name="entrypoint"):
    entry = db.get("entrypoint")
    assert entry and entry[:3] == ["/bin/sh", "-eu", "-c"], "MySQL must validate credentials before image startup"
    assert entry[4:] == ["--"], "shell positional arguments must preserve original server options"
    program = _container_shell(entry[3])
    target = "/usr/local/bin/docker-entrypoint.sh"
    assert target in program
    _stub(workspace, "docker-entrypoint.sh", 'printf "%s\\n" "$@" > entrypoint.args\n')
    # Only redirect the image executable; execute actual guards and argument forwarding.
    program = program.replace(target, '"$PWD/bin/docker-entrypoint.sh"')
    return _shell(workspace, "set -eu; " + program, values, db["command"], name=name)


def test_mysql_entrypoint_preserves_image_command(tmp_path, mysql_model):
    db = mysql_model["services"]["db"]
    result = _entrypoint(tmp_path, db, MYSQL_CREDENTIALS)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "entrypoint.args").read_text().splitlines() == ["mysqld", *db["command"]]


@pytest.mark.parametrize("credential", MYSQL_CREDENTIALS)
@pytest.mark.parametrize("missing", [True, False], ids=["missing", "empty"])
def test_mysql_entrypoint_credential_fail_closed(tmp_path, mysql_model, credential, missing):
    values = dict(MYSQL_CREDENTIALS)
    values.pop(credential)
    if not missing:
        values[credential] = ""
    result = _entrypoint(tmp_path, mysql_model["services"]["db"], values, name=f"entry-{credential}-{missing}")
    assert result.returncode != 0
    assert credential in result.stderr
    assert not (tmp_path / "entrypoint.args").exists(), "official entrypoint must not be reached"


@pytest.mark.parametrize("credential", MYSQL_CREDENTIALS)
@pytest.mark.parametrize("missing", [True, False], ids=["missing", "empty"])
def test_mysql_config_empty_credentials_defer_to_runtime_guard(tmp_path, credential, missing):
    values = {"DB_PROVIDER": "mysql", **MYSQL_CREDENTIALS}
    values.pop(credential)
    if not missing:
        values[credential] = ""
    db = _model(_compose(tmp_path / "config", ("mysql", "maintenance"), values,
                         name=f"config-invalid-{credential}-{missing}"))["services"]["db"]
    assert db["environment"][credential] == "", "missing credentials must not acquire a default password"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    result = _entrypoint(runtime, db, {key: _container_shell(value) for key, value in db["environment"].items()},
                         name=f"config-invalid-runtime-{credential}-{missing}")
    assert result.returncode != 0 and credential in result.stderr
    assert not (runtime / "entrypoint.args").exists()


def _load_deployment(workspace: Path, provider: str, host: str, credentials: dict, name="load"):
    deploy = workspace / "deploy"
    deploy.mkdir(parents=True)
    (deploy / "scripts").mkdir()
    shutil.copyfile(DEPLOY / "scripts/deploy_docker.sh", deploy / "scripts/deploy_docker.sh")
    shutil.copyfile(DEPLOY / "docker-compose.yml", deploy / "docker-compose.yml")
    values = {**CREDENTIALS, "DB_PROVIDER": provider, "MYSQL_HOST": host, **credentials}
    def quote(value):
        return "'" + value.replace("'", "'\"'\"'") + "'"
    (deploy / ".env").write_text("".join(f"{key}={quote(value)}\n" for key, value in values.items()), encoding="utf-8")
    _stub(workspace, "docker", 'printf "%s\\n" "$*" >> docker.calls\ncase "$*" in\n'
          '  "compose version"|"info") exit 0;;\n  "compose "*" config --quiet") exit 0;;\n  *) exit 97;;\nesac\n')
    result = _shell(workspace, '[[ "$(command -v docker)" == "$PWD/bin/docker" ]] || exit 98; '
                    'source deploy/scripts/deploy_docker.sh; load_deployment; '
                    'printf "LOAD_OK:%s:%s\\n" "$DB_PROVIDER" "$INTERNAL_MYSQL"; '
                    'printf "ARG:%s\\n" "${COMPOSE_ARGS[@]}"', {}, name=name)
    calls = (workspace / "docker.calls").read_text() if (workspace / "docker.calls").exists() else ""
    return result, calls


@pytest.mark.parametrize("provider,host,credentials,internal", [
    ("sqlite", "db", {}, "false"),
    ("mysql", "db", MYSQL_CREDENTIALS, "true"),
    ("mysql", "external-db.invalid", {"MYSQL_PASSWORD": MYSQL_CREDENTIALS["MYSQL_PASSWORD"]}, "false"),
], ids=["sqlite", "internal-mysql", "external-mysql"])
def test_existing_release_loader_selects_profiles(tmp_path, provider, host, credentials, internal):
    result, calls = _load_deployment(tmp_path, provider, host, credentials, name=f"load-{provider}-{internal}")
    assert result.returncode == 0, result.stderr
    assert f"LOAD_OK:{provider}:{internal}" in result.stdout
    assert "ARG:maintenance" in result.stdout
    assert ("ARG:mysql" in result.stdout) == (internal == "true")
    assert len(calls.splitlines()) == 3
    assert not any(password in calls for password in credentials.values())
    assert not (tmp_path / "deploy/.deployment-lock").exists()


@pytest.mark.parametrize("host,credential", [("db", "MYSQL_PASSWORD"), ("db", "MYSQL_ROOT_PASSWORD"), ("external-db.invalid", "MYSQL_PASSWORD")])
@pytest.mark.parametrize("missing", [True, False], ids=["missing", "empty"])
def test_release_loader_rejects_credentials_before_docker(tmp_path, host, credential, missing):
    values = dict(MYSQL_CREDENTIALS)
    values.pop(credential)
    if not missing:
        values[credential] = ""
    result, calls = _load_deployment(tmp_path, "mysql", host, values, name=f"load-invalid-{host}-{credential}-{missing}")
    assert result.returncode != 0
    assert credential in result.stderr
    assert calls == "", "credential validation must precede all Docker activity"
    assert not (tmp_path / "backups").exists()


def test_in_process_negative_controls(tmp_path, mysql_model):
    """Mutate in-memory inputs, use the same assertions/probes, never edit production files."""
    killed = []
    text = (DEPLOY / ".env.example").read_text(encoding="utf-8")
    with pytest.raises(AssertionError, match="direct compose up"):
        _assert_entry_document(text.replace("bash deploy/scripts/deploy_docker.sh", "docker compose up -d"))
    killed.append("direct-up-entry")
    broken_env = text + "\nSECRET_KEY=broken unquoted space\n"
    assert _source_example(tmp_path, broken_env, "negative-unquoted-env").returncode != 0
    killed.append("unquoted-env")
    source = (DEPLOY / "docker-compose.yml").read_text(encoding="utf-8")
    for credential in MYSQL_CREDENTIALS:
        broken = source.replace(f"{credential}: ${{{credential}:-}}", f"{credential}: ${{{credential}:-bad-default}}")
        with pytest.raises(AssertionError):
            _assert_no_defaults(broken)
        killed.append(f"default-{credential}")
    broken = source.replace("MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-}", "MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:?required}")
    result = _compose(tmp_path / "required", source=broken, name="negative-inactive-profile-required")
    assert result.returncode != 0 and "MYSQL_ROOT_PASSWORD" in result.stderr
    killed.append("inactive-profile-global-required")
    db = copy.deepcopy(mysql_model["services"]["db"])
    db["healthcheck"]["test"] = ["CMD", "mysqladmin", "ping", "-proot-literal"]
    with pytest.raises(AssertionError):
        _assert_health_uses_environment(db)
    killed.append("health-cli-password")
    for credential in MYSQL_CREDENTIALS:
        db = copy.deepcopy(mysql_model["services"]["db"])
        entry = db.get("entrypoint")
        assert entry, "baseline credential guard must exist before mutation"
        lines = entry[3].splitlines(keepends=True)
        changed = "".join(line for line in lines if not (line.strip().startswith(": ") and credential in line))
        assert changed != entry[3], "mutation must remove an actual guard"
        entry[3] = changed
        workspace = tmp_path / credential
        workspace.mkdir()
        values = dict(MYSQL_CREDENTIALS)
        values.pop(credential)
        result = _entrypoint(workspace, db, values, name=f"negative-guard-{credential}")
        with pytest.raises(AssertionError):
            assert result.returncode != 0 and not (workspace / "entrypoint.args").exists()
        assert (workspace / "entrypoint.args").exists()
        killed.append(f"guard-{credential}")
    _record("negative-controls", {"process": os.getpid(), "mutations_detected": killed, "count": len(killed), "production_files_mutated": False})
    assert len(killed) == 8
