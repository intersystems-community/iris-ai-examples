"""Governance: who may do what, and which tool calls wait for a human.

Three decisions, all read from the ``policy:`` block of the config:

* may this principal call the API at all, and which parts of it (roles);
* may they invoke a write tool directly, outside an agent run;
* does a tool call an agent wants to make pause for a named approver.

The approval gate is the point. ``TriggerFollowUp`` fires an Interoperability
production — a real side effect in a clinical system — so the service parks
the run in ``awaiting_approval`` and the call happens only once someone holding
the approver role says yes. The same rule CareConnect's instructions ask the
model to follow ("a human must confirm") is enforced here, where a model that
ignores its instructions cannot get past it.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_POLICY = {
    "roles": {
        "list": ["caller", "approver", "admin"],
        "run_agents": ["caller", "approver", "admin"],
        "invoke_read_tools": ["caller", "approver", "admin"],
        "invoke_write_tools": ["approver", "admin"],
        "approve": ["approver", "admin"],
    },
    "approval": {
        # Tool effects whose calls inside an agent run need a human decision.
        "required_for": ["write"],
        # Individual tools can be exempted (safe writes) or added (sensitive reads).
        "exempt_tools": [],
        "extra_tools": [],
    },
}


@dataclass
class Policy:
    roles: dict
    approval: dict

    @classmethod
    def from_config(cls, cfg) -> "Policy":
        raw = cfg.policy or {}
        roles = {**DEFAULT_POLICY["roles"], **raw.get("roles", {})}
        approval = {**DEFAULT_POLICY["approval"], **raw.get("approval", {})}
        return cls(roles=roles, approval=approval)

    def allows(self, principal, action: str) -> bool:
        if principal is None:
            return False
        return bool(principal.roles & set(self.roles.get(action, [])))

    def needs_approval(self, tool) -> bool:
        if tool.name in self.approval.get("exempt_tools", []):
            return False
        if tool.name in self.approval.get("extra_tools", []):
            return True
        return tool.effect in self.approval.get("required_for", [])
