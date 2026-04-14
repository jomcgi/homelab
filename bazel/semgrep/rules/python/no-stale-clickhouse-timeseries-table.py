# Tests for no-stale-clickhouse-timeseries-table rule.

# ruleid: no-stale-clickhouse-timeseries-table
query = "SELECT * FROM distributed_time_series_v4"

# ruleid: no-stale-clickhouse-timeseries-table
query = "SELECT fingerprint FROM distributed_time_series_v4 WHERE"

# ok: no-stale-clickhouse-timeseries-table
query = "SELECT * FROM distributed_time_series_v4_6hrs"

# ok: no-stale-clickhouse-timeseries-table
query = "SELECT * FROM distributed_time_series_v4_1day"
