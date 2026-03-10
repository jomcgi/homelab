package controller

import (
	"context"
	"time"

	"sigs.k8s.io/controller-runtime/pkg/client"
	logf "sigs.k8s.io/controller-runtime/pkg/log"

	v1alpha1 "github.com/jomcgi/homelab/projects/operators/oci-model-cache/api/v1alpha1"
)

// TTLSweeper periodically checks for ModelCache CRs that have exceeded their TTL
// and deletes them. Runs as a manager Runnable.
type TTLSweeper struct {
	Client   client.Client
	Interval time.Duration
}

// Start implements manager.Runnable.
func (s *TTLSweeper) Start(ctx context.Context) error {
	log := logf.FromContext(ctx).WithName("ttl-sweeper")
	ticker := time.NewTicker(s.Interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			log.Info("TTL sweeper stopping")
			return nil
		case <-ticker.C:
			s.sweep(ctx)
		}
	}
}

func (s *TTLSweeper) sweep(ctx context.Context) {
	log := logf.FromContext(ctx).WithName("ttl-sweeper")

	var list v1alpha1.ModelCacheList
	if err := s.Client.List(ctx, &list); err != nil {
		log.Error(err, "Failed to list ModelCache resources for TTL sweep")
		return
	}

	now := time.Now()
	deleted := 0
	for i := range list.Items {
		mc := &list.Items[i]
		if mc.Spec.TTL == nil || mc.Spec.TTL.Duration <= 0 {
			continue
		}

		expiry := mc.CreationTimestamp.Add(mc.Spec.TTL.Duration)
		if now.After(expiry) {
			log.Info("Deleting expired ModelCache", "name", mc.Name, "ttl", mc.Spec.TTL.Duration, "created", mc.CreationTimestamp)
			if err := s.Client.Delete(ctx, mc); err != nil {
				log.Error(err, "Failed to delete expired ModelCache", "name", mc.Name)
				continue
			}
			deleted++
		}
	}

	if deleted > 0 {
		log.Info("TTL sweep complete", "deleted", deleted)
	}
}
