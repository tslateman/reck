use rumqttc::{AsyncClient, MqttOptions, QoS};
use std::time::Duration;
use tonic::{Request, Response, Status};

use crate::reck::{
    act_service_server::ActService, ActionAck, ActionProposal, RevertRequest,
};

pub struct ActServiceImpl {
    mqtt_client: AsyncClient,
}

impl ActServiceImpl {
    pub async fn new(host: &str, port: u16) -> (Self, rumqttc::EventLoop) {
        let mut mqttoptions = MqttOptions::new("reck-core-act", host, port);
        mqttoptions.set_keep_alive(Duration::from_secs(5));

        let (client, eventloop) = AsyncClient::new(mqttoptions, 10);
        (Self { mqtt_client: client }, eventloop)
    }
}

#[tonic::async_trait]
impl ActService for ActServiceImpl {
    async fn execute_action(
        &self,
        request: Request<ActionProposal>,
    ) -> Result<Response<ActionAck>, Status> {
        let proposal = request.into_inner();
        let topic = format!("{}/cmd", proposal.target);
        let payload = proposal.proposed_value.to_string();

        match self.mqtt_client.publish(topic, QoS::AtLeastOnce, false, payload).await {
            Ok(_) => Ok(Response::new(ActionAck {
                success: true,
                error: "".to_string(),
            })),
            Err(e) => Ok(Response::new(ActionAck {
                success: false,
                error: format!("MQTT publish failed: {}", e),
            })),
        }
    }

    async fn revert_action(
        &self,
        request: Request<RevertRequest>,
    ) -> Result<Response<ActionAck>, Status> {
        let req = request.into_inner();
        let topic = format!("{}/cmd", req.target);
        let payload = req.original_value.to_string();

        match self.mqtt_client.publish(topic, QoS::AtLeastOnce, false, payload).await {
            Ok(_) => Ok(Response::new(ActionAck {
                success: true,
                error: "".to_string(),
            })),
            Err(e) => Ok(Response::new(ActionAck {
                success: false,
                error: format!("MQTT revert failed: {}", e),
            })),
        }
    }
}
