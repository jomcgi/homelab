#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests",
#     "rich",
# ]
# ///
"""TTYD Session Manager Test Script

This script:
1. Builds and pushes backend API and worker images
2. Updates the backend deployment
3. Creates a test session
4. Waits for the session pod to be ready
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def run_command(
    cmd: list[str], capture_output: bool = True, timeout: int = 300
) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result
    except subprocess.TimeoutExpired:
        console.print(f"[red]✗ Command timed out after {timeout}s: {' '.join(cmd)}")
        sys.exit(1)


def build_images():
    """Build both backend and worker images."""
    console.print("🔨 [cyan]Building both images...")
    result = run_command(
        [
            "bazel",
            "build",
            "--stamp",
            "//charts/ttyd-session-manager/backend:image",
            "//charts/ttyd-session-manager/backend:ttyd_worker_image",
        ],
        capture_output=False,
    )
    if result.returncode != 0:
        console.print("[red]✗ Build failed")
        sys.exit(1)
    console.print("[green]✓ Both images built successfully\n")


def push_image(target: str, image_pattern: str) -> str:
    """Push an image and extract its tag."""
    console.print(f"📤 [cyan]Pushing {target}...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Pushing {target}...", total=None)

        result = run_command(
            ["bazel", "run", "--stamp", target],
            timeout=600,
        )

        progress.update(task, completed=True)

    if result.returncode != 0:
        console.print(f"[red]✗ Push failed for {target}")
        console.print(f"[dim]{result.stderr}")
        sys.exit(1)

    # Extract tag from output
    # The output contains a line like: "ghcr.io/.../backend:2025.11.10.02.34.14-33a149b: digest: sha256:..."
    # We need to extract the version tag (the part between : and the next :)
    full_output = result.stdout + result.stderr

    # Match the full image reference with tag
    # Pattern: image_pattern:TAG where TAG is version-like (YYYY.MM.DD.HH.MM.SS-hash)
    match = re.search(rf"{image_pattern}:([\d.]+-[\w]+)", full_output, re.MULTILINE)

    if not match:
        console.print(f"[red]✗ Failed to extract image tag from push output")
        console.print(f"[dim]Pattern: {image_pattern}:([\\d.]+-[\\w]+)")
        # Show the relevant part
        idx = full_output.find(image_pattern)
        if idx >= 0:
            console.print(f"[dim]Found pattern at index {idx}, context:")
            console.print(repr(full_output[idx : idx + 200]))
        else:
            console.print(f"[dim]Pattern '{image_pattern}' not found in output")
            console.print(f"[dim]Full output (last 1000 chars):\n{full_output[-1000:]}")
        sys.exit(1)

    tag = match.group(1)
    console.print(f"[green]✓ Pushed with tag: {tag}")
    return tag


def update_backend_deployment(image_tag: str):
    """Update the backend deployment with new image."""
    console.print(f"\n🔄 [cyan]Updating backend deployment...")

    image = f"ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/backend:{image_tag}"
    result = run_command(
        [
            "kubectl",
            "set",
            "image",
            "deployment/ttyd-session-manager",
            f"api-server={image}",
            "-n",
            "ttyd-sessions",
        ]
    )

    if result.returncode != 0:
        console.print(f"[red]✗ Failed to update deployment")
        console.print(f"[dim]{result.stderr}")
        sys.exit(1)

    console.print("[green]✓ Deployment updated")

    # Wait for rollout
    console.print("⏳ [cyan]Waiting for rollout...")
    result = run_command(
        [
            "kubectl",
            "rollout",
            "status",
            "deployment/ttyd-session-manager",
            "-n",
            "ttyd-sessions",
            "--timeout=300s",
        ],
        capture_output=False,
        timeout=320,
    )

    if result.returncode != 0:
        console.print("[red]✗ Rollout failed")
        sys.exit(1)

    console.print("[green]✓ Rollout complete\n")


def create_session(api_url: str, session_name: str, worker_tag: str) -> dict:
    """Create a new session via API."""
    console.print(
        f"🚀 [cyan]Creating session '{session_name}' with worker tag {worker_tag}..."
    )

    try:
        response = requests.post(
            f"{api_url}/api/sessions",
            json={"display_name": session_name, "image_tag": worker_tag},
            timeout=30,  # Increased timeout for session creation
        )
        response.raise_for_status()
        session = response.json()

        console.print("[green]✓ Session created successfully")
        console.print(f"  [dim]Session ID: {session['id']}")
        console.print(f"  [dim]Pod Name: ttyd-session-{session['id']}")

        return session
    except requests.RequestException as e:
        console.print(f"[red]✗ Failed to create session: {e}")
        sys.exit(1)


def wait_for_pod_ready(
    pod_name: str, namespace: str = "ttyd-sessions", timeout: int = 120
):
    """Wait for pod to be ready."""
    console.print(f"⏳ [cyan]Waiting for pod {pod_name} to be ready...")

    result = run_command(
        [
            "kubectl",
            "wait",
            "--for=condition=ready",
            f"pod/{pod_name}",
            "-n",
            namespace,
            f"--timeout={timeout}s",
        ],
        timeout=timeout + 10,
    )

    if result.returncode != 0:
        console.print(f"[red]✗ Pod did not become ready in {timeout}s")
        console.print("\n[yellow]Checking pod status:")
        run_command(
            ["kubectl", "describe", f"pod/{pod_name}", "-n", namespace],
            capture_output=False,
        )
        sys.exit(1)

    console.print("[green]✓ Pod is ready\n")


def setup_port_forward(
    namespace: str = "ttyd-sessions", local_port: int = 8083
) -> subprocess.Popen:
    """Set up port-forward to session manager API."""
    console.print(
        f"🔌 [cyan]Setting up port-forward to session manager API on port {local_port}..."
    )

    proc = subprocess.Popen(
        [
            "kubectl",
            "port-forward",
            "-n",
            namespace,
            "deployment/ttyd-session-manager",
            f"{local_port}:8080",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for port-forward to be ready
    time.sleep(3)

    # Check if port is listening
    result = run_command(["lsof", "-i", f":{local_port}"], capture_output=True)
    if result.returncode != 0:
        console.print(f"[red]✗ Port-forward failed (port {local_port} not listening)")
        proc.kill()
        sys.exit(1)

    console.print(f"[green]✓ Port-forward active (PID: {proc.pid})\n")
    return proc


def main():
    parser = argparse.ArgumentParser(description="Test TTYD Session Manager")
    parser.add_argument(
        "session_name", nargs="?", default="test-session", help="Session display name"
    )
    parser.add_argument(
        "--skip-build", action="store_true", help="Skip build and push steps"
    )
    parser.add_argument(
        "--port", type=int, default=8083, help="Local port for API (default: 8083)"
    )
    args = parser.parse_args()

    console.print("\n[bold cyan]====================================")
    console.print("[bold cyan]TTYD Session Manager Test Script")
    console.print("[bold cyan]====================================\n")

    pf_proc = None
    api_url = f"http://localhost:{args.port}"

    try:
        if not args.skip_build:
            # Build images
            build_images()

            # Push images
            # Image paths in registry: ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/backend:TAG
            # and ghcr.io/jomcgi/homelab/charts/ttyd-session-manager/ttyd-worker:TAG
            backend_tag = push_image(
                "//charts/ttyd-session-manager/backend:image.push",
                "manager/backend",  # Match end of registry path to be unique
            )

            worker_tag = push_image(
                "//charts/ttyd-session-manager/backend:ttyd_worker_image.push",
                "manager/ttyd-worker",  # Match end of registry path to be unique
            )

            # Update backend deployment
            update_backend_deployment(backend_tag)

            # Setup port-forward to new backend pod
            pf_proc = setup_port_forward(local_port=args.port)
        else:
            console.print("[yellow]⏭️  Skipping build steps")
            # Use latest tag from git
            result = run_command(["git", "describe", "--tags", "--always", "--dirty"])
            worker_tag = f"2025.11.09.{result.stdout.strip()}"

            # Setup port-forward
            pf_proc = setup_port_forward(local_port=args.port)

        # Create session
        session = create_session(api_url, args.session_name, worker_tag)
        pod_name = f"ttyd-session-{session['id']}"

        # Wait for pod
        wait_for_pod_ready(pod_name)

        # Success!
        console.print("[bold green]====================================")
        console.print(f"[bold green]✅ Success! Terminal ready at:")
        console.print(
            f"[bold green]   https://test.jomcgi.dev/sessions/{session['id']}"
        )
        console.print("[bold green]====================================\n")

        console.print("[dim]Session Details:")
        console.print(f"[dim]  - Session ID: {session['id']}")
        console.print(f"[dim]  - Session Name: {args.session_name}")
        console.print(f"[dim]  - Pod Name: {pod_name}")
        console.print(f"[dim]  - Worker Tag: {worker_tag}\n")

    finally:
        # Cleanup port-forward
        if pf_proc:
            pf_proc.kill()


if __name__ == "__main__":
    main()
