"""ComposeDriver: one sandbox = a labelled set of containers on one internal network.

Talks to the Docker Engine API (aiodocker; npipe on Windows, the unix socket elsewhere). No
compose CLI: the driver needs per-step control (dependency waits, files before start,
recreating one service with new env) and must work from Temporal activities.

Isolation (ADR 012, PLAN §12.2):
- one `internal: true` bridge network per sandbox: no egress, no route to the host;
- nothing is published on the host; the platform reaches in only through the Docker API;
- cgroup limits on every container (CPU, memory without swap, pids), NET_RAW dropped,
  no-new-privileges; images' declared volumes become tmpfs, so nothing outlives the sandbox;
- everything carries `devgrill.*` labels, so destroy and the orphan sweeper find it all.

Every operation is idempotent where it can be: `create` first destroys anything left from a
previous try of the same attempt, `destroy` ignores what is already gone.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import shlex
import tarfile
import time
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import aiodocker
import structlog
from aiodocker.containers import DockerContainer
from aiodocker.exceptions import DockerError

from devgrill.domain.spec import FaultApply
from devgrill.sandbox.baseapp import BaseAppSpec
from devgrill.sandbox.content import Bundle, Fault, render_apply, resolve_params
from devgrill.sandbox.driver import (
    DeployResult,
    ExecResult,
    LogLine,
    MetricSnapshot,
    ResourceUsage,
    SandboxError,
    SandboxHandle,
    SandboxSpec,
)
from devgrill.sandbox.images import ensure_built, ensure_pulled

log = structlog.get_logger(__name__)

LABEL_MANAGED = "devgrill.managed"
LABEL_SANDBOX = "devgrill.sandbox"
LABEL_ATTEMPT = "devgrill.attempt"
LABEL_SERVICE = "devgrill.service"
PROBE = "--probe"  # container suffix; service names can't start with "-", so no clash

_MIB = 1024 * 1024
_SEC = 1_000_000_000
PIDS_LIMIT = 256
SHELL_PIDS_LIMIT = 512
PROBE_CPUS = 1.0
PROBE_MEMORY_MB = 512
_STAGE = "/tmp/devgrill"  # scratch dir inside containers for scripts and patches
_COMMIT = 'git add -A && git commit -q -m "$MSG"'
_LOG_TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?Z\s?(.*)$")


def project_name(attempt_id: str) -> str:
    """`dg-` + 12 hex chars of the attempt id: short, unique, valid as a container name."""
    return "dg-" + re.sub(r"[^a-z0-9]", "", attempt_id.lower())[:12]


def _tar(files: dict[str, bytes], *, mode: int = 0o644) -> bytes:
    """A tar of {path: content}, with parent directories, for put_archive at "/"."""
    buf = io.BytesIO()
    now = int(time.time())
    with tarfile.open(fileobj=buf, mode="w") as tar:
        dirs: set[str] = set()
        for name in files:
            for parent in reversed(PurePosixPath(name).parents):
                key = str(parent)
                if key in (".", "/") or key in dirs:
                    continue
                dirs.add(key)
                info = tarfile.TarInfo(key)
                info.type, info.mode, info.mtime = tarfile.DIRTYPE, 0o755, now
                tar.addfile(info)
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), mode, now
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _folder_files(folder: Path, prefix: str) -> dict[str, bytes]:
    skip = {"__pycache__", ".git", ".venv", "node_modules"}
    out: dict[str, bytes] = {}
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder)
        if not path.is_file() or skip.intersection(rel.parts):
            continue
        out[f"{prefix}/{rel.as_posix()}"] = path.read_bytes().replace(b"\r\n", b"\n")
    return out


def _levels(app: BaseAppSpec) -> list[list[str]]:
    """Services grouped by dependency depth: everything in a level can start together."""
    depth: dict[str, int] = {}
    for name in app.ordered():
        deps = app.services[name].depends_on
        depth[name] = 1 + max((depth[d] for d in deps), default=-1)
    levels: list[list[str]] = [[] for _ in range(max(depth.values()) + 1)]
    for name, d in depth.items():
        levels[d].append(name)
    return levels


def _num(value: object) -> object:
    """Toxic attributes arrive as rendered strings; Toxiproxy wants numbers."""
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value):
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def _git_env(minutes_ago: float, author: str = "deploy-bot") -> dict[str, str]:
    stamp = f"@{int(time.time() - minutes_ago * 60)} +0530"
    return {
        "GIT_AUTHOR_DATE": stamp,
        "GIT_COMMITTER_DATE": stamp,
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": f"{author}@shopkart.test",
        "GIT_COMMITTER_NAME": author,
        "GIT_COMMITTER_EMAIL": f"{author}@shopkart.test",
    }


# Sets KEY=value lines in an env file, keeping comments and order (runs in the shell container).
_SET_ENV_PY = """
import sys
path, pairs = sys.argv[1], dict(a.split("=", 1) for a in sys.argv[2:])
lines = open(path, encoding="utf-8").read().splitlines()
seen = set()
for i, line in enumerate(lines):
    key = line.split("=", 1)[0].strip()
    if "=" in line and not line.lstrip().startswith("#") and key in pairs:
        lines[i] = f"{key}={pairs[key]}"
        seen.add(key)
lines += [f"{k}={v}" for k, v in pairs.items() if k not in seen]
open(path, "w", encoding="utf-8").write("\\n".join(lines) + "\\n")
"""


class ComposeDriver:
    def __init__(
        self,
        *,
        docker: aiodocker.Docker | None = None,
        probe_image: str = "devgrill/sandbox-probe:1",
        probe_build_dir: Path | None = None,
        healthy_timeout_s: int = 120,
    ) -> None:
        self._docker = docker or aiodocker.Docker()
        self._probe_image = probe_image
        self._probe_build_dir = probe_build_dir
        self._healthy_timeout_s = healthy_timeout_s

    async def close(self) -> None:
        await self._docker.close()

    # ---------------------------------------------------------------------------- helpers

    @staticmethod
    def _labels(handle: SandboxHandle) -> dict[str, str]:
        return {LABEL_MANAGED: "1", LABEL_SANDBOX: handle.ref, LABEL_ATTEMPT: handle.attempt_id}

    @staticmethod
    def _network(handle: SandboxHandle) -> str:
        return f"{handle.ref}-net"

    async def _container(self, handle: SandboxHandle, service: str) -> DockerContainer:
        name = f"{handle.ref}{PROBE}" if service == PROBE else f"{handle.ref}-{service}"
        try:
            return await self._docker.containers.get(name)
        except DockerError as exc:
            if exc.status == 404:
                raise SandboxError(f"{service} is not running in {handle.ref}") from exc
            raise

    async def _run(
        self,
        container: DockerContainer,
        argv: list[str],
        *,
        timeout_s: float = 60,
        env: dict[str, str] | None = None,
        workdir: str | None = None,
    ) -> ExecResult:
        execution = await container.exec(argv, environment=env, workdir=workdir)
        out, err = bytearray(), bytearray()

        async def pump() -> None:
            async with execution.start(detach=False) as stream:
                while (message := await stream.read_out()) is not None:
                    (out if message.stream == 1 else err).extend(message.data)

        try:
            await asyncio.wait_for(pump(), timeout_s)
        except TimeoutError:
            return ExecResult(
                124, out.decode(errors="replace"), err.decode(errors="replace") + "\n[timed out]"
            )
        code: int | None = None
        for _ in range(20):  # the exit code lands a moment after the stream closes
            info = await execution.inspect()
            if not info.get("Running"):
                code = info.get("ExitCode")
                break
            await asyncio.sleep(0.05)
        return ExecResult(
            -1 if code is None else code, out.decode(errors="replace"), err.decode(errors="replace")
        )

    async def _run_detached(self, container: DockerContainer, argv: list[str]) -> None:
        execution = await container.exec(argv)
        await execution.start(detach=True)

    async def _put(
        self, container: DockerContainer, files: dict[str, bytes], *, mode: int = 0o644
    ) -> None:
        """Copy files into a container (created or running). Paths are absolute."""
        await container.put_archive(
            "/", _tar({k.lstrip("/"): v for k, v in files.items()}, mode=mode)
        )

    async def _must(
        self, container: DockerContainer, argv: list[str], what: str, **kw: Any
    ) -> ExecResult:
        result = await self._run(container, argv, **kw)
        if not result.ok:
            raise SandboxError(
                f"{what} failed ({result.exit_code}): {(result.stderr or result.stdout)[-2000:]}"
            )
        return result

    # ----------------------------------------------------------------------------- create

    async def ensure_images(self, bundle: Bundle) -> None:
        app = bundle.base_app
        jobs = []
        for name, svc in app.services.items():
            if svc.build:
                jobs.append(
                    ensure_built(self._docker, app.image_for(name), bundle.base_app_dir / svc.build)
                )
            else:
                jobs.append(ensure_pulled(self._docker, app.image_for(name)))
        if self._probe_build_dir is not None:
            jobs.append(ensure_built(self._docker, self._probe_image, self._probe_build_dir))
        else:
            jobs.append(ensure_pulled(self._docker, self._probe_image))
        await asyncio.gather(*jobs)

    async def create(self, spec: SandboxSpec) -> SandboxHandle:
        bundle = spec.bundle
        handle = SandboxHandle(spec.attempt_id, project_name(spec.attempt_id))
        await self.destroy(handle)  # a retried activity starts from a clean slate
        await self.ensure_images(bundle)
        started = time.monotonic()
        await self._docker.networks.create(
            {
                "Name": self._network(handle),
                "Driver": "bridge",
                "Internal": True,
                "CheckDuplicate": True,
                "Labels": self._labels(handle),
            }
        )
        try:
            await self._start_probe(handle, bundle)
            for level in _levels(bundle.base_app):
                await asyncio.gather(*(self._start_service(handle, spec, name) for name in level))
                await asyncio.gather(*(self._wait_service(handle, name) for name in level))
            await self._init_repos(handle, bundle)
        except BaseException:
            await asyncio.shield(self.destroy(handle))
            raise
        log.info(
            "sandbox.created", sandbox=handle.ref, seconds=round(time.monotonic() - started, 1)
        )
        return handle

    async def _start_probe(self, handle: SandboxHandle, bundle: Bundle) -> None:
        container = await self._docker.containers.create(
            {
                "Image": self._probe_image,
                "Hostname": "probe",
                "Labels": {**self._labels(handle), LABEL_SERVICE: PROBE},
                "Env": ["K6_NO_USAGE_REPORT=true"],
                "HostConfig": self._host_config(
                    handle, PROBE_CPUS, PROBE_MEMORY_MB, PIDS_LIMIT, {}
                ),
                "NetworkingConfig": {"EndpointsConfig": {self._network(handle): {}}},
            },
            name=f"{handle.ref}{PROBE}",
        )
        files = _folder_files(bundle.base_app_dir / "load", "probe/load")
        verify = bundle.scenario_dir / "verify"
        if verify.is_dir():
            files |= _folder_files(verify, "probe/verify")
        if files:
            await self._put(container, files)
        await container.start()

    def _host_config(
        self, handle: SandboxHandle, cpus: float, memory_mb: int, pids: int, tmpfs: dict[str, str]
    ) -> dict[str, Any]:
        return {
            "NetworkMode": self._network(handle),
            "NanoCpus": int(cpus * _SEC),
            "Memory": memory_mb * _MIB,
            "MemorySwap": memory_mb * _MIB,  # no swap: a leak ends in an OOM kill, as in prod
            "PidsLimit": pids,
            "Tmpfs": tmpfs,
            "CapDrop": ["NET_RAW"],
            "SecurityOpt": ["no-new-privileges"],
            "LogConfig": {"Type": "json-file", "Config": {"max-size": "10m", "max-file": "2"}},
            # Crashed and OOM-killed services come back, like under any orchestrator.
            "RestartPolicy": {"Name": "on-failure", "MaximumRetryCount": 0},
        }

    async def _service_config(
        self,
        handle: SandboxHandle,
        spec: SandboxSpec,
        name: str,
        env_overrides: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        app = spec.bundle.base_app
        svc = app.services[name]
        image = app.image_for(name)
        info = await self._docker.images.inspect(image)
        volumes = (info.get("Config") or {}).get("Volumes") or {}
        size = min(svc.memory_mb // 2, 256)
        tmpfs = {path: f"size={size}m" for path in volumes}
        env = dict(svc.env) | (env_overrides or {})
        if svc.shell:
            env |= {
                "DEVGRILL_CONTROL_URL": "http://control:7000",
                "DEVGRILL_CONTROL_TOKEN": spec.control_token,
                "DEVGRILL_ATTEMPT": spec.attempt_id,
            }
        config: dict[str, Any] = {
            "Image": image,
            "Hostname": name,
            "Env": [f"{k}={v}" for k, v in env.items()],
            "Labels": {**self._labels(handle), LABEL_SERVICE: name},
            "HostConfig": self._host_config(
                handle,
                svc.cpus,
                svc.memory_mb,
                SHELL_PIDS_LIMIT if svc.shell else PIDS_LIMIT,
                tmpfs,
            ),
            "NetworkingConfig": {
                "EndpointsConfig": {self._network(handle): {"Aliases": [name, *svc.aliases]}}
            },
        }
        if svc.command:
            config["Cmd"] = svc.command
        if svc.healthcheck:
            config["Healthcheck"] = {
                "Test": ["CMD", *svc.healthcheck],
                "Interval": 5 * _SEC,
                "Timeout": 3 * _SEC,
                "Retries": 3,
                "StartPeriod": 120 * _SEC,
                "StartInterval": 1 * _SEC,
            }
        return config

    async def _start_service(
        self,
        handle: SandboxHandle,
        spec: SandboxSpec,
        name: str,
        env_overrides: dict[str, str] | None = None,
    ) -> None:
        svc = spec.bundle.base_app.services[name]
        config = await self._service_config(handle, spec, name, env_overrides)
        container = await self._docker.containers.create(config, name=f"{handle.ref}-{name}")
        if svc.files:
            await self._put(
                container,
                {
                    dest: (spec.bundle.base_app_dir / src).read_bytes().replace(b"\r\n", b"\n")
                    for dest, src in svc.files.items()
                },
            )
        await container.start()

    async def _wait_service(
        self, handle: SandboxHandle, name: str, timeout_s: float | None = None
    ) -> None:
        container = await self._container(handle, name)
        deadline = time.monotonic() + (timeout_s or self._healthy_timeout_s)
        while True:
            state = (await container.show())["State"]
            health = (state.get("Health") or {}).get("Status")
            if state.get("Status") == "running" and health in (None, "healthy"):
                return
            # A crashed service is restarted by its on-failure policy: keep waiting.
            if time.monotonic() > deadline:
                tail = await self._tail(container, 30)
                status = state.get("Status")
                raise SandboxError(
                    f"{name} did not become healthy (state={status}, health={health}):\n{tail}"
                )
            await asyncio.sleep(0.5)

    async def _tail(self, container: DockerContainer, lines: int) -> str:
        try:
            chunks = await container.log(stdout=True, stderr=True, tail=str(lines))
        except DockerError:
            return ""
        return "".join(chunks)[-4000:]

    async def wait_healthy(self, handle: SandboxHandle, timeout_s: int) -> None:
        containers = await self._containers(handle)
        names = [
            c["Labels"][LABEL_SERVICE]
            for c in containers
            if c["Labels"].get(LABEL_SERVICE) != PROBE
        ]
        if not names:
            raise SandboxError(f"{handle.ref} has no services")
        await asyncio.gather(*(self._wait_service(handle, n, timeout_s) for n in names))

    # ---------------------------------------------------------------------------- git

    @staticmethod
    def _repo(service: str) -> str:
        return f"/workspace/{service}"

    async def _init_repos(self, handle: SandboxHandle, bundle: Bundle) -> None:
        """The patchable services' source as git repos in the shell, with the scenario's history."""
        app = bundle.base_app
        shell = await self._container(handle, app.shell_service)
        plain = sorted(
            (e for e in bundle.scenario.deploy_history if not e.from_fault),
            key=lambda e: -e.minutes_before,
        )
        for name, svc in app.services.items():
            if not svc.source or not svc.build:
                continue
            repo = self._repo(name)
            await self._put(shell, _folder_files(bundle.base_app_dir / svc.build, repo.lstrip("/")))
            oldest = max([e.minutes_before for e in plain] + [0]) + 60 * 24 * 30
            await self._must(
                shell,
                ["sh", "-c", 'git init -q -b main && git add -A && git commit -q -m "$MSG"'],
                f"git init {name}",
                env={**_git_env(oldest, "priya"), "MSG": f"{app.name} {name}: initial import"},
                workdir=repo,
            )
            for entry in plain:
                await self._must(
                    shell,
                    ["sh", "-c", f'printf -- "- %s\\n" "$MSG" >> CHANGELOG.md && {_COMMIT}'],
                    f"git history {name}",
                    env={**_git_env(entry.minutes_before), "MSG": entry.message},
                    workdir=repo,
                )

    async def _commit(
        self, handle: SandboxHandle, bundle: Bundle, service: str, message: str, minutes_ago: float
    ) -> None:
        shell = await self._container(handle, bundle.base_app.shell_service)
        await self._must(
            shell,
            ["sh", "-c", 'git add -A && git commit -q -m "$MSG"'],
            f"commit {service}",
            env={**_git_env(minutes_ago), "MSG": message},
            workdir=self._repo(service),
        )

    # ---------------------------------------------------------------------------- faults

    @staticmethod
    def _deploy_entry(bundle: Bundle, fault: Fault) -> tuple[str, float]:
        """The commit message and age for a fault that ships as a deploy."""
        for entry in bundle.scenario.deploy_history:
            if entry.from_fault == fault.ref:
                return entry.message, float(entry.minutes_before)
        for step in bundle.scenario.faults:
            if step.use == fault.ref and step.at_seconds < 0:
                return fault.spec.deploy_message or f"change: {fault.ref}", -step.at_seconds / 60
        return fault.spec.deploy_message or f"change: {fault.ref}", 0.0

    async def apply_fault(
        self, handle: SandboxHandle, bundle: Bundle, use: str, params: dict[str, object]
    ) -> None:
        fault = bundle.faults[use]
        values = resolve_params(fault.spec, params)
        message, minutes_ago = self._deploy_entry(bundle, fault)
        for step in (fault.spec.apply, fault.spec.also):
            if step is not None:
                await self._apply_step(
                    handle, bundle, fault, render_apply(step, values), message, minutes_ago
                )
        log.info("sandbox.fault_applied", sandbox=handle.ref, fault=use)

    async def revert_fault(
        self, handle: SandboxHandle, bundle: Bundle, use: str, params: dict[str, object]
    ) -> None:
        fault = bundle.faults[use]
        values = resolve_params(fault.spec, params)
        if fault.spec.revert is not None:
            await self._apply_step(
                handle, bundle, fault, render_apply(fault.spec.revert, values), f"revert: {use}", 0
            )
            return
        step = render_apply(fault.spec.apply, values)
        app = bundle.base_app
        if step.toxic:
            await self.toxic_delete(
                handle, bundle, str(step.toxic["proxy"]), f"dg-{fault.ref.replace('/', '-')}"
            )
        elif step.patch and step.service:
            shell = await self._container(handle, app.shell_service)
            await self._put(
                shell, {f"{_STAGE}/fault.diff": (fault.folder / step.patch).read_bytes()}
            )
            await self._must(
                shell,
                ["git", "apply", "-R", "-p0", f"{_STAGE}/fault.diff"],
                "revert patch",
                workdir=self._repo(step.service),
            )
            await self._run(shell, ["rm", "-f", f"{_STAGE}/fault.diff"])
            await self._commit(handle, bundle, step.service, f'Revert "{use}"', 0)
            await self._deploy_checked(handle, bundle, step.service)
        elif step.env and step.service:
            svc = app.services[step.service]
            if svc.source and svc.source.config_file:
                original = _read_env_file(
                    bundle.base_app_dir / (svc.build or "") / svc.source.config_file
                )
                await self._set_config(
                    handle, bundle, step.service, {k: original.get(k, "") for k in step.env}
                )
                await self._commit(handle, bundle, step.service, f'Revert "{use}"', 0)
                await self._deploy_checked(handle, bundle, step.service)
            else:
                await self._recreate(handle, bundle, step.service, {})
        else:
            raise SandboxError(f"{use} has no revert step")

    async def _apply_step(
        self,
        handle: SandboxHandle,
        bundle: Bundle,
        fault: Fault,
        step: FaultApply,
        message: str,
        minutes_ago: float,
    ) -> None:
        app = bundle.base_app
        if step.toxic:
            await self._toxic_add(handle, bundle, fault, dict(step.toxic))
            return
        assert step.service is not None  # FaultApply guarantees it for the rest
        svc = app.services[step.service]
        if step.patch:
            shell = await self._container(handle, app.shell_service)
            await self._put(
                shell,
                {
                    f"{_STAGE}/fault.diff": (fault.folder / step.patch)
                    .read_bytes()
                    .replace(b"\r\n", b"\n")
                },
            )
            await self._must(
                shell,
                ["git", "apply", "-p0", f"{_STAGE}/fault.diff"],
                f"apply {fault.ref}",
                workdir=self._repo(step.service),
            )
            await self._run(shell, ["rm", "-f", f"{_STAGE}/fault.diff"])
            await self._commit(handle, bundle, step.service, message, minutes_ago)
            await self._deploy_checked(handle, bundle, step.service)
        elif step.env is not None:
            if svc.source and svc.source.config_file:
                await self._set_config(handle, bundle, step.service, dict(step.env))
                await self._commit(handle, bundle, step.service, message, minutes_ago)
                await self._deploy_checked(handle, bundle, step.service)
            else:
                await self._recreate(handle, bundle, step.service, dict(step.env))
        elif step.script:
            await self._script(handle, bundle, fault, step)

    async def _set_config(
        self, handle: SandboxHandle, bundle: Bundle, service: str, values: dict[str, str]
    ) -> None:
        svc = bundle.base_app.services[service]
        assert svc.source
        assert svc.source.config_file
        shell = await self._container(handle, bundle.base_app.shell_service)
        path = f"{self._repo(service)}/{svc.source.config_file}"
        await self._must(
            shell,
            ["python3", "-c", _SET_ENV_PY, path, *(f"{k}={v}" for k, v in values.items())],
            f"config {service}",
        )

    async def _recreate(
        self, handle: SandboxHandle, bundle: Bundle, service: str, env: dict[str, str]
    ) -> None:
        """Replace a service's container with one that has `env` on top of the base app's."""
        old = await self._container(handle, service)
        await old.delete(force=True, v=True)
        spec = SandboxSpec(handle.attempt_id, bundle)
        await self._start_service(handle, spec, service, env)
        await self._wait_service(handle, service)

    async def _script(
        self, handle: SandboxHandle, bundle: Bundle, fault: Fault, step: FaultApply
    ) -> None:
        assert step.script
        assert step.service
        svc = bundle.base_app.services[step.service]
        container = await self._container(handle, step.service)
        target = f"{_STAGE}/{fault.ref.replace('/', '-')}-{PurePosixPath(step.script).name}"
        await self._put(
            container, {target: (fault.folder / step.script).read_bytes().replace(b"\r\n", b"\n")}
        )
        if step.script.endswith(".sql"):
            assert svc.sql is not None
            argv = [
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                svc.sql.user,
                "-d",
                svc.sql.database,
                "-f",
                target,
            ]
        elif step.script.endswith(".py"):
            argv = ["python3", target]
        else:
            argv = ["sh", target]
        if step.detach:
            await self._run_detached(container, argv)
            return
        await self._must(container, argv, f"{fault.ref} script", timeout_s=180)
        await self._run(container, ["rm", "-f", target])

    def _toxiproxy_url(self, bundle: Bundle) -> str:
        name = bundle.base_app.toxiproxy_service
        if name is None:
            raise SandboxError(f"{bundle.base_app.slug} has no toxiproxy")
        spec = bundle.base_app.services[name].toxiproxy
        assert spec is not None
        return f"http://{name}:{spec.admin_port}"

    async def toxic(
        self, handle: SandboxHandle, bundle: Bundle, name: str, toxic: dict[str, object]
    ) -> None:
        """Add a toxic (verifier chaos steps use this too)."""
        attributes = {
            k: _num(v) for k, v in toxic.items() if k not in ("proxy", "type", "stream", "toxicity")
        }
        body = {
            "name": name,
            "type": toxic["type"],
            "stream": toxic.get("stream", "downstream"),
            "toxicity": float(str(toxic.get("toxicity", 1.0))),
            "attributes": attributes,
        }
        probe = await self._container(handle, PROBE)
        url = f"{self._toxiproxy_url(bundle)}/proxies/{toxic['proxy']}/toxics"
        await self._must(
            probe,
            [
                "curl",
                "-sS",
                "-f",
                "-X",
                "POST",
                "-H",
                "content-type: application/json",
                "-d",
                json.dumps(body),
                url,
            ],
            f"toxic {name}",
        )

    async def _toxic_add(
        self, handle: SandboxHandle, bundle: Bundle, fault: Fault, toxic: dict[str, object]
    ) -> None:
        await self.toxic(handle, bundle, f"dg-{fault.ref.replace('/', '-')}", toxic)

    async def toxic_delete(
        self, handle: SandboxHandle, bundle: Bundle, proxy: str, name: str
    ) -> None:
        probe = await self._container(handle, PROBE)
        url = f"{self._toxiproxy_url(bundle)}/proxies/{proxy}/toxics/{name}"
        await self._run(probe, ["curl", "-sS", "-X", "DELETE", url])

    # ------------------------------------------------------------------------------ load

    async def start_load(
        self, handle: SandboxHandle, bundle: Bundle, *, multiplier: float = 1.0
    ) -> None:
        """The "sale": k6 in the probe, in the background, until stopped or torn down."""
        profile = bundle.scenario.load
        if profile is None:
            return
        env = {
            "TARGET": bundle.base_app.load.target,
            "VUS": str(max(1, round(profile.vus * multiplier))),
            "DURATION": "4h",
            **{k: str(v) for k, v in profile.params.items()},
        }
        flags = " ".join(f"-e {k}={shlex.quote(v)}" for k, v in env.items())
        script = f"/probe/load/{profile.script}"
        command = (
            f"nohup k6 run --quiet {flags} {shlex.quote(script)} "
            "> /probe/out/play-load.log 2>&1 & echo $! > /probe/out/play-load.pid"
        )
        probe = await self._container(handle, PROBE)
        await self._must(probe, ["sh", "-c", command], "start load")

    async def stop_load(self, handle: SandboxHandle) -> None:
        probe = await self._container(handle, PROBE)
        pid = "/probe/out/play-load.pid"
        await self._run(
            probe, ["sh", "-c", f"[ -f {pid} ] && kill $(cat {pid}); rm -f {pid}; true"]
        )

    # ------------------------------------------------------------------------- operate

    async def exec(
        self, handle: SandboxHandle, service: str, argv: list[str], *, timeout_s: int = 60
    ) -> ExecResult:
        return await self._run(await self._container(handle, service), argv, timeout_s=timeout_s)

    async def probe(
        self, handle: SandboxHandle, argv: list[str], *, timeout_s: int = 60
    ) -> ExecResult:
        return await self._run(await self._container(handle, PROBE), argv, timeout_s=timeout_s)

    async def put_probe_files(self, handle: SandboxHandle, files: dict[str, bytes]) -> None:
        await self._put(await self._container(handle, PROBE), files)

    async def deploy(
        self, handle: SandboxHandle, bundle: Bundle, service: str, ref: str | None = None
    ) -> DeployResult:
        """Copy the service's source from the shell's repo (working tree or a commit); restart."""
        svc = bundle.base_app.services.get(service)
        if svc is None or svc.source is None:
            raise SandboxError(f"{service} can't be deployed (not patchable)")
        source = svc.source
        shell = await self._container(handle, bundle.base_app.shell_service)
        repo = self._repo(service)
        paths = " ".join(shlex.quote(p) for p in source.paths)
        export = (
            f"git archive {shlex.quote(ref)} {paths} | tar -x -C {_STAGE}/deploy"
            if ref
            else f"cp -a {paths} {_STAGE}/deploy/"
        )
        script = (
            f"rm -rf {_STAGE}/deploy && mkdir -p {_STAGE}/deploy && {export}"
            f" && git rev-parse --short {shlex.quote(ref or 'HEAD')}"
            " && git status --porcelain | head -1"
        )
        prepared = await self._run(shell, ["sh", "-c", script], workdir=repo)
        if not prepared.ok:
            return DeployResult(
                False, ref or "", "could not read the source", prepared.stderr[-2000:]
            )
        lines = prepared.stdout.splitlines()
        sha = lines[0].strip() if lines else ""
        dirty = ref is None and len(lines) > 1
        archive = await shell.get_archive(f"{_STAGE}/deploy")
        files: dict[str, bytes] = {}
        for member in archive.getmembers():
            if not member.isfile():
                continue
            rel = PurePosixPath(member.name).relative_to("deploy")
            extracted = archive.extractfile(member)
            if extracted is not None:
                files[f"{source.dest}/{rel.as_posix()}"] = extracted.read()
        await self._run(shell, ["rm", "-rf", f"{_STAGE}/deploy"])
        target = await self._container(handle, service)
        await self._run(
            target,
            [
                "sh",
                "-c",
                " ".join(f"rm -rf {shlex.quote(source.dest + '/' + p)}" for p in source.paths),
            ],
        )
        await self._put(target, files)
        await target.restart(timeout=5)
        label = f"{sha}{' (with uncommitted changes)' if dirty else ''}"
        try:
            await self._wait_service(handle, service, 90)
        except SandboxError as exc:
            return DeployResult(False, sha, f"{service} {label} is unhealthy", str(exc)[-4000:])
        return DeployResult(True, sha, f"{service} {label} is live", "")

    async def patch(
        self, handle: SandboxHandle, bundle: Bundle, service: str, diff: bytes, message: str
    ) -> DeployResult:
        """Apply a -p0 diff to the service's repo, commit it and deploy (solutions, approaches)."""
        shell = await self._container(handle, bundle.base_app.shell_service)
        await self._put(shell, {f"{_STAGE}/change.diff": diff.replace(b"\r\n", b"\n")})
        applied = await self._run(
            shell, ["git", "apply", "-p0", f"{_STAGE}/change.diff"], workdir=self._repo(service)
        )
        await self._run(shell, ["rm", "-f", f"{_STAGE}/change.diff"])
        if not applied.ok:
            return DeployResult(False, "", "the patch does not apply", applied.stderr[-2000:])
        await self._commit(handle, bundle, service, message, 0)
        return await self.deploy(handle, bundle, service)

    async def _deploy_checked(self, handle: SandboxHandle, bundle: Bundle, service: str) -> None:
        result = await self.deploy(handle, bundle, service)
        if not result.ok:
            raise SandboxError(f"deploy of {service} failed: {result.message}\n{result.log}")

    async def restart(self, handle: SandboxHandle, service: str) -> None:
        await (await self._container(handle, service)).restart(timeout=5)

    async def logs(
        self, handle: SandboxHandle, *, since: datetime | None = None, tail: int = 200
    ) -> AsyncIterator[LogLine]:
        """Recent log lines of every service, oldest first."""
        lines: list[LogLine] = []
        for info in await self._containers(handle):
            service = info["Labels"].get(LABEL_SERVICE, "")
            if service == PROBE:
                continue
            container = self._docker.containers.container(info["Id"])
            params: dict[str, Any] = {"timestamps": "true", "tail": str(tail)}
            if since is not None:
                params["since"] = str(int(since.timestamp()))
            try:
                chunks = await container.log(stdout=True, stderr=True, **params)
            except DockerError:
                continue
            for raw in "".join(chunks).splitlines():
                match = _LOG_TS.match(raw)
                if not match:
                    continue
                stamp, frac, text = match.groups()
                ts = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
                if frac:
                    ts = ts.replace(microsecond=int(frac[:6].ljust(6, "0")))
                lines.append(LogLine(ts, service, text))
        for line in sorted(lines, key=lambda item: item.ts):
            yield line

    async def metrics(self, handle: SandboxHandle, bundle: Bundle) -> MetricSnapshot:
        targets = [
            f"{name}={name}:{svc.scrape_path}"
            for name, svc in bundle.base_app.services.items()
            if svc.scrape_path
        ]
        at = datetime.now(UTC)
        result = await self.probe(handle, ["dg-scrape", *targets], timeout_s=10)
        raw: dict[str, str] = {}
        job: str | None = None
        buf: list[str] = []
        for line in result.stdout.splitlines():
            if line.startswith("### "):
                if job is not None:
                    raw[job] = "\n".join(buf)
                job, buf = line[4:].strip(), []
            else:
                buf.append(line)
        if job is not None:
            raw[job] = "\n".join(buf)
        return MetricSnapshot(at, raw)

    async def usage(self, handle: SandboxHandle) -> ResourceUsage:
        """CPU seconds and memory across the sandbox, read from every container at once."""

        async def one(container_id: str) -> tuple[int, int]:
            try:
                # `one-shot` answers immediately instead of waiting a second for a second
                # sample; aiodocker's stats() can't pass it, so call the endpoint directly.
                sample = await self._docker._query_json(
                    f"containers/{container_id}/stats", params={"stream": "0", "one-shot": "1"}
                )
            except DockerError:
                return 0, 0
            cpu = ((sample.get("cpu_stats") or {}).get("cpu_usage") or {}).get("total_usage")
            memory = (sample.get("memory_stats") or {}).get("usage")
            return int(cpu or 0), int(memory or 0)

        samples = await asyncio.gather(*(one(c["Id"]) for c in await self._containers(handle)))
        return ResourceUsage(
            cpu_seconds=sum(cpu for cpu, _ in samples) / _SEC,
            memory_bytes=sum(memory for _, memory in samples),
        )

    # --------------------------------------------------------------------------- destroy

    async def _containers(self, handle: SandboxHandle) -> list[dict[str, Any]]:
        return await self._list_containers([f"{LABEL_SANDBOX}={handle.ref}"])

    async def _list_containers(self, labels: Iterable[str]) -> list[dict[str, Any]]:
        found = await self._docker.containers.list(
            all="true", filters=json.dumps({"label": list(labels)})
        )
        return [{"Id": c.id, "Labels": c["Labels"] or {}} for c in found]

    async def destroy(self, handle: SandboxHandle) -> None:
        """Remove everything labelled with this sandbox. Safe to call any number of times."""

        async def remove(container_id: str) -> None:
            try:
                await self._docker.containers.container(container_id).delete(force=True, v=True)
            except DockerError as exc:
                if exc.status not in (404, 409):
                    raise

        containers = await self._containers(handle)
        await asyncio.gather(*(remove(c["Id"]) for c in containers))
        # A network can refuse deletion for a moment while endpoints detach: retry briefly.
        for attempt in range(10):
            networks = await self._docker.networks.list(
                filters={"label": f"{LABEL_SANDBOX}={handle.ref}"}
            )
            if not networks:
                break
            for net in networks:
                try:
                    await (await self._docker.networks.get(net["Id"])).delete()
                except DockerError as exc:
                    if exc.status != 404 and attempt == 9:
                        raise
            await asyncio.sleep(0.2)
        if containers:
            log.info("sandbox.destroyed", sandbox=handle.ref, containers=len(containers))

    async def list_sandboxes(self) -> list[str]:
        """Every sandbox with something left on this host (for the sweeper and leak checks)."""
        refs = {c["Labels"][LABEL_SANDBOX] for c in await self._list_containers([LABEL_MANAGED])}
        networks = await self._docker.networks.list(filters={"label": LABEL_MANAGED})
        refs |= {
            n["Labels"][LABEL_SANDBOX] for n in networks if LABEL_SANDBOX in (n.get("Labels") or {})
        }
        return sorted(refs)

    async def count_resources(self) -> dict[str, int]:
        """Our leftover containers and networks, and every dangling volume on the host.

        Anonymous volumes carry no labels, so volume leaks are counted host-wide: compare
        before and after (the leak script does).
        """
        containers = await self._list_containers([LABEL_MANAGED])
        networks = await self._docker.networks.list(filters={"label": LABEL_MANAGED})
        volumes = await self._docker.volumes.list(filters={"dangling": "true"})
        return {
            "containers": len(containers),
            "networks": len(networks),
            "dangling_volumes": len(volumes.get("Volumes") or []),
        }


def _read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out
