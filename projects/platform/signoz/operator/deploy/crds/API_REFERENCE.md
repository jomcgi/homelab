# SigNoz Operator CRDs - API Reference

Complete field-level documentation for all CRD spec and status fields.

## HTTPCheck

### Spec Fields

| Field                | Type              | Required | Default | Description                               |
| -------------------- | ----------------- | -------- | ------- | ----------------------------------------- |
| `endpoint`           | string            | Yes      | -       | URL to check (must start with http(s)://) |
| `method`             | enum              | No       | GET     | HTTP method (GET, POST, HEAD)             |
| `expectedStatusCode` | integer           | No       | 200     | Expected response status code             |
| `interval`           | string            | No       | 2m      | Check frequency (e.g., "30s", "2m")       |
| `timeout`            | string            | No       | 10s     | Request timeout                           |
| `headers`            | map[string]string | No       | -       | Custom HTTP headers                       |
| `body`               | string            | No       | -       | Request body for POST requests            |
| `authSecretRef`      | object            | No       | -       | Reference to Secret with auth credentials |
| `insecureSkipVerify` | boolean           | No       | false   | Skip TLS verification                     |
| `labels`             | map[string]string | No       | -       | Labels for grouping/filtering             |
| `disabled`           | boolean           | No       | false   | Temporarily disable the check             |

#### authSecretRef Object

| Field       | Type     | Required | Description                                        |
| ----------- | -------- | -------- | -------------------------------------------------- |
| `name`      | string   | Yes      | Secret name                                        |
| `namespace` | string   | No       | Secret namespace (defaults to HTTPCheck namespace) |
| `keys`      | []object | Yes      | Array of key mappings                              |

#### authSecretRef.keys[] Object

| Field        | Type   | Required | Description             |
| ------------ | ------ | -------- | ----------------------- |
| `secretKey`  | string | Yes      | Key in the Secret       |
| `headerName` | string | Yes      | HTTP header name to set |

### Status Fields

| Field              | Type      | Description                               |
| ------------------ | --------- | ----------------------------------------- |
| `phase`            | string    | Pending, Syncing, Synced, Error, Disabled |
| `signozId`         | string    | ID in SigNoz                              |
| `lastSyncTime`     | timestamp | Last sync with SigNoz                     |
| `lastCheckTime`    | timestamp | Last health check execution               |
| `lastCheckResult`  | string    | Success, Failure, Unknown                 |
| `lastResponseTime` | integer   | Response time in milliseconds             |
| `errorMessage`     | string    | Error details if phase is Error           |

## Alert

### Spec Fields

| Field                  | Type     | Required | Default | Description                         |
| ---------------------- | -------- | -------- | ------- | ----------------------------------- |
| `alertName`            | string   | Yes      | -       | Display name for the alert          |
| `description`          | string   | No       | -       | Detailed description                |
| `summary`              | string   | No       | -       | Short summary for notifications     |
| `httpCheckRef`         | object   | No\*     | -       | Reference to HTTPCheck to alert on  |
| `customQuery`          | object   | No\*     | -       | Custom PromQL/ClickHouse query      |
| `condition`            | object   | Yes      | -       | Alert trigger condition             |
| `evalWindow`           | string   | No       | 5m      | Evaluation time window              |
| `frequency`            | string   | No       | 1m      | Evaluation frequency                |
| `consecutiveFailures`  | integer  | No       | 1       | Required consecutive failures       |
| `severity`             | enum     | No       | warning | critical, warning, info             |
| `notificationChannels` | []string | No       | -       | NotificationChannel names to notify |
| `labels`               | map      | No       | -       | Labels for grouping/routing         |
| `annotations`          | map      | No       | -       | Additional metadata                 |
| `disabled`             | boolean  | No       | false   | Temporarily disable                 |
| `runbookUrl`           | string   | No       | -       | Link to response documentation      |

\*Either `httpCheckRef` or `customQuery` must be specified.

#### httpCheckRef Object

| Field       | Type   | Required | Description                                       |
| ----------- | ------ | -------- | ------------------------------------------------- |
| `name`      | string | Yes      | HTTPCheck resource name                           |
| `namespace` | string | No       | HTTPCheck namespace (defaults to Alert namespace) |

#### customQuery Object

| Field       | Type   | Required | Description                          |
| ----------- | ------ | -------- | ------------------------------------ |
| `query`     | string | Yes      | PromQL or ClickHouse query           |
| `queryType` | enum   | No       | promql, clickhouse (default: promql) |

#### condition Object

| Field       | Type   | Required | Default | Description                      |
| ----------- | ------ | -------- | ------- | -------------------------------- |
| `operator`  | enum   | Yes      | -       | >, >=, <, <=, ==, !=             |
| `threshold` | number | Yes      | -       | Value to compare against         |
| `matchType` | enum   | No       | once    | once, always, onAverage, inTotal |

### Status Fields

| Field           | Type      | Description                               |
| --------------- | --------- | ----------------------------------------- |
| `phase`         | string    | Pending, Syncing, Synced, Error, Disabled |
| `signozId`      | string    | ID in SigNoz                              |
| `lastSyncTime`  | timestamp | Last sync with SigNoz                     |
| `alertState`    | string    | inactive, pending, firing                 |
| `lastFiredTime` | timestamp | Last time alert fired                     |
| `errorMessage`  | string    | Error details if phase is Error           |

## NotificationChannel

Cluster-scoped resource for configuring notification targets.

### Spec Fields

| Field          | Type    | Required | Default | Description                                         |
| -------------- | ------- | -------- | ------- | --------------------------------------------------- |
| `type`         | enum    | Yes      | -       | pagerduty, webhook, slack, email, opsgenie, msteams |
| `sendResolved` | boolean | No       | true    | Send notification when alert resolves               |
| `pagerduty`    | object  | No\*     | -       | PagerDuty configuration                             |
| `webhook`      | object  | No\*     | -       | Webhook configuration                               |
| `slack`        | object  | No\*     | -       | Slack configuration                                 |
| `email`        | object  | No\*     | -       | Email configuration                                 |
| `opsgenie`     | object  | No\*     | -       | OpsGenie configuration                              |
| `msteams`      | object  | No\*     | -       | Microsoft Teams configuration                       |

\*The configuration object matching `type` is required.

### PagerDuty Configuration

| Field                 | Type   | Required | Description                      |
| --------------------- | ------ | -------- | -------------------------------- |
| `routingKeySecretRef` | object | Yes      | Secret reference for routing key |
| `severity`            | enum   | No       | error, warning, info, critical   |
| `class`               | string | No       | PagerDuty incident class         |
| `component`           | string | No       | PagerDuty incident component     |
| `group`               | string | No       | PagerDuty incident group         |

#### routingKeySecretRef Object

| Field       | Type   | Required | Description                       |
| ----------- | ------ | -------- | --------------------------------- |
| `name`      | string | Yes      | Secret name                       |
| `namespace` | string | Yes      | Secret namespace                  |
| `key`       | string | Yes      | Secret key containing routing key |

### Webhook Configuration

| Field           | Type              | Required | Description                      |
| --------------- | ----------------- | -------- | -------------------------------- |
| `url`           | string            | Yes      | Webhook URL                      |
| `httpMethod`    | enum              | No       | POST, PUT, PATCH (default: POST) |
| `authSecretRef` | object            | No       | Secret reference for auth token  |
| `headers`       | map[string]string | No       | Custom HTTP headers              |

#### webhook.authSecretRef Object

| Field        | Type   | Required | Description                            |
| ------------ | ------ | -------- | -------------------------------------- |
| `name`       | string | Yes      | Secret name                            |
| `namespace`  | string | Yes      | Secret namespace                       |
| `key`        | string | Yes      | Secret key containing auth token       |
| `headerName` | string | Yes      | HTTP header name (e.g., Authorization) |

### Slack Configuration

| Field                 | Type   | Required | Description                      |
| --------------------- | ------ | -------- | -------------------------------- |
| `webhookUrlSecretRef` | object | Yes      | Secret reference for webhook URL |
| `channel`             | string | No       | Override channel (e.g., #alerts) |
| `username`            | string | No       | Bot username                     |
| `iconEmoji`           | string | No       | Icon emoji (e.g., :warning:)     |
| `iconUrl`             | string | No       | Icon URL                         |

#### slack.webhookUrlSecretRef Object

| Field       | Type   | Required | Description                       |
| ----------- | ------ | -------- | --------------------------------- |
| `name`      | string | Yes      | Secret name                       |
| `namespace` | string | Yes      | Secret namespace                  |
| `key`       | string | Yes      | Secret key containing webhook URL |

### Email Configuration

| Field     | Type     | Required | Description               |
| --------- | -------- | -------- | ------------------------- |
| `to`      | []string | Yes      | Recipient email addresses |
| `from`    | string   | No       | Sender email address      |
| `subject` | string   | No       | Email subject template    |

### OpsGenie Configuration

| Field             | Type     | Required | Description                      |
| ----------------- | -------- | -------- | -------------------------------- |
| `apiKeySecretRef` | object   | Yes      | Secret reference for API key     |
| `apiUrl`          | string   | No       | OpsGenie API URL (for EU region) |
| `priority`        | enum     | No       | P1, P2, P3, P4, P5               |
| `responders`      | []object | No       | Array of responder definitions   |
| `tags`            | []string | No       | Alert tags                       |

#### opsgenie.apiKeySecretRef Object

| Field       | Type   | Required | Description                   |
| ----------- | ------ | -------- | ----------------------------- |
| `name`      | string | Yes      | Secret name                   |
| `namespace` | string | Yes      | Secret namespace              |
| `key`       | string | Yes      | Secret key containing API key |

#### opsgenie.responders[] Object

| Field      | Type   | Required | Description                      |
| ---------- | ------ | -------- | -------------------------------- |
| `type`     | enum   | Yes      | team, user, escalation, schedule |
| `id`       | string | No\*     | Responder ID                     |
| `name`     | string | No\*     | Responder name                   |
| `username` | string | No\*     | Username (for type: user)        |

\*One of `id`, `name`, or `username` is required.

### Microsoft Teams Configuration

| Field                 | Type   | Required | Description                      |
| --------------------- | ------ | -------- | -------------------------------- |
| `webhookUrlSecretRef` | object | Yes      | Secret reference for webhook URL |
| `title`               | string | No       | Message title template           |

#### msteams.webhookUrlSecretRef Object

| Field       | Type   | Required | Description                       |
| ----------- | ------ | -------- | --------------------------------- |
| `name`      | string | Yes      | Secret name                       |
| `namespace` | string | Yes      | Secret namespace                  |
| `key`       | string | Yes      | Secret key containing webhook URL |

### Status Fields

| Field            | Type      | Description                     |
| ---------------- | --------- | ------------------------------- |
| `phase`          | string    | Pending, Syncing, Synced, Error |
| `signozId`       | string    | ID in SigNoz                    |
| `lastSyncTime`   | timestamp | Last sync with SigNoz           |
| `lastTestTime`   | timestamp | Last test notification sent     |
| `lastTestResult` | string    | Success, Failure, Unknown       |
| `errorMessage`   | string    | Error details if phase is Error |
