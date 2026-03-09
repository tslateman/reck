use glob::Pattern;
use serde::Deserialize;
use std::path::Path;
use tonic::{Request, Response, Status};

use crate::reck::{
    guard_service_server::GuardService, ActionProposal, ConstraintResult, Verdict,
};

#[derive(Debug, Deserialize)]
struct ConstraintEntry {
    parameter: String,
    min: f64,
    max: f64,
    unit: String,
    rate_of_change: f64,
    #[serde(default)]
    requires_approval: bool,
}

#[derive(Debug, Deserialize)]
struct ConstraintConfig {
    constraints: Vec<ConstraintEntry>,
}

pub struct GuardServiceImpl {
    constraints: Vec<ConstraintEntry>,
}

impl GuardServiceImpl {
    pub fn from_yaml(path: &Path) -> Result<Self, Box<dyn std::error::Error>> {
        let f = std::fs::File::open(path)?;
        let config: ConstraintConfig = serde_yaml::from_reader(f)?;
        Ok(Self {
            constraints: config.constraints,
        })
    }
}

#[tonic::async_trait]
impl GuardService for GuardServiceImpl {
    async fn validate_proposal(
        &self,
        request: Request<ActionProposal>,
    ) -> Result<Response<ConstraintResult>, Status> {
        let proposal = request.into_inner();
        let target = &proposal.target;

        for c in &self.constraints {
            // Check if glob matches target
            if let Ok(pattern) = Pattern::new(&c.parameter) {
                if !pattern.matches(target) {
                    continue;
                }

                // Min/Max check
                if proposal.proposed_value < c.min {
                    return Ok(Response::new(ConstraintResult {
                        action_id: proposal.action_id,
                        verdict: Verdict::Fail as i32,
                        violated_constraint: c.parameter.clone(),
                        reason: format!(
                            "proposed value {} below minimum {} {}",
                            proposal.proposed_value, c.min, c.unit
                        ),
                    }));
                }

                if proposal.proposed_value > c.max {
                    return Ok(Response::new(ConstraintResult {
                        action_id: proposal.action_id,
                        verdict: Verdict::Fail as i32,
                        violated_constraint: c.parameter.clone(),
                        reason: format!(
                            "proposed value {} exceeds maximum {} {}",
                            proposal.proposed_value, c.max, c.unit
                        ),
                    }));
                }

                // Rate of change check
                if proposal.delta.abs() > c.rate_of_change {
                    return Ok(Response::new(ConstraintResult {
                        action_id: proposal.action_id,
                        verdict: Verdict::Fail as i32,
                        violated_constraint: c.parameter.clone(),
                        reason: format!(
                            "delta {} exceeds rate-of-change limit {}",
                            proposal.delta.abs(),
                            c.rate_of_change
                        ),
                    }));
                }

                // Approval check
                if c.requires_approval {
                    return Ok(Response::new(ConstraintResult {
                        action_id: proposal.action_id,
                        verdict: Verdict::Escalate as i32,
                        violated_constraint: c.parameter.clone(),
                        reason: "constraint requires human approval".to_string(),
                    }));
                }
            }
        }

        // PASS if no constraints failed
        Ok(Response::new(ConstraintResult {
            action_id: proposal.action_id,
            verdict: Verdict::Pass as i32,
            violated_constraint: "".to_string(),
            reason: "".to_string(),
        }))
    }
}
