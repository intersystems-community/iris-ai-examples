/// CareConnect Contradiction Gate Skill
///
/// Packages the "refuses to guess" governance behavior as a reusable
/// %AI.Agent.Skill. Load this into any agent that cites clinical protocols
/// and the gate behavior is automatically active — no per-agent wiring needed.
///
/// Usage (one line):
///   $$$ThrowOnError(agent.UseSkill("CareConnect.Skill.ContradictionGate"))
///
/// The skill contributes:
///   - INSTRUCTIONS: the full gate policy injected into the agent's system prompt
///   - Requires: CareConnect.Tools.SDoHToolSet (CheckProtocolContradictions,
///               GetKnowledgeContext, GroundAnswerWithCitations) registered separately
///
/// Prerequisite:
///   IVG stack running: docker compose --profile ivg up -d --wait
///   (seeds 3 demo contradictions — gate fires out of the box)
///
/// Compare to Sample.AI.Skill.Echo — same mechanism, higher stakes:
///   Echo teaches formatting. This skill encodes a governance policy.
Class CareConnect.Skill.ContradictionGate Extends %AI.Agent.Skill
{

/// YAML metadata — name + description used for skill discovery
XData SUMMARY [ MimeType = "text/yaml" ]
{
name: contradiction-gate
description: Blocks clinical recommendations when unresolved guideline contradictions exist. Encodes the "refuses to guess" governance policy for SDoH protocol citations.
tags:
  - careconnect
  - sdoh
  - governance
  - clinical
  - knowledge-graph
}

/// Gate instructions injected into the agent's system prompt.
/// Identical logic to SDoHAssessment.cls INSTRUCTIONS — extracted here
/// so any agent can load it without subclassing SDoHAssessment.
XData INSTRUCTIONS [ MimeType = "text/markdown" ]
{
## Contradiction gate — MANDATORY before citing any clinical protocol

You have access to a persistent knowledge graph (IVG) that tracks governing
decisions and known contradictions for SDoH clinical guidelines.

### Before citing ANY screening threshold, referral rule, or clinical guideline:

1. Call **CheckProtocolContradictions** with the concept name
   (e.g. "food insecurity screening", "housing instability threshold",
   "depression screening instrument")

2. If the result starts with `BLOCKED`:
   - Do **NOT** choose between the conflicting guidelines
   - Do **NOT** prefer the more recent document — recency is not applicability
   - Respond exactly: "I cannot make a protocol recommendation for [concept] —
     conflicting guidelines exist. Human review required before I can proceed."
   - Include the full contradiction details from the tool result
   - **Stop** — do not draft a care plan for that domain until resolved

3. If the result starts with `NO_CONTRADICTIONS`, proceed normally

### Before drafting any care plan section:

Call **GetKnowledgeContext** to retrieve governing decisions with full source
provenance. Every recommendation must trace to a source returned by this tool.
Never invent or paraphrase a guideline.

### Optional: quote-level citation verification

After drafting, call **GroundAnswerWithCitations** to verify claims against
verbatim source quotes and add inline [SOURCE: ...] citations.
Only active when PARSELTONGUE_GROUNDING=true — safe to call always.
}

}
