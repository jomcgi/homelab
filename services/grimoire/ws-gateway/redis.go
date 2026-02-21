package main

import (
	"context"
	"log/slog"

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
func NewRedisRelay(addr string) (*RedisRelay, error) {
	client := redis.NewClient(&redis.Options{
		Addr: addr,
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
// for each received message. It blocks until the context is cancelled.
func (r *RedisRelay) Subscribe(handler func([]byte)) {
	sub := r.client.Subscribe(r.ctx, redisChannel)
	defer sub.Close()

	ch := sub.Channel()
	for {
		select {
		case msg, ok := <-ch:
			if !ok {
				return
			}
			handler([]byte(msg.Payload))
		case <-r.ctx.Done():
			return
		}
	}
}

// Close shuts down the Redis connection.
func (r *RedisRelay) Close() error {
	r.cancel()
	return r.client.Close()
}
