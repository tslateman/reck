# Reck: Autonomous Manufacturing Intelligence

# Show available recipes
[private]
default:
    @just --list

# Print usage summary
help:
    @just --list

# Install Python dependencies and generate proto stubs
setup:
    uv sync --all-extras
    just proto
    @echo ""
    @echo "Checking required tools..."
    @command -v cargo >/dev/null 2>&1 && echo "  cargo  ok" || echo "  cargo  MISSING (install rustup)"
    @command -v docker >/dev/null 2>&1 && echo "  docker ok" || echo "  docker MISSING (install OrbStack or Docker Desktop)"
    @echo ""
    @echo "Setup complete. Run 'just dev' to start."

# Install reck CLI system-wide (adds 'reck' to PATH)
install:
    uv tool install .

# --- Development ---

# Start the full system
dev:
    uv run python -m reck

# Start the full system with injected anomaly after 10s
dev-anomaly:
    uv run python -m reck --anomaly

# Start simulated production line only
sim:
    uv run python -m sim

# Inject an anomaly into simulation
sim-anomaly:
    uv run python -m sim --anomaly

# Show recent decisions
log *ARGS:
    uv run reck log {{ARGS}}

# Show hot-path latency statistics (ms)
bench:
    uv run reck bench

# --- Quality ---

# Lint + format + type-check
check:
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright .

# Format code in place
fmt:
    uv run ruff format .
    uv run ruff check --fix .

# Run unit test suite
test:
    uv run pytest

# Run integration tests (requires: just build-core)
test-integration:
    uv run pytest --run-integration

# Run check + test (CI gate)
ci:
    just check
    just test

# --- Infrastructure ---

# Start EMQX broker
broker:
    docker run -d --name reck-emqx -p 1883:1883 -p 18083:18083 emqx/emqx:latest

# Stop EMQX broker
broker-stop:
    docker stop reck-emqx && docker rm reck-emqx

# --- Rust Hot-Path ---

# Build Rust hot-path target
build-core:
    cd reck-core && cargo build 2>&1

# Run Rust hot-path stub (override port with WATCH_PORT env var)
core-stub:
    cd reck-core && cargo run

# --- Proto ---

# Generate Python protobuf stubs from proto/reck.proto
proto:
    uv run python -m grpc_tools.protoc \
        -Iproto \
        --python_out=proto \
        --grpc_python_out=proto \
        --pyi_out=proto \
        proto/reck.proto

# --- Cleanup ---

# Remove generated caches and local data
clean:
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
    rm -rf data/
