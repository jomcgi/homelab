import textwrap

import pytest

from observability.config import load_config, TopologyConfig


MINIMAL_YAML = textwrap.dedent("""\
    cache_ttl: 900

    groups:
      - id: mygroup
        label: MY GROUP
        tier: critical
        description: "test group"
        children: [child_a]
        slo:
          target: 99.0
          window: 30d

    nodes:
      - id: ext
        label: EXTERNAL
        tier: ingress
        description: "external"
        metrics:
          - key: clients
            static: "a, b"

      - id: child_a
        label: CHILD A
        tier: critical
        group: mygroup
        description: "a child"
        slo:
          target: 99.0
          window: 30d
          query: "SELECT 100 AS value"
        metrics:
          - key: rps
            query: "SELECT 1.5 AS value"

    edges:
      - from: ext
        to: child_a
""")


class TestLoadConfig:
    def test_loads_minimal_yaml(self, tmp_path):
        p = tmp_path / "topology.yaml"
        p.write_text(MINIMAL_YAML)
        cfg = load_config(p)
        assert isinstance(cfg, TopologyConfig)
        assert cfg.cache_ttl == 900

    def test_parses_groups(self, tmp_path):
        p = tmp_path / "topology.yaml"
        p.write_text(MINIMAL_YAML)
        cfg = load_config(p)
        assert len(cfg.groups) == 1
        g = cfg.groups[0]
        assert g.id == "mygroup"
        assert g.children == ["child_a"]
        assert g.slo.target == 99.0

    def test_parses_nodes(self, tmp_path):
        p = tmp_path / "topology.yaml"
        p.write_text(MINIMAL_YAML)
        cfg = load_config(p)
        assert len(cfg.nodes) == 2
        ext = next(n for n in cfg.nodes if n.id == "ext")
        assert ext.slo is None
        assert ext.metrics[0].static == "a, b"

    def test_node_with_slo_query(self, tmp_path):
        p = tmp_path / "topology.yaml"
        p.write_text(MINIMAL_YAML)
        cfg = load_config(p)
        child = next(n for n in cfg.nodes if n.id == "child_a")
        assert child.slo is not None
        assert child.slo.query == "SELECT 100 AS value"
        assert child.group == "mygroup"

    def test_parses_edges(self, tmp_path):
        p = tmp_path / "topology.yaml"
        p.write_text(MINIMAL_YAML)
        cfg = load_config(p)
        assert len(cfg.edges) == 1
        assert cfg.edges[0].source == "ext"
        assert cfg.edges[0].target == "child_a"

    def test_node_slo_window_parsed_to_days(self, tmp_path):
        p = tmp_path / "topology.yaml"
        p.write_text(MINIMAL_YAML)
        cfg = load_config(p)
        child = next(n for n in cfg.nodes if n.id == "child_a")
        assert child.slo.window_days == 30
