use glob::Pattern;
use serde::Deserialize;
use std::path::Path;
use tonic::{Request, Response, Status};

use crate::reck::{guard_service_server::GuardService, ActionProposal, ConstraintResult, Verdict};

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
                    let reason = format!(
                        "proposed value {} below minimum {} {}",
                        proposal.proposed_value, c.min, c.unit
                    );
                    tracing::warn!(
                        action_id = %proposal.action_id,
                        constraint = %c.parameter,
                        error_code = "CONSTRAINT_FAIL",
                        reason = %reason,
                        "guard rejected proposal"
                    );
                    return Ok(Response::new(ConstraintResult {
                        action_id: proposal.action_id,
                        verdict: Verdict::Fail as i32,
                        violated_constraint: c.parameter.clone(),
                        reason,
                    }));
                }

                if proposal.proposed_value > c.max {
                    let reason = format!(
                        "proposed value {} exceeds maximum {} {}",
                        proposal.proposed_value, c.max, c.unit
                    );
                    tracing::warn!(
                        action_id = %proposal.action_id,
                        constraint = %c.parameter,
                        error_code = "CONSTRAINT_FAIL",
                        reason = %reason,
                        "guard rejected proposal"
                    );
                    return Ok(Response::new(ConstraintResult {
                        action_id: proposal.action_id,
                        verdict: Verdict::Fail as i32,
                        violated_constraint: c.parameter.clone(),
                        reason,
                    }));
                }

                // Rate of change check
                if proposal.delta.abs() > c.rate_of_change {
                    let reason = format!(
                        "delta {} exceeds rate-of-change limit {}",
                        proposal.delta.abs(),
                        c.rate_of_change
                    );
                    tracing::warn!(
                        action_id = %proposal.action_id,
                        constraint = %c.parameter,
                        error_code = "CONSTRAINT_FAIL",
                        reason = %reason,
                        "guard rejected proposal"
                    );
                    return Ok(Response::new(ConstraintResult {
                        action_id: proposal.action_id,
                        verdict: Verdict::Fail as i32,
                        violated_constraint: c.parameter.clone(),
                        reason,
                    }));
                }

                // Approval check
                if c.requires_approval {
                    tracing::warn!(
                        action_id = %proposal.action_id,
                        constraint = %c.parameter,
                        error_code = "CONSTRAINT_ESCALATE",
                        "guard escalated proposal"
                    );
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
        tracing::debug!(action_id = %proposal.action_id, "guard passed proposal");
        Ok(Response::new(ConstraintResult {
            action_id: proposal.action_id,
            verdict: Verdict::Pass as i32,
            violated_constraint: "".to_string(),
            reason: "".to_string(),
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    fn test_constraints_yaml() -> NamedTempFile {
        let mut f = NamedTempFile::new().unwrap();
        write!(
            f,
            r#"constraints:
  - parameter: "*/temperature_sp"
    min: 160.0
    max: 230.0
    unit: celsius
    rate_of_change: 10.0
  - parameter: "*/pressure_sp"
    min: 1.0
    max: 10.0
    unit: bar
    rate_of_change: 2.0
"#
        )
        .unwrap();
        f
    }

    fn make_proposal(target: &str, proposed: f64, delta: f64) -> ActionProposal {
        ActionProposal {
            action_id: "test-001".to_string(),
            source: "test/signal".to_string(),
            target: target.to_string(),
            delta,
            previous_value: proposed - delta,
            proposed_value: proposed,
            rule_name: "test_rule".to_string(),
            confidence: 0.9,
            lifecycle: 0,
            action_chain_id: "chain-001".to_string(),
            rollback_window_s: 60,
        }
    }

    #[tokio::test]
    async fn test_pass_within_bounds() {
        let f = test_constraints_yaml();
        let svc = GuardServiceImpl::from_yaml(f.path()).unwrap();
        let req = Request::new(make_proposal(
            "site1/extruder/zone_1/temperature_sp",
            200.0,
            5.0,
        ));
        let res = svc.validate_proposal(req).await.unwrap().into_inner();
        assert_eq!(res.verdict, Verdict::Pass as i32);
    }

    #[tokio::test]
    async fn test_fail_below_min() {
        let f = test_constraints_yaml();
        let svc = GuardServiceImpl::from_yaml(f.path()).unwrap();
        let req = Request::new(make_proposal(
            "site1/extruder/zone_1/temperature_sp",
            150.0,
            -5.0,
        ));
        let res = svc.validate_proposal(req).await.unwrap().into_inner();
        assert_eq!(res.verdict, Verdict::Fail as i32);
        assert!(res.reason.contains("below minimum"));
    }

    #[tokio::test]
    async fn test_fail_above_max() {
        let f = test_constraints_yaml();
        let svc = GuardServiceImpl::from_yaml(f.path()).unwrap();
        let req = Request::new(make_proposal(
            "site1/extruder/zone_1/temperature_sp",
            240.0,
            5.0,
        ));
        let res = svc.validate_proposal(req).await.unwrap().into_inner();
        assert_eq!(res.verdict, Verdict::Fail as i32);
        assert!(res.reason.contains("exceeds maximum"));
    }

    #[tokio::test]
    async fn test_fail_rate_of_change() {
        let f = test_constraints_yaml();
        let svc = GuardServiceImpl::from_yaml(f.path()).unwrap();
        let req = Request::new(make_proposal(
            "site1/extruder/zone_1/temperature_sp",
            200.0,
            15.0,
        ));
        let res = svc.validate_proposal(req).await.unwrap().into_inner();
        assert_eq!(res.verdict, Verdict::Fail as i32);
        assert!(res.reason.contains("rate-of-change"));
    }

    #[tokio::test]
    async fn test_pass_unmatched_target() {
        let f = test_constraints_yaml();
        let svc = GuardServiceImpl::from_yaml(f.path()).unwrap();
        // A target that matches no constraint pattern passes by default
        let req = Request::new(make_proposal("site1/conveyor/speed_sp", 999.0, 100.0));
        let res = svc.validate_proposal(req).await.unwrap().into_inner();
        assert_eq!(res.verdict, Verdict::Pass as i32);
    }

    #[tokio::test]
    async fn test_pressure_constraint() {
        let f = test_constraints_yaml();
        let svc = GuardServiceImpl::from_yaml(f.path()).unwrap();
        // Within bounds
        let req = Request::new(make_proposal("site1/pump/pressure_sp", 5.0, 1.0));
        let res = svc.validate_proposal(req).await.unwrap().into_inner();
        assert_eq!(res.verdict, Verdict::Pass as i32);
        // Exceeds max
        let req = Request::new(make_proposal("site1/pump/pressure_sp", 12.0, 1.0));
        let res = svc.validate_proposal(req).await.unwrap().into_inner();
        assert_eq!(res.verdict, Verdict::Fail as i32);
    }
}
