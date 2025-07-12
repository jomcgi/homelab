package controller

import (
	"context"
	"fmt"
	"os"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/util/intstr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/log"

	cfapi "github.com/jomcgi/homelab/operators/cloudflare/internal/cloudflare"
)

type TunnelReconciler struct {
	client.Client
	Scheme           *runtime.Scheme
	CloudflareClient *cfapi.Client
}

func (r *TunnelReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := log.FromContext(ctx)

	// For now, this is a placeholder controller that demonstrates
	// how tunnels would be managed
	log.Info("Reconciling Tunnel", "name", req.Name, "namespace", req.Namespace)

	// Get account ID from environment
	accountID := os.Getenv("CLOUDFLARE_ACCOUNT_ID")
	if accountID == "" {
		return ctrl.Result{}, fmt.Errorf("CLOUDFLARE_ACCOUNT_ID environment variable is required")
	}

	// In a real implementation, we would:
	// 1. Get the Tunnel CR
	// 2. Create/update the Cloudflare tunnel
	// 3. Create the deployment and associated resources
	// 4. Update the CR status

	log.Info("Would create Cloudflare tunnel", "accountID", accountID)

	return ctrl.Result{RequeueAfter: time.Minute * 10}, nil
}

func (r *TunnelReconciler) createTunnel(ctx context.Context, name string) error {
	log := log.FromContext(ctx)
	
	// TODO: Implement tunnel creation with v3 SDK
	log.Info("📋 Tunnel creation with v3 SDK - coming soon!", "tunnel", name)
	
	return nil
}

func (r *TunnelReconciler) createTunnelDeployment(ctx context.Context, tunnelName, tunnelID, tunnelSecret string, namespace string, replicas int32) error {
	deployment := &appsv1.Deployment{
		ObjectMeta: metav1.ObjectMeta{
			Name:      fmt.Sprintf("cloudflared-%s", tunnelName),
			Namespace: namespace,
		},
		Spec: appsv1.DeploymentSpec{
			Replicas: &replicas,
			Selector: &metav1.LabelSelector{
				MatchLabels: map[string]string{
					"app": fmt.Sprintf("cloudflared-%s", tunnelName),
				},
			},
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						"app": fmt.Sprintf("cloudflared-%s", tunnelName),
					},
				},
				Spec: corev1.PodSpec{
					Containers: []corev1.Container{
						{
							Name:  "cloudflared",
							Image: "cloudflare/cloudflared:latest",
							Args: []string{
								"tunnel",
								"--config",
								"/etc/cloudflared/config.yaml",
								"run",
							},
							Env: []corev1.EnvVar{
								{
									Name:  "TUNNEL_TOKEN",
									Value: tunnelSecret,
								},
							},
							VolumeMounts: []corev1.VolumeMount{
								{
									Name:      "config",
									MountPath: "/etc/cloudflared",
									ReadOnly:  true,
								},
							},
							LivenessProbe: &corev1.Probe{
								ProbeHandler: corev1.ProbeHandler{
									HTTPGet: &corev1.HTTPGetAction{
										Path: "/ready",
										Port: intstr.FromInt(2000),
									},
								},
								InitialDelaySeconds: 10,
								PeriodSeconds:       10,
								FailureThreshold:    1,
							},
							SecurityContext: &corev1.SecurityContext{
								ReadOnlyRootFilesystem:   &[]bool{true}[0],
								AllowPrivilegeEscalation: &[]bool{false}[0],
								RunAsNonRoot:             &[]bool{true}[0],
								RunAsUser:                &[]int64{65532}[0],
								Capabilities: &corev1.Capabilities{
									Drop: []corev1.Capability{"ALL"},
								},
								SeccompProfile: &corev1.SeccompProfile{
									Type: corev1.SeccompProfileTypeRuntimeDefault,
								},
							},
						},
					},
					Volumes: []corev1.Volume{
						{
							Name: "config",
							VolumeSource: corev1.VolumeSource{
								ConfigMap: &corev1.ConfigMapVolumeSource{
									LocalObjectReference: corev1.LocalObjectReference{
										Name: fmt.Sprintf("cloudflared-config-%s", tunnelName),
									},
								},
							},
						},
					},
				},
			},
		},
	}

	return r.Create(ctx, deployment)
}

func (r *TunnelReconciler) SetupWithManager(mgr ctrl.Manager) error {
	// This would be uncommented when we have the actual CRD type
	// return ctrl.NewControllerManagedBy(mgr).
	// 	For(&cloudflareapi.Tunnel{}).
	// 	Complete(r)
	return nil
}