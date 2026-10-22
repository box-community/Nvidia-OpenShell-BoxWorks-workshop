# Support Risk Playbook

The prediction skill estimates whether an account is likely to need support intervention.

Signals include account tier, open cases, average case age, recent priority cases, and renewal proximity.

## Recommended Action

If predicted risk is high, retrieve the current support policy and produce a cited recommendation. The recommendation should include the risk evidence, the policy citation, and a next step for the support owner.

## Workshop Scope

The local fallback returns a deterministic score so the workshop runs without credentials. The production swap uses NVIDIA Kumo Relational for prediction over tabular or relational account data.
