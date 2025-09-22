# AIS Streaming Implementation Guide - Quick Reference

## Resource Allocation (per node)
- **NATS JetStream**: 3GB RAM, 4 CPU cores
- **ClickHouse**: 6GB RAM, 8 CPU cores  
- **Storage**: 100GB total (20GB NATS, 80GB ClickHouse)

## NATS JetStream Configuration

### Stream Settings
```yaml
jetstream:
  max_memory_store: 2Gi
  max_file_store: 20Gi
  store_dir: /data/jetstream
  
streams:
  - name: AIS-POSITIONS
    subjects: ["ais.*.positions.*"]
    retention: limits
    max_age: 24h
    max_msgs_per_subject: 1000
    duplicate_window: 5m
    compression: s2
    storage: file
    discard: old
    
  - name: AIS-STATIC
    subjects: ["ais.*.static.*"]
    retention: limits
    max_age: 7d
    duplicate_window: 30m
    compression: s2
```

### Consumer Configuration
```yaml
consumers:
  ack_policy: explicit
  ack_wait: 30s
  max_deliver: 3
  max_ack_pending: 1000
  max_batch: 100
  flow_control: true
```

## ClickHouse Schema

### Position Table (Optimized)
```sql
CREATE TABLE ais_positions (
    timestamp DateTime64(3) CODEC(DoubleDelta, ZSTD),
    mmsi UInt32 CODEC(T64),
    latitude Float32 CODEC(Gorilla, ZSTD),
    longitude Float32 CODEC(Gorilla, ZSTD),
    speed Float32 CODEC(Gorilla),
    course Float32 CODEC(Gorilla),
    heading UInt16 CODEC(T64),
    status UInt8,
    h3_7 UInt64 CODEC(T64),  -- H3 index resolution 7 (5km)
    h3_9 UInt64 CODEC(T64)   -- H3 index resolution 9 (0.5km)
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (mmsi, timestamp)
TTL timestamp + INTERVAL 1 DAY TO DISK 'warm',
    timestamp + INTERVAL 7 DAY DELETE
SETTINGS index_granularity = 8192;
```

### Current Positions View
```sql
CREATE MATERIALIZED VIEW vessel_current_positions
ENGINE = AggregatingMergeTree()
ORDER BY mmsi
AS SELECT
    mmsi,
    argMaxState(latitude, timestamp) as lat,
    argMaxState(longitude, timestamp) as lon,
    argMaxState(speed, timestamp) as spd,
    maxState(timestamp) as last_seen
FROM ais_positions
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY mmsi;
```

### Direct NATS Integration
```sql
CREATE TABLE nats_queue (
    timestamp DateTime64(3),
    mmsi UInt32,
    latitude Float32,
    longitude Float32
) ENGINE = NATS
SETTINGS nats_url = 'nats:4222',
         nats_subjects = 'ais.positions',
         nats_format = 'JSONEachRow';

CREATE MATERIALIZED VIEW nats_consumer TO ais_positions AS
SELECT *, 
       geoToH3(longitude, latitude, 7) as h3_7,
       geoToH3(longitude, latitude, 9) as h3_9
FROM nats_queue
WHERE latitude BETWEEN -90 AND 90 
  AND longitude BETWEEN -180 AND 180;
```

## ClickHouse Performance Settings

```xml
<clickhouse>
  <profiles>
    <default>
      <max_memory_usage>6000000000</max_memory_usage>
      <max_memory_usage_for_all_queries>8000000000</max_memory_usage_for_all_queries>
      <max_threads>10</max_threads>
      <background_pool_size>8</background_pool_size>
      <background_merges_mutations_concurrency_ratio>2</background_merges_mutations_concurrency_ratio>
      
      <!-- Async inserts for better throughput -->
      <async_insert>1</async_insert>
      <async_insert_max_data_size>10485760</async_insert_max_data_size>
      <async_insert_busy_timeout_ms>200</async_insert_busy_timeout_ms>
      
      <!-- Merge control -->
      <parts_to_delay_insert>150</parts_to_delay_insert>
      <parts_to_throw_insert>300</parts_to_throw_insert>
    </default>
  </profiles>
</clickhouse>
```

## Kubernetes Deployments

### NATS StatefulSet (Single Node)
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: nats
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: nats
        image: nats:2.10-alpine
        resources:
          requests:
            memory: 2Gi
            cpu: 2
          limits:
            memory: 3Gi
            cpu: 4
        env:
        - name: NATS_JETSTREAM_MAX_MEM
          value: "2G"
        - name: NATS_JETSTREAM_MAX_FILE
          value: "20G"
```

### ClickHouse Installation
```yaml
apiVersion: clickhouse.altinity.com/v1
kind: ClickHouseInstallation
metadata:
  name: ais-clickhouse
spec:
  configuration:
    clusters:
    - name: cluster
      layout:
        shardsCount: 1
        replicasCount: 1
      templates:
        podTemplate: clickhouse-pod
        dataVolumeClaimTemplate: data-volume
        
  templates:
    podTemplates:
    - name: clickhouse-pod
      spec:
        containers:
        - name: clickhouse
          resources:
            requests:
              memory: 6Gi
              cpu: 6
            limits:
              memory: 8Gi
              cpu: 10
              
    volumeClaimTemplates:
    - name: data-volume
      spec:
        storageClassName: longhorn
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 80Gi
```

## AIS Data Validation (Consumer)

```python
def validate_ais_message(msg):
    # Required validations
    if not (-90 <= msg['latitude'] <= 90):
        return False
    if not (-180 <= msg['longitude'] <= 180):
        return False
    if not (100000000 <= msg['mmsi'] <= 999999999):
        return False
    if msg['speed'] > 102.2:  # Max 102.2 knots
        msg['speed'] = 102.2
    return True

# Message type routing
POSITION_TYPES = [1, 2, 3, 18, 19, 27]
STATIC_TYPES = [5, 24]

def route_message(msg_type):
    if msg_type in POSITION_TYPES:
        return "ais.region.positions"
    elif msg_type in STATIC_TYPES:
        return "ais.region.static"
```

## Monitoring Metrics

### Key Metrics to Track
```yaml
alerts:
  - name: AIS Message Rate
    expr: rate(ais_messages_total[1m]) < 10
    severity: warning
    
  - name: Consumer Lag
    expr: nats_consumer_pending_messages > 10000
    severity: critical
    
  - name: ClickHouse Parts Queue
    expr: clickhouse_merge_queue_size > 100
    severity: warning
    
  - name: Query Latency
    expr: histogram_quantile(0.95, clickhouse_query_duration) > 0.1
    severity: warning
```

## Storage Classes

```yaml
# Longhorn configurations
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: longhorn-fast
parameters:
  numberOfReplicas: "2"
  dataLocality: "best-effort"
  diskSelector: "ssd"
  
---
apiVersion: storage.k8s.io/v1
kind: StorageClass  
metadata:
  name: longhorn-standard
parameters:
  numberOfReplicas: "2"
  dataLocality: "disabled"
```

## Implementation Checklist

1. **Deploy NATS JetStream**
   - [ ] StatefulSet with 3GB RAM, file storage
   - [ ] Create AIS-POSITIONS and AIS-STATIC streams
   - [ ] Configure S2 compression and deduplication

2. **Deploy ClickHouse**
   - [ ] Single-node with 6GB RAM allocation
   - [ ] Create ais_positions table with codecs
   - [ ] Enable async inserts
   - [ ] Create materialized views

3. **Setup Data Pipeline**
   - [ ] Implement coordinate validation
   - [ ] Configure NATS consumer with batching
   - [ ] Setup ClickHouse NATS engine integration

4. **Configure Retention**
   - [ ] 24h detailed positions
   - [ ] 7d aggregated data
   - [ ] TTL policies for automatic cleanup

5. **Enable Monitoring**
   - [ ] NATS metrics endpoint (8222)
   - [ ] ClickHouse Prometheus export
   - [ ] SigNoz dashboards
   - [ ] Alert rules

## Expected Performance
- **Message throughput**: 5,000-10,000/sec
- **Query latency**: P95 < 100ms
- **Storage growth**: 1.5GB/month
- **Compression ratio**: 10:1
- **CPU usage**: <50% average
- **Memory stable**: 9GB combi
