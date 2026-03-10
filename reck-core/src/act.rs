use rumqttc::{AsyncClient, MqttOptions, QoS};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};
use std::time::Duration;
use tonic::{Request, Response, Status};

use crate::reck::{
    act_service_server::ActService, ActionAck, ActionProposal, RevertRequest,
};

pub struct ActServiceImpl {
    mqtt_client: AsyncClient,
    pub connected: Arc<AtomicBool>,
}

impl ActServiceImpl {
    pub async fn new(host: &str, port: u16) -> (Self, rumqttc::EventLoop) {
        let mut mqttoptions = MqttOptions::new("reck-core-act", host, port);
        mqttoptions.set_keep_alive(Duration::from_secs(5));
        let (client, eventloop) = AsyncClient::new(mqttoptions, 10);
        let connected = Arc::new(AtomicBool::new(false));
        (Self { mqtt_client: client, connected }, eventloop)
    }
}

#[tonic::async_trait]
impl ActService for ActServiceImpl {
    async fn execute_action(
        &self,
        request: Request<ActionProposal>,
    ) -> Result<Response<ActionAck>, Status> {
        if !self.connected.load(Ordering::Relaxed) {
            tracing::warn!(
                error_code = "MQTT_UNAVAILABLE",
                "execute_action rejected: broker unreachable"
            );
            return Err(Status::unavailable("MQTT broker unreachable"));
        }

        let proposal = request.into_inner();
        let topic = format!("{}/cmd", proposal.target);
        let payload = proposal.proposed_value.to_string();

        match self.mqtt_client.publish(topic, QoS::AtLeastOnce, false, payload).await {
            Ok(_) => Ok(Response::new(ActionAck {
                success: true,
                error: "".to_string(),
            })),
            Err(e) => {
                tracing::warn!(error = %e, error_code = "MQTT_PUBLISH_FAILED", "execute_action publish failed");
                Err(Status::internal("MQTT_PUBLISH_FAILED"))
            }
        }
    }

    async fn revert_action(
        &self,
        request: Request<RevertRequest>,
    ) -> Result<Response<ActionAck>, Status> {
        if !self.connected.load(Ordering::Relaxed) {
            tracing::warn!(
                error_code = "MQTT_UNAVAILABLE",
                "revert_action rejected: broker unreachable"
            );
            return Err(Status::unavailable("MQTT broker unreachable"));
        }

        let req = request.into_inner();
        let topic = format!("{}/cmd", req.target);
        let payload = req.original_value.to_string();

        match self.mqtt_client.publish(topic, QoS::AtLeastOnce, false, payload).await {
            Ok(_) => Ok(Response::new(ActionAck {
                success: true,
                error: "".to_string(),
            })),
            Err(e) => {
                tracing::warn!(error = %e, error_code = "MQTT_REVERT_FAILED", "revert_action publish failed");
                Err(Status::internal("MQTT_REVERT_FAILED"))
            }
        }
    }
}
