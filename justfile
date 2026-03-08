# Reck: Autonomous Manufacturing Intelligence

# Start EMQX broker
broker:
    docker run -d --name reck-emqx -p 1883:1883 -p 18083:18083 emqx/emqx:latest

# Stop EMQX broker
broker-stop:
    docker stop reck-emqx && docker rm reck-emqx

# Start simulated production line
sim:
    uv run python -m sim

# Inject an anomaly into simulation
sim-anomaly:
    uv run python -m sim --anomaly

# Start the full system (simulator + all components)
dev:
    uv run python -m reck

# Run full test suite
test:
    uv run pytest

# Lint + format + type-check
check:
    uv run ruff check .
    uv run ruff format --check .

# Format code
fmt:
    uv run ruff format .
    uv run ruff check --fix .

# Generate Python protobuf stubs
proto:
    uv run python -m grpc_tools.protoc \
        -Iproto \
        --python_out=proto \
        --grpc_python_out=proto \
        --pyi_out=proto \
        proto/reck.proto

# Build Rust watch gRPC stub
build-watch:
    cd watch/rust && cargo build 2>&1

# Run Rust watch gRPC stub (set WATCH_PORT env var to override 50051)
watch-stub:
    cd watch/rust && cargo run

# Run integration tests including gRPC contract tests (requires just build-watch first)
test-integration:
    uv run pytest --run-integration

# Show recent decisions
log *ARGS:
    uv run reck log {{ARGS}}
