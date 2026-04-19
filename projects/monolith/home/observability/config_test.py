from home.observability.config import TopologyConfig
from home.observability.topology_config import TOPOLOGY


class TestTopologyConfig:
    def test_is_topology_config(self):
        assert isinstance(TOPOLOGY, TopologyConfig)

    def test_cache_ttl(self):
        assert TOPOLOGY.cache_ttl == 900

    def test_has_groups(self):
        assert len(TOPOLOGY.groups) == 3
        ids = [g.id for g in TOPOLOGY.groups]
        assert "monolith" in ids
        assert "context-forge" in ids
        assert "cluster" in ids

    def test_group_children_reference_valid_nodes(self):
        node_ids = {n.id for n in TOPOLOGY.nodes}
        for g in TOPOLOGY.groups:
            for child in g.children:
                assert child in node_ids, (
                    f"group {g.id} references unknown node {child}"
                )

    def test_has_nodes(self):
        assert len(TOPOLOGY.nodes) == 21

    def test_external_nodes_have_no_slo(self):
        ext = next(n for n in TOPOLOGY.nodes if n.id == "external")
        assert ext.slo is None
        assert ext.metrics[0].static == "webpage, claude, cli"

    def test_slo_nodes_have_queries(self):
        for n in TOPOLOGY.nodes:
            if n.slo is not None:
                assert n.slo.query is not None, f"node {n.id} has SLO but no query"
                assert n.slo.target == 98.0
                assert n.slo.window_days == 30

    def test_edges(self):
        assert len(TOPOLOGY.edges) == 15

    def test_edge_references_valid_nodes(self):
        node_ids = {n.id for n in TOPOLOGY.nodes}
        for e in TOPOLOGY.edges:
            assert e.source in node_ids, f"edge source {e.source} not in nodes"
            assert e.target in node_ids, f"edge target {e.target} not in nodes"

    def test_node_groups_reference_valid_groups(self):
        group_ids = {g.id for g in TOPOLOGY.groups}
        for n in TOPOLOGY.nodes:
            if n.group is not None:
                assert n.group in group_ids, (
                    f"node {n.id} references unknown group {n.group}"
                )
