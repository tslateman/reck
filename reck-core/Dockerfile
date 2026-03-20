FROM rust:1.77 AS builder

WORKDIR /app
COPY . .
# Proto file lives one level up
COPY ../proto/reck.proto /app/proto/reck.proto
RUN cargo build --release

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/target/release/reck-core /usr/local/bin/reck-core
ENTRYPOINT ["reck-core"]
