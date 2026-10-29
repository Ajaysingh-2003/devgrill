"""Pure parts of the sandbox layer: metric maths, content cross-checks, spec v1 rules."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from devgrill.domain.spec import Beat, DeployEntry, FaultApply, ProbeTarget, ScenarioSpec, Slo
from devgrill.sandbox.baseapp import BaseAppSpec, MetricDef
from devgrill.sandbox.content import ContentError, load_bundle, render, resolve_params
from devgrill.sandbox.metrics import Scrape, evaluate, parse_text

CONTENT = Path(__file__).resolve().parents[3] / "content"

API_T0 = """
# HELP http_requests_total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",route="/products/{product_id}",status="200"} 100.0
http_requests_total{method="GET",route="/products/{product_id}",status="503"} 0.0
http_request_duration_seconds_bucket{le="0.1",route="/products/{product_id}"} 90.0
http_request_duration_seconds_bucket{le="0.5",route="/products/{product_id}"} 99.0
http_request_duration_seconds_bucket{le="+Inf",route="/products/{product_id}"} 100.0
db_pool_in_use 3.0
"""
API_T1 = """
http_requests_total{method="GET",route="/products/{product_id}",status="200"} 280.0
http_requests_total{method="GET",route="/products/{product_id}",status="503"} 20.0
http_request_duration_seconds_bucket{le="0.1",route="/products/{product_id}"} 190.0
http_request_duration_seconds_bucket{le="0.5",route="/products/{product_id}"} 289.0
http_request_duration_seconds_bucket{le="+Inf",route="/products/{product_id}"} 300.0
db_pool_in_use 7.0
"""


def scrape(t: float, text: str) -> Scrape:
    return Scrape(t, {"api": parse_text(text)})


def metric(**kw: object) -> MetricDef:
    return MetricDef.model_validate({"job": "api", **kw})


def test_parse_text_reads_labels_and_skips_comments() -> None:
    samples = parse_text('# HELP x\nx_total{a="1",b="two \\"q\\""} 4.5 1700000000\nbad line\n')
    assert len(samples) == 1
    assert samples[0].labels == {"a": "1", "b": 'two "q"'}
    assert samples[0].value == 4.5


def test_gauge_rate_ratio_quantile() -> None:
    prev, cur = scrape(0, API_T0), scrape(10, API_T1)
    assert evaluate(metric(type="gauge", metric="db_pool_in_use"), prev, cur) == 7.0
    assert evaluate(metric(type="rate", metric="http_requests_total"), prev, cur) == 20.0
    ratio = metric(type="ratio", metric="http_requests_total", labels={"status": "5.."})
    assert evaluate(ratio, prev, cur) == pytest.approx(0.1)
    p99 = metric(
        type="quantile",
        metric="http_request_duration_seconds",
        q=0.99,
        labels={"route": "/products/\\{product_id\\}"},
        scale=1000,
    )
    # 200 new observations: 100 under 0.1 s, 90 more under 0.5 s, 10 above. p99 is in +Inf.
    assert evaluate(p99, prev, cur) == pytest.approx(500.0)
    p50 = p99.model_copy(update={"q": 0.5})
    assert evaluate(p50, prev, cur) == pytest.approx(100.0)


def test_unknowable_values_are_none_not_zero() -> None:
    quiet = scrape(0, API_T0)
    ratio = metric(type="ratio", metric="http_requests_total", labels={"status": "5.."})
    assert evaluate(ratio, None, quiet) is None  # first scrape
    assert evaluate(ratio, quiet, scrape(10, API_T0)) is None  # no traffic in between
    restarted = scrape(10, API_T0.replace("100.0", "5.0"))
    assert evaluate(metric(type="rate", metric="http_requests_total"), quiet, restarted) is None


def test_quantile_needs_q() -> None:
    with pytest.raises(ValidationError):
        metric(type="quantile", metric="x")
    with pytest.raises(ValidationError):
        metric(type="gauge", metric="x", q=0.5)


# ---------------------------------------------------------------------------- content


@pytest.mark.parametrize(
    "slug",
    [
        "ttl-zero",
        "big-sale-meltdown",
        "pool-party",
        "the-3am-table-lock",
        "restarts-every-six-hours",
        "the-index-that-wasnt",
        "orders-stuck-in-the-queue",
    ],
)
def test_playable_scenarios_load_with_their_faults(slug: str) -> None:
    bundle = load_bundle(CONTENT, slug)
    assert bundle.base_app.slug == "shopkart"
    assert set(bundle.faults) == {f.use for f in bundle.scenario.faults}
    assert bundle.scenario.hints is not None
    assert bundle.scenario.probes


def test_fault_params_are_checked() -> None:
    fault = load_bundle(CONTENT, "pool-party").faults["db/pool-exhaustion"].spec
    assert resolve_params(fault, {}) == {"latency_ms": 150}
    with pytest.raises(ContentError, match="unknown params"):
        resolve_params(fault, {"latency": 1})
    with pytest.raises(ContentError, match="must be integer"):
        resolve_params(fault, {"latency_ms": "slow"})


def test_render_refuses_unknown_placeholders() -> None:
    assert render("{{ttl}}s", {"ttl": 0}) == "0s"
    with pytest.raises(ContentError):
        render("{{nope}}", {})


def test_base_app_needs_one_shell_and_no_cycles() -> None:
    base = {
        "schema": "devgrill/base-app@1",
        "slug": "tiny",
        "name": "Tiny",
        "version": 1,
        "slo": {"p99_latency_ms": 500, "error_rate": 0.01},
        "load": {"script": "load/x.js", "target": "http://api:8000"},
    }
    with pytest.raises(ValidationError, match="shell"):
        BaseAppSpec.model_validate({**base, "services": {"api": {"image": "x", "port": 8000}}})
    cyclic = {
        "a": {"image": "x", "depends_on": ["b"], "shell": True},
        "b": {"image": "x", "depends_on": ["a"]},
    }
    with pytest.raises(ValidationError, match="cycle"):
        BaseAppSpec.model_validate({**base, "services": cyclic})


# ---------------------------------------------------------------------------- spec v1


def test_beats_use_when_not_on() -> None:
    assert Beat(persona="arjun", say="hi", when="state:mitigated").when == "state:mitigated"
    with pytest.raises(ValidationError):
        Beat(persona="arjun", say="hi")


def test_only_scripts_detach() -> None:
    assert FaultApply(script="lock.sql", service="db", detach=True).detach
    with pytest.raises(ValidationError):
        FaultApply(env={"A": "1"}, service="api", detach=True)
    with pytest.raises(ValidationError):
        FaultApply(script="run.rb", service="api")


def test_slo_targets_merge_thresholds() -> None:
    slo = Slo(error_rate=0.01, thresholds={"db_qps_product": ProbeTarget(lt=75)})
    assert set(slo.targets()) == {"error_rate", "db_qps_product"}
    assert slo.targets()["error_rate"].holds(0.001)
    assert not slo.targets()["db_qps_product"].holds(80)
    assert not math.isnan(slo.for_s)


def test_fault_deploys_must_be_the_newest(tmp_path: Path) -> None:
    spec = load_bundle(CONTENT, "ttl-zero").scenario.model_dump(by_alias=True)
    spec["deploy_history"] = [
        DeployEntry(
            message="old fault", minutes_before=500, from_fault="cache/ttl-zero"
        ).model_dump(),
        DeployEntry(message="newer plain deploy", minutes_before=5).model_dump(),
    ]
    with pytest.raises(ValidationError, match="newer"):
        ScenarioSpec.model_validate(spec)


def test_stored_specs_read_back() -> None:
    """Versions store model_dump() (field names); the API parses them again."""
    spec = load_bundle(CONTENT, "big-sale-meltdown").scenario
    assert ScenarioSpec.model_validate(spec.model_dump(mode="json")) == spec


def test_charts_must_be_base_app_metrics(tmp_path: Path) -> None:
    import shutil

    root = tmp_path / "content"
    shutil.copytree(CONTENT, root)
    path = root / "scenarios/databases/the-3am-table-lock/scenario.yaml"
    text = path.read_text(encoding="utf-8").replace(
        "\nfaults:\n", "\ncharts: [error_rate, nope_metric]\n\nfaults:\n", 1
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ContentError, match="chart 'nope_metric' is not a shopkart metric"):
        load_bundle(root, "the-3am-table-lock")


def test_deploy_history_names_a_service_with_source(tmp_path: Path) -> None:
    import shutil

    root = tmp_path / "content"
    shutil.copytree(CONTENT, root)
    path = root / "scenarios/queues/orders-stuck-in-the-queue/scenario.yaml"
    text = path.read_text(encoding="utf-8")
    assert "service: worker\n" in text
    path.write_text(text.replace("service: worker\n", "service: redis-db\n", 1), encoding="utf-8")
    with pytest.raises(ContentError, match="'redis-db', which has no source"):
        load_bundle(root, "orders-stuck-in-the-queue")
