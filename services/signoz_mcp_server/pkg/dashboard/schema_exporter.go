package dashboard

// Schema strings populated by InitClickhouseSchema.
//
// In the upstream SigNoz MCP server these are derived from the signoz-otel-collector
// schema migrator package. For this vendored build we replace that heavy dependency
// (which pulls in ClickHouse drivers and hundreds of transitive modules) with static
// schema summaries. The query reference constants in query.go already contain
// comprehensive ClickHouse schema documentation and examples that LLMs use.

// LogsSchema contains ClickHouse schema reference for logs queries.
var LogsSchema string

// MetricsSchema contains ClickHouse schema reference for metrics queries.
var MetricsSchema string

// TracesSchema contains ClickHouse schema reference for traces queries.
var TracesSchema string

const schemaReadingInstructions = `
INSTRUCTIONS FOR USING THIS CLICKHOUSE SCHEMA
1. Read every table, column, and data type exactly as written.
2. Never skip or simplify types. Use LowCardinality(...), Map(...), JSON(...),
   AggregateFunction(...), Array(...), Tuple(...), Nullable(...) exactly as shown.
3. Do not infer or assume types. Trust only the declared type.
4. When writing queries:
   - use exact column names
   - use exact data types
   - verify the column exists in the table
5. Aliases may be used, but their type is identical to the base column.
6. Do not hallucinate additional fields or hidden schema.
Use this schema verbatim for all query construction.
`

// InitClickhouseSchema populates the schema reference strings with static summaries.
// Refer to ClickhouseSqlQueryForLogs, ClickhouseSqlQueryForMetrics,
// ClickhouseSqlQueryForTraces, and Querybuilder constants in query.go for
// comprehensive ClickHouse query patterns and table documentation.
func InitClickhouseSchema() {
	LogsSchema = schemaReadingInstructions + logsSchemaReference
	MetricsSchema = schemaReadingInstructions + metricsSchemaReference
	TracesSchema = schemaReadingInstructions + tracesSchemaReference
}

const logsSchemaReference = `
=== LOGS SCHEMA ===

Database: signoz_logs

Key Tables:
- distributed_logs_v2 (main query table)
- distributed_logs_v2_resource (resource fingerprint lookups)
- distributed_tag_attributes_v2 (tag attribute metadata)

See ClickhouseSqlQueryForLogs resource for full column details and query examples.
`

const metricsSchemaReference = `
=== METRICS SCHEMA ===

Database: signoz_metrics

Key Tables:
- distributed_samples_v4 (raw metric samples)
- distributed_time_series_v4 (1h granularity time series)
- distributed_time_series_v4_6hrs (6h granularity)
- distributed_time_series_v4_1day (1d granularity)
- distributed_exp_hist (exponential histograms)

See ClickhouseSqlQueryForMetrics resource for full column details and query examples.
`

const tracesSchemaReference = `
=== TRACES SCHEMA ===

Database: signoz_traces

Key Tables:
- distributed_signoz_index_v3 (main trace index)
- distributed_signoz_spans (span details)
- distributed_traces_v3_resource (resource fingerprint lookups)
- distributed_dependency_graph_minutes_v2 (service dependencies)
- distributed_trace_summary (trace summaries)
- distributed_signoz_error_index_v2 (error index)
- distributed_top_level_operations (top level ops)

See ClickhouseSqlQueryForTraces resource for full column details and query examples.
`
