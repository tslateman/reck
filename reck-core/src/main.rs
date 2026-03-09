use dashmap::DashMap;
use std::collections::VecDeque;
use std::net::SocketAddr;
use std::sync::Arc;
use tonic::{transport::Server, Request, Response, Status};

pub mod reck {
    tonic::include_proto!("reck");
}

mod guard;
mod act;

use reck::{
    act_service_server::ActServiceServer,
    guard_service_server::GuardServiceServer,
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
    eprintln!("[reck-core] listening on {addr}");

    let watch_service = WatchServiceImpl::default();

    let constraints_path = std::env::var("CONSTRAINTS_PATH")
        .unwrap_or_else(|_| "../guard/constraints.yaml".to_string());
    let guard_service = guard::GuardServiceImpl::from_yaml(std::path::Path::new(&constraints_path))?;

    let mqtt_host = std::env::var("MQTT_HOST").unwrap_or_else(|_| "localhost".to_string());
    let mqtt_port = std::env::var("MQTT_PORT")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(1883);
    
    let (act_service, mut eventloop) = act::ActServiceImpl::new(&mqtt_host, mqtt_port).await;

    // Spawn MQTT event loop
    tokio::spawn(async move {
        loop {
            match eventloop.poll().await {
                Ok(notification) => {
                    if let rumqttc::Event::Incoming(_) = notification {
                        // success
                    }
                }
                Err(e) => {
                    eprintln!("[act] MQTT poll error: {}", e);
                    tokio::time::sleep(std::time::Duration::from_secs(1)).await;
                }
            }
        }
    });

    Server::builder()
        .add_service(WatchServiceServer::new(watch_service))
        .add_service(GuardServiceServer::new(guard_service))
        .add_service(ActServiceServer::new(act_service))
        .serve(addr)
        .await?;

    Ok(())
}
