use dashmap::DashMap;
use std::collections::VecDeque;
use std::net::SocketAddr;
use std::sync::Arc;
use tonic::{transport::Server, Request, Response, Status};

pub mod reck {
    tonic::include_proto!("reck");
}

mod act;
mod guard;

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
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("reck_core=info".parse().unwrap()),
        )
        .init();

    let port: u16 = std::env::var("WATCH_PORT")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(50051);
    let addr: SocketAddr = format!("0.0.0.0:{port}").parse()?;
    tracing::info!(addr = %addr, "reck-core listening");

    let watch_service = WatchServiceImpl::default();

    let constraints_path = std::env::var("CONSTRAINTS_PATH")
        .unwrap_or_else(|_| "../guard/constraints.yaml".to_string());
    let guard_service =
        guard::GuardServiceImpl::from_yaml(std::path::Path::new(&constraints_path))?;

    let mqtt_host = std::env::var("MQTT_HOST").unwrap_or_else(|_| "localhost".to_string());
    let mqtt_port = std::env::var("MQTT_PORT")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(1883);

    let (act_service, mut eventloop) = act::ActServiceImpl::new(&mqtt_host, mqtt_port).await;
    let connected = act_service.connected.clone();

    // Spawn MQTT event loop
    tokio::spawn(async move {
        loop {
            match eventloop.poll().await {
                Ok(rumqttc::Event::Incoming(rumqttc::Packet::ConnAck(_))) => {
                    tracing::info!("act MQTT connected");
                    connected.store(true, std::sync::atomic::Ordering::Relaxed);
                }
                Ok(_) => {}
                Err(e) => {
                    tracing::warn!(error = %e, error_code = "MQTT_POLL_ERROR", "act MQTT poll error");
                    connected.store(false, std::sync::atomic::Ordering::Relaxed);
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

#[cfg(test)]
mod tests {
    use super::*;

    fn make_signal(source: &str, value: f64) -> SignalEvent {
        SignalEvent {
            source: source.to_string(),
            value,
            unit: "celsius".to_string(),
            state_transition: "".to_string(),
            timestamp: None,
            context: None,
        }
    }

    #[tokio::test]
    async fn test_no_anomaly_within_normal_range() {
        let svc = WatchServiceImpl::default();
        // Feed 30 samples at value 100.0 to build baseline
        for _ in 0..30 {
            let req = Request::new(make_signal("test/temp", 100.0));
            let res = svc.forward_signal(req).await.unwrap().into_inner();
            assert!(res.accepted);
            assert!(res.anomaly.is_none());
        }
        // Value within normal range
        let req = Request::new(make_signal("test/temp", 100.5));
        let res = svc.forward_signal(req).await.unwrap().into_inner();
        assert!(res.anomaly.is_none());
    }

    #[tokio::test]
    async fn test_anomaly_detected_on_spike() {
        let svc = WatchServiceImpl {
            windows: Arc::new(DashMap::new()),
            window_size: 100,
            min_samples: 20,
        };
        // Build baseline: 25 samples at 100.0 with slight variance
        for i in 0..25 {
            let v = 100.0 + (i as f64 % 3.0) * 0.1;
            let req = Request::new(make_signal("test/temp", v));
            svc.forward_signal(req).await.unwrap();
        }
        // Spike far outside normal range
        let req = Request::new(make_signal("test/temp", 200.0));
        let res = svc.forward_signal(req).await.unwrap().into_inner();
        assert!(res.anomaly.is_some());
        let anomaly = res.anomaly.unwrap();
        assert_eq!(anomaly.source, "test/temp");
        assert!(anomaly.deviation_sigma > 3.0);
    }

    #[tokio::test]
    async fn test_insufficient_samples_no_anomaly() {
        let svc = WatchServiceImpl {
            windows: Arc::new(DashMap::new()),
            window_size: 100,
            min_samples: 20,
        };
        // Only 5 samples -- below min_samples threshold
        for _ in 0..5 {
            let req = Request::new(make_signal("test/temp", 100.0));
            svc.forward_signal(req).await.unwrap();
        }
        // Even a spike should not trigger anomaly with insufficient data
        let req = Request::new(make_signal("test/temp", 999.0));
        let res = svc.forward_signal(req).await.unwrap().into_inner();
        assert!(res.anomaly.is_none());
    }

    #[tokio::test]
    async fn test_window_size_respected() {
        let svc = WatchServiceImpl {
            windows: Arc::new(DashMap::new()),
            window_size: 30,
            min_samples: 20,
        };
        // Fill window with 35 samples (5 should be evicted)
        for _ in 0..35 {
            let req = Request::new(make_signal("test/temp", 100.0));
            svc.forward_signal(req).await.unwrap();
        }
        let state = svc.windows.get("test/temp").unwrap();
        assert!(state.values.len() <= 30);
    }

    #[tokio::test]
    async fn test_separate_sources_independent() {
        let svc = WatchServiceImpl::default();
        // Feed source A with stable data (slight variance for nonzero stddev)
        for i in 0..25 {
            let v = 100.0 + (i as f64 % 3.0) * 0.1;
            let req = Request::new(make_signal("source_a", v));
            svc.forward_signal(req).await.unwrap();
        }
        // Feed source B with different stable data
        for i in 0..25 {
            let v = 50.0 + (i as f64 % 3.0) * 0.1;
            let req = Request::new(make_signal("source_b", v));
            svc.forward_signal(req).await.unwrap();
        }
        // Spike on source A should detect anomaly
        let req = Request::new(make_signal("source_a", 200.0));
        let res = svc.forward_signal(req).await.unwrap().into_inner();
        assert!(res.anomaly.is_some());
        // Value near the mean on source B should not
        let req = Request::new(make_signal("source_b", 50.1));
        let res = svc.forward_signal(req).await.unwrap().into_inner();
        assert!(res.anomaly.is_none());
    }

    #[tokio::test]
    async fn test_configurable_window_and_min_samples() {
        let svc = WatchServiceImpl {
            windows: Arc::new(DashMap::new()),
            window_size: 50,
            min_samples: 10,
        };
        // With lower min_samples, anomaly detection kicks in sooner
        for i in 0..12 {
            let v = 100.0 + (i as f64 % 3.0) * 0.1;
            let req = Request::new(make_signal("test/temp", v));
            svc.forward_signal(req).await.unwrap();
        }
        let req = Request::new(make_signal("test/temp", 200.0));
        let res = svc.forward_signal(req).await.unwrap().into_inner();
        assert!(res.anomaly.is_some());
    }
}
