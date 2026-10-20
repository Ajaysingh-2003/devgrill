"""`content/base-apps/<slug>/base-app.yaml`: the services a base app is made of (ADR 012)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from devgrill.domain.spec import RelPath, ServiceName, Slug


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _absolute_path(value: str) -> str:
    if not re.fullmatch(r"/[A-Za-z0-9_./-]{1,200}", value) or ".." in value.split("/"):
        raise ValueError(f"{value!r} is not an absolute container path")
    return value


ContainerPath = Annotated[str, AfterValidator(_absolute_path)]


class SourceSpec(_Strict):
    """A patchable service: its build folder is a git repo in the shell (/workspace/<service>);
    deploying copies `paths` from there to `dest` and restarts the service."""

    dest: ContainerPath
    paths: list[RelPath] = Field(min_length=1)
    #: KEY=value file in the repo; `env` faults on this service edit it (config-as-code).
    config_file: RelPath | None = None


class SqlSpec(_Strict):
    user: str = Field(pattern=r"^[a-z_][a-z0-9_]{0,30}$")
    database: str = Field(pattern=r"^[a-z_][a-z0-9_]{0,30}$")


class ToxiproxySpec(_Strict):
    admin_port: int = Field(ge=1, le=65535, default=8474)


class ServiceSpec(_Strict):
    image: str | None = Field(default=None, max_length=200)
    build: RelPath | None = None
    env: dict[str, str] = Field(default_factory=dict)
    command: list[str] | None = None
    #: Files copied into the container before it starts: {container path: base-app path}.
    files: dict[ContainerPath, RelPath] = Field(default_factory=dict)
    #: Extra DNS names on the sandbox network (the datastores are reached through toxiproxy).
    aliases: list[ServiceName] = Field(default_factory=list)
    source: SourceSpec | None = None
    #: This service runs SQL scripts (data faults) with psql.
    sql: SqlSpec | None = None
    #: This service is the Toxiproxy (toxic faults, chaos steps).
    toxiproxy: ToxiproxySpec | None = None
    #: This service is the Redis-protocol cache (chaos steps: del_key, flush_cache).
    cache: bool = False
    #: The player's shell. Exactly one service has it.
    shell: bool = False
    #: The HTTP port the app serves (the load target) and its metrics path.
    port: int | None = Field(default=None, ge=1, le=65535)
    metrics: str | None = Field(default=None, pattern=r"^/[A-Za-z0-9_/-]*$")
    #: Exporters and workers: metrics served on this port at /metrics.
    metrics_port: int | None = Field(default=None, ge=1, le=65535)
    healthcheck: list[str] | None = None
    depends_on: list[ServiceName] = Field(default_factory=list)
    cpus: float = Field(gt=0, le=8, default=0.5)
    memory_mb: int = Field(ge=32, le=8192, default=256)

    @model_validator(mode="after")
    def _image_or_build(self) -> ServiceSpec:
        if bool(self.image) == bool(self.build):
            raise ValueError("a service has exactly one of: image, build")
        if self.source and not self.build:
            raise ValueError("a patchable service (source) must be built from a folder")
        return self

    @property
    def scrape_path(self) -> str | None:
        """Where its Prometheus metrics are, as host:port/path relative to the service name."""
        if self.port and self.metrics:
            return f"{self.port}{self.metrics}"
        if self.metrics_port:
            return f"{self.metrics_port}/metrics"
        return None


class MetricDef(_Strict):
    """A named metric computed from scrapes.

    - gauge: the summed value of `metric` (matching labels) in the latest scrape.
    - rate: per-second increase of a counter between two scrapes.
    - ratio: rate of `metric` matching `labels` / rate of `metric` (all label values).
    - quantile: `q` quantile of a histogram's observations between two scrapes.
    """

    type: Literal["gauge", "rate", "ratio", "quantile"]
    job: ServiceName
    metric: str = Field(pattern=r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
    labels: dict[str, str] = Field(default_factory=dict)
    q: float | None = Field(default=None, gt=0, lt=1)
    scale: float = 1.0

    @model_validator(mode="after")
    def _shape(self) -> MetricDef:
        if (self.type == "quantile") != (self.q is not None):
            raise ValueError("q is required for quantile metrics and only for them")
        for pattern in self.labels.values():
            re.compile(pattern)
        return self


class SloSpec(_Strict):
    p99_latency_ms: float = Field(gt=0)
    error_rate: float = Field(ge=0, le=1)


class LoadSpec(_Strict):
    script: RelPath
    target: str = Field(pattern=r"^http://[a-z][a-z0-9-]*:\d+$")


class BaseAppSpec(_Strict):
    schema_: Literal["devgrill/base-app@1"] = Field(alias="schema")
    slug: Slug
    name: str = Field(max_length=60)
    version: int = Field(ge=1)
    services: dict[ServiceName, ServiceSpec]
    slo: SloSpec
    load: LoadSpec
    metrics: dict[str, MetricDef] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _references_resolve(self) -> BaseAppSpec:
        for name, service in self.services.items():
            for dep in service.depends_on:
                if dep not in self.services:
                    raise ValueError(f"{name} depends on unknown service {dep}")
        shells = [n for n, s in self.services.items() if s.shell]
        if len(shells) != 1:
            raise ValueError("a base app needs exactly one shell service (the player's terminal)")
        for key, metric in self.metrics.items():
            job = self.services.get(metric.job)
            if job is None or job.scrape_path is None:
                raise ValueError(f"metric {key}: job {metric.job} is not a scraped service")
        self.ordered()  # raises on a dependency cycle
        return self

    @property
    def shell_service(self) -> str:
        return next(n for n, s in self.services.items() if s.shell)

    @property
    def toxiproxy_service(self) -> str | None:
        return next((n for n, s in self.services.items() if s.toxiproxy), None)

    @property
    def cache_service(self) -> str | None:
        return next((n for n, s in self.services.items() if s.cache), None)

    def image_for(self, service: str) -> str:
        spec = self.services[service]
        return spec.image or f"devgrill/{self.slug}-{service}:{self.version}"

    def ordered(self) -> list[str]:
        """Services in dependency order (stable topological sort)."""
        done: list[str] = []
        remaining = dict(self.services)
        while remaining:
            ready = [n for n, s in remaining.items() if all(d in done for d in s.depends_on)]
            if not ready:
                raise ValueError("dependency cycle between services")
            done.extend(ready)
            for n in ready:
                remaining.pop(n)
        return done


def load_base_app(content_root: Path, slug: str) -> tuple[Path, BaseAppSpec]:
    folder = content_root / "base-apps" / slug
    path = folder / "base-app.yaml"
    spec = BaseAppSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if spec.slug != slug:
        raise ValueError(f"{path}: slug {spec.slug!r} does not match folder {slug!r}")
    for name, service in spec.services.items():
        for rel in [*service.files.values(), *([service.build] if service.build else [])]:
            if not (folder / rel).exists():
                raise ValueError(f"{path}: {name} refers to missing {rel}")
    if not (folder / spec.load.script).is_file():
        raise ValueError(f"{path}: load script {spec.load.script} is missing")
    return folder, spec
