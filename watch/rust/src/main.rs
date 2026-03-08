use std::net::SocketAddr;
use tonic::{transport::Server, Request, Response, Status};

pub mod reck {
    tonic::include_proto!("reck");
}

use reck::{
    watch_service_server::{WatchService, WatchServiceServer},
    SignalAck, SignalEvent,
};

#[derive(Debug, Default)]
struct WatchServiceImpl;

#[tonic::async_trait]
impl WatchService for WatchServiceImpl {
    async fn forward_signal(
        &self,
        request: Request<SignalEvent>,
    ) -> Result<Response<SignalAck>, Status> {
        let event = request.into_inner();
        eprintln!(
            "[watch-stub] received: source={} value={}",
            event.source, event.value
        );
        Ok(Response::new(SignalAck { accepted: true }))
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
    Server::builder()
        .add_service(WatchServiceServer::new(WatchServiceImpl::default()))
        .serve(addr)
        .await?;
    Ok(())
}
