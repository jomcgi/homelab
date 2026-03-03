#!/usr/bin/env bash

# ruleid: no-direct-test
go test ./...

# ruleid: no-direct-test
pytest tests/

# ruleid: no-direct-test
npm test

# ruleid: no-direct-test
npm run test

# ruleid: no-direct-test
go test -v -race ./internal/...

# ok: no-direct-test
bazel test //...

# ok: no-direct-test
bazel test //services/ships_api/...

# ok: no-direct-test
bb test //...
