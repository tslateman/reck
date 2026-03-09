use dashmap::DashMap;
use std::collections::VecDeque;
use std::net::SocketAddr;
use std::sync::Arc;
use tonic::{transport::Server, Request, Response, Status};

pub mod reck {
    tonic::include_proto!("reck");
}

use reck::{
    watch_service_server::{WatchService, WatchServiceServer},
    AnomalyEvent, SignalAck, SignalEvent,
};

#[derive(Debug)]
struct WindowState {
    values: VecDeque<f64>,
    last_seen: chrono::DateTime<chrono::Utc>,
}

impl WindowState {
    fn new(window_size: usize) -> Self {
        Self {
            values: VecDeque::with_capacity(window_size),
            last_seen: chrono::Utc::now(),
        }
    }
}

#[derive(Debug)]
struct WatchServiceImpl {
    windows: Arc<DashMap<String, WindowState>>,
    window_size: usize,
    min_samples: usize,
}

impl Default for WatchServiceImpl {
    fn default() -> Self {
        Self {
            windows: Arc::new(DashMap::new()),
            window_size: 100,
            min_samples: 20,
        }
    }
}

#[tonic::async_trait]
impl WatchService for WatchServiceImpl {
    async fn forward_signal(
        &self,
        request: Request<SignalEvent>,
    ) -> Result<Response<SignalAck>, Status> {
        let event = request.into_inner();
        let source = event.source.clone();
        let value = event.value;

        // Ensure window exists for this source
        let mut state = self
            .windows
            .entry(source.clone())
            .or_insert_with(|| WindowState::new(self.window_size));

        // Check for gap > 60s
        let now = chrono::Utc::now();
        if (now - state.last_seen).num_seconds() > 60 {
            state.values.clear();
        }
        state.last_seen = now;

        let mut anomaly = None;

        // Compute stats from current window (before adding new value)
        if state.values.len() >= self.min_samples {
            let n = state.values.len() as f64;
            let mean = state.values.iter().sum::<f64>() / n;
            let variance = state.values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / n;
            let stddev = variance.sqrt();

            if stddev > 0.0 {
                let deviation = (value - mean).abs() / stddev;
                if deviation > 3.0 {
                    anomaly = Some(AnomalyEvent {
                        source: source.clone(),
                        timestamp: event.timestamp,
                        value,
                        baseline_mean: (mean * 10000.0).round() / 10000.0,
                        baseline_stddev: (stddev * 10000.0).round() / 10000.0,
                        deviation_sigma: (deviation * 100.0).round() / 100.0,
                        priority: 1, // LOW
                        context: event.context,
                    });
                }
            }
        }

        // Add value to window
        state.values.push_back(value);
        if state.values.len() > self.window_size {
            state.values.pop_front();
        }

        Ok(Response::new(SignalAck {
            accepted: true,
            anomaly,
        }))
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let port: u16 = std::env::var("WATCH_PORT")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(50051);
    let addr: SocketAddr = format!("0.0.0.0:{port}").parse()?;
    eprintln!("[watch-stub] listening on {addr}");

    let service = WatchServiceImpl::default();

    Server::builder()
        .add_service(WatchServiceServer::new(service))
        .serve(addr)
        .await?;

    Ok(())
}
