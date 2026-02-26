#!/usr/bin/env python3
"""cdk8s chart for cloudflare-operator-test.

This is a cdk8s equivalent of charts/cloudflare-operator-test/.
Run with: cdk8s synth
"""

import sys

sys.path.insert(0, str(__file__).rsplit("/", 2)[0])  # Add cdk8s/ to path

from cdk8s import App, Chart
from constructs import Construct

from imports import k8s
from lib import Labels, ResourceRequirements


class SecureDeployment(Construct):
    """Deployment with security best practices baked in."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        name: str,
        image: str,
        port: int,
        labels: Labels,
        args: list[str] | None = None,
        replicas: int = 1,
        resources: ResourceRequirements | None = None,
        health_path: str = "/",
    ):
        super().__init__(scope, id)

        if resources is None:
            resources = ResourceRequirements()

        k8s.KubeDeployment(
            self,
            "deployment",
            metadata=k8s.ObjectMeta(
                name=name,
                labels=labels.common(),
            ),
            spec=k8s.DeploymentSpec(
                replicas=replicas,
                selector=k8s.LabelSelector(match_labels=labels.selector()),
                template=k8s.PodTemplateSpec(
                    metadata=k8s.ObjectMeta(labels=labels.selector()),
                    spec=k8s.PodSpec(
                        security_context=k8s.PodSecurityContext(
                            run_as_non_root=True,
                            run_as_user=65534,
                            fs_group=65534,
                            seccomp_profile=k8s.SeccompProfile(type="RuntimeDefault"),
                        ),
                        containers=[
                            k8s.Container(
                                name="http-echo",
                                image=image,
                                image_pull_policy="IfNotPresent",
                                args=args or [],
                                ports=[
                                    k8s.ContainerPort(
                                        name="http",
                                        container_port=port,
                                        protocol="TCP",
                                    )
                                ],
                                liveness_probe=k8s.Probe(
                                    http_get=k8s.HttpGetAction(
                                        path=health_path,
                                        port=k8s.IntOrString.from_string("http"),
                                    ),
                                    initial_delay_seconds=5,
                                    period_seconds=10,
                                ),
                                readiness_probe=k8s.Probe(
                                    http_get=k8s.HttpGetAction(
                                        path=health_path,
                                        port=k8s.IntOrString.from_string("http"),
                                    ),
                                    initial_delay_seconds=5,
                                    period_seconds=5,
                                ),
                                resources=k8s.ResourceRequirements(
                                    limits={
                                        "cpu": k8s.Quantity.from_string(
                                            resources.cpu_limit
                                        ),
                                        "memory": k8s.Quantity.from_string(
                                            resources.memory_limit
                                        ),
                                    },
                                    requests={
                                        "cpu": k8s.Quantity.from_string(
                                            resources.cpu_request
                                        ),
                                        "memory": k8s.Quantity.from_string(
                                            resources.memory_request
                                        ),
                                    },
                                ),
                                security_context=k8s.SecurityContext(
                                    allow_privilege_escalation=False,
                                    read_only_root_filesystem=True,
                                    run_as_non_root=True,
                                    capabilities=k8s.Capabilities(drop=["ALL"]),
                                    seccomp_profile=k8s.SeccompProfile(
                                        type="RuntimeDefault"
                                    ),
                                ),
                            )
                        ],
                    ),
                ),
            ),
        )


class ClusterIPService(Construct):
    """ClusterIP Service with optional Cloudflare operator annotations."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        name: str,
        labels: Labels,
        target_port: str = "http",
        port: int = 80,
        cloudflare_hostname: str | None = None,
        cloudflare_zero_trust_enabled: bool | None = None,
        cloudflare_zero_trust_policy: str | None = None,
    ):
        super().__init__(scope, id)

        annotations = {}
        if cloudflare_hostname:
            annotations["cloudflare.ingress.hostname"] = cloudflare_hostname
        if cloudflare_zero_trust_enabled is not None:
            annotations["cloudflare.zero-trust.enabled"] = str(
                cloudflare_zero_trust_enabled
            ).lower()
        if cloudflare_zero_trust_policy:
            annotations["cloudflare.zero-trust.policy"] = cloudflare_zero_trust_policy

        k8s.KubeService(
            self,
            "service",
            metadata=k8s.ObjectMeta(
                name=name,
                labels=labels.common(),
                annotations=annotations if annotations else None,
            ),
            spec=k8s.ServiceSpec(
                type="ClusterIP",
                ports=[
                    k8s.ServicePort(
                        port=port,
                        target_port=k8s.IntOrString.from_string(target_port),
                        protocol="TCP",
                        name="http",
                    )
                ],
                selector=labels.selector(),
            ),
        )


class CloudflareOperatorTestChart(Chart):
    """Test application for validating Cloudflare operator annotations.

    Creates two deployments:
    - noauth: Public service (no Zero Trust)
    - auth: Protected service (Zero Trust with joe-only policy)
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        release_name: str = "cf-test",
        chart_name: str = "cloudflare-operator-test",
        chart_version: str = "0.1.0",
        app_version: str = "1.0",
        image_repository: str = "hashicorp/http-echo",
        image_tag: str = "1.0",
        # noauth service config
        noauth_enabled: bool = True,
        noauth_hostname: str = "cf-noauth-test.jomcgi.dev",
        noauth_replicas: int = 1,
        noauth_text: str = "Hello from public service (no auth required)",
        noauth_port: int = 5678,
        # auth service config
        auth_enabled: bool = True,
        auth_hostname: str = "cf-auth-test.jomcgi.dev",
        auth_policy: str = "joe-only",
        auth_replicas: int = 1,
        auth_text: str = "Hello from protected service (Zero Trust enabled)",
        auth_port: int = 5678,
    ):
        super().__init__(scope, id)

        fullname = f"{release_name}-{chart_name}"
        image = f"{image_repository}:{image_tag}"
        chart_label = f"{chart_name}-{chart_version}"

        resources = ResourceRequirements(
            cpu_limit="100m",
            memory_limit="64Mi",
            cpu_request="10m",
            memory_request="32Mi",
        )

        # noauth deployment and service
        if noauth_enabled:
            noauth_labels = Labels(
                name=chart_name,
                instance=release_name,
                version=app_version,
                component="noauth",
                chart=chart_label,
                managed_by="Helm",  # Match Helm output for comparison
            )

            SecureDeployment(
                self,
                "noauth-deployment",
                name=f"{fullname}-noauth",
                image=image,
                port=noauth_port,
                labels=noauth_labels,
                args=[f"-text={noauth_text}", f"-listen=:{noauth_port}"],
                replicas=noauth_replicas,
                resources=resources,
            )

            ClusterIPService(
                self,
                "noauth-service",
                name=f"{fullname}-noauth",
                labels=noauth_labels,
                cloudflare_hostname=noauth_hostname,
                cloudflare_zero_trust_enabled=False,
            )

        # auth deployment and service
        if auth_enabled:
            auth_labels = Labels(
                name=chart_name,
                instance=release_name,
                version=app_version,
                component="auth",
                chart=chart_label,
                managed_by="Helm",  # Match Helm output for comparison
            )

            SecureDeployment(
                self,
                "auth-deployment",
                name=f"{fullname}-auth",
                image=image,
                port=auth_port,
                labels=auth_labels,
                args=[f"-text={auth_text}", f"-listen=:{auth_port}"],
                replicas=auth_replicas,
                resources=resources,
            )

            ClusterIPService(
                self,
                "auth-service",
                name=f"{fullname}-auth",
                labels=auth_labels,
                cloudflare_hostname=auth_hostname,
                cloudflare_zero_trust_policy=auth_policy,
            )


app = App()
CloudflareOperatorTestChart(app, "cloudflare-operator-test")
app.synth()
