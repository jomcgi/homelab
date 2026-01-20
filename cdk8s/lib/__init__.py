"""Shared cdk8s constructs for homelab."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ResourceRequirements:
    """Container resource requirements."""

    cpu_limit: str = "100m"
    memory_limit: str = "64Mi"
    cpu_request: str = "10m"
    memory_request: str = "32Mi"


@dataclass
class Labels:
    """Standard Kubernetes labels."""

    name: str
    instance: str
    version: str = "1.0"
    component: Optional[str] = None
    chart: Optional[str] = None
    managed_by: str = "cdk8s"

    def common(self) -> dict:
        """Return common labels for metadata."""
        labels = {
            "app.kubernetes.io/name": self.name,
            "app.kubernetes.io/instance": self.instance,
            "app.kubernetes.io/version": self.version,
            "app.kubernetes.io/managed-by": self.managed_by,
        }
        if self.chart:
            labels["helm.sh/chart"] = self.chart
        if self.component:
            labels["app.kubernetes.io/component"] = self.component
        return labels

    def selector(self) -> dict:
        """Return selector labels."""
        labels = {
            "app.kubernetes.io/name": self.name,
            "app.kubernetes.io/instance": self.instance,
        }
        if self.component:
            labels["app.kubernetes.io/component"] = self.component
        return labels
