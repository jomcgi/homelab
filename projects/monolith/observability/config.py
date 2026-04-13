from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SloConfig:
    target: float
    window_days: int
    query: str | None = None


@dataclass
class MetricConfig:
    key: str
    query: str | None = None
    static: str | None = None
    unit: str | None = None
    format: str | None = None


@dataclass
class SparkConfig:
    query: str


@dataclass
class NodeConfig:
    id: str
    label: str
    tier: str
    description: str
    group: str | None = None
    ingress: bool = False
    slo: SloConfig | None = None
    metrics: list[MetricConfig] = field(default_factory=list)
    spark: SparkConfig | None = None


@dataclass
class GroupConfig:
    id: str
    label: str
    tier: str
    description: str
    children: list[str]
    ingress: bool = False
    slo: SloConfig | None = None


@dataclass
class EdgeConfig:
    source: str
    target: str
    bidi: bool = False


@dataclass
class TopologyConfig:
    cache_ttl: int
    groups: list[GroupConfig]
    nodes: list[NodeConfig]
    edges: list[EdgeConfig]


def _parse_window(window: str) -> int:
    m = re.match(r"^(\d+)d$", window)
    if not m:
        raise ValueError(f"Invalid window format: {window!r} (expected e.g. '30d')")
    return int(m.group(1))


def _parse_slo(raw: dict | None) -> SloConfig | None:
    if raw is None:
        return None
    return SloConfig(
        target=raw["target"],
        window_days=_parse_window(raw["window"]),
        query=raw.get("query"),
    )


def _parse_metric(raw: dict) -> MetricConfig:
    return MetricConfig(
        key=raw["key"],
        query=raw.get("query"),
        static=raw.get("static"),
        unit=raw.get("unit"),
        format=raw.get("format"),
    )


def load_config(path: Path) -> TopologyConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)

    groups = []
    for g in raw.get("groups", []):
        groups.append(
            GroupConfig(
                id=g["id"],
                label=g["label"],
                tier=g["tier"],
                description=g["description"],
                children=g["children"],
                ingress=g.get("ingress", False),
                slo=_parse_slo(g.get("slo")),
            )
        )

    nodes = []
    for n in raw.get("nodes", []):
        spark_raw = n.get("spark")
        spark = SparkConfig(query=spark_raw["query"]) if spark_raw else None
        nodes.append(
            NodeConfig(
                id=n["id"],
                label=n["label"],
                tier=n["tier"],
                description=n["description"],
                group=n.get("group"),
                ingress=n.get("ingress", False),
                slo=_parse_slo(n.get("slo")),
                metrics=[_parse_metric(m) for m in n.get("metrics", [])],
                spark=spark,
            )
        )

    edges = []
    for e in raw.get("edges", []):
        edges.append(
            EdgeConfig(
                source=e["from"],
                target=e["to"],
                bidi=e.get("bidi", False),
            )
        )

    return TopologyConfig(
        cache_ttl=raw.get("cache_ttl", 900),
        groups=groups,
        nodes=nodes,
        edges=edges,
    )
