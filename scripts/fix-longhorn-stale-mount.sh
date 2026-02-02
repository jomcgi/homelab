#!/usr/bin/env bash
# fix-longhorn-stale-mount.sh - Fix stale Longhorn volume mounts
#
# This script resolves the "already mounted or mount point busy" error that can occur
# when a Longhorn volume's mount point becomes stale after a node restart or pod eviction.
#
# Error pattern:
#   MountVolume.MountDevice failed for volume "pvc-xxx" : rpc error: code = Internal desc = mount failed
#   mount: /var/lib/kubelet/plugins/kubernetes.io/csi/driver.longhorn.io/.../globalmount:
#   /dev/longhorn/pvc-xxx already mounted or mount point busy
#
# Root cause: The VolumeAttachment shows attached=true, but the actual mount state on the
# node is inconsistent. Deleting the VolumeAttachment forces Longhorn to perform a clean
# detach/re-attach cycle.
#
# Usage:
#   ./scripts/fix-longhorn-stale-mount.sh <pvc-name> <namespace>
#   ./scripts/fix-longhorn-stale-mount.sh data-seaweedfs-volume-0 seaweedfs

set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <pvc-name> <namespace>"
    echo "Example: $0 data-seaweedfs-volume-0 seaweedfs"
    exit 1
fi

PVC_NAME="$1"
NAMESPACE="$2"

echo "Looking up PV for PVC ${PVC_NAME} in namespace ${NAMESPACE}..."
PV_NAME=$(kubectl get pvc "${PVC_NAME}" -n "${NAMESPACE}" -o jsonpath='{.spec.volumeName}')

if [[ -z "${PV_NAME}" ]]; then
    echo "ERROR: Could not find PV for PVC ${PVC_NAME}"
    exit 1
fi

echo "Found PV: ${PV_NAME}"

echo "Looking up VolumeAttachment for PV ${PV_NAME}..."
VA_NAME=$(kubectl get volumeattachment -o json | jq -r ".items[] | select(.spec.source.persistentVolumeName == \"${PV_NAME}\") | .metadata.name")

if [[ -z "${VA_NAME}" ]]; then
    echo "ERROR: Could not find VolumeAttachment for PV ${PV_NAME}"
    exit 1
fi

echo "Found VolumeAttachment: ${VA_NAME}"

# Show current state
echo ""
echo "Current VolumeAttachment state:"
kubectl get volumeattachment "${VA_NAME}" -o wide

echo ""
echo "Current pod state:"
kubectl get pods -n "${NAMESPACE}" -l "app.kubernetes.io/name=seaweedfs,app.kubernetes.io/component=volume" -o wide || true

echo ""
echo "This will delete the VolumeAttachment to force a clean re-attach cycle."
echo "The pod will automatically recover once the volume is re-attached."
read -p "Continue? [y/N] " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo "Deleting VolumeAttachment ${VA_NAME}..."
kubectl delete volumeattachment "${VA_NAME}"

echo ""
echo "VolumeAttachment deleted. Waiting for pod to recover..."
echo "Watch progress with: kubectl get pods -n ${NAMESPACE} -w"
