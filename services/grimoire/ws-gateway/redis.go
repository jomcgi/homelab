package main

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/redis/go-redis/v9"
)

const redisChannel = "grimoire:ws:broadcast"

// RedisRelay handles pub/sub for cross-replica WebSocket message distribution.
// Even with a single replica, using Redis pub/sub from the start means the
// gateway can scale horizontally without code changes.
type RedisRelay struct {
	client *redis.Client
	ctx    context.Context
	cancel context.CancelFunc
}

// NewRedisRelay connects to Redis and returns a relay.
func NewRedisRelay(addr, password string) (*RedisRelay, error) {
	client := redis.NewClient(&redis.Options{
		Addr:     addr,
		Password: password,
	})

	ctx, cancel := context.WithCancel(context.Background())

	// Verify connectivity.
	if err := client.Ping(ctx).Err(); err != nil {
		cancel()
		return nil, err
	}

	slog.Info("connected to Redis", "addr", addr)

	return &RedisRelay{
		client: client,
		ctx:    ctx,
		cancel: cancel,
	}, nil
}

// Publish sends a message to the broadcast channel.
func (r *RedisRelay) Publish(msg []byte) error {
	return r.client.Publish(r.ctx, redisChannel, msg).Err()
}

// Subscribe starts listening on the broadcast channel and calls handler
// for each received message. It reconnects on failure with backoff.
// It blocks until the context is cancelled.
func (r *RedisRelay) Subscribe(handler func([]byte)) {
	backoff := time.Second
	for {
		if r.ctx.Err() != nil {
			return
		}
		err := r.subscribe(handler)
		if err == nil || r.ctx.Err() != nil {
			return
		}
		slog.Error("redis subscription lost, reconnecting", "error", err, "backoff", backoff)
		time.Sleep(backoff)
		if backoff < 30*time.Second {
			backoff *= 2
		}
	}
}

func (r *RedisRelay) subscribe(handler func([]byte)) error {
	sub := r.client.Subscribe(r.ctx, redisChannel)
	defer sub.Close()

	ch := sub.Channel()
	for {
		select {
		case msg, ok := <-ch:
			if !ok {
				return fmt.Errorf("subscription channel closed")
			}
			handler([]byte(msg.Payload))
		case <-r.ctx.Done():
			return nil
		}
	}
}

// Ping checks Redis connectivity.
func (r *RedisRelay) Ping() error {
	return r.client.Ping(r.ctx).Err()
}

// Close shuts down the Redis connection.
func (r *RedisRelay) Close() error {
	r.cancel()
	return r.client.Close()
}
