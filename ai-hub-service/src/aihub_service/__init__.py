"""AI Hub Service — agents as a service for IRIS applications.

A REST service that fronts IRIS AI Hub: a tool catalog, an agent runtime, and a
governance layer (roles, human approval, audit trail) behind one versioned HTTP
contract. Callers never import an SDK; an ObjectScript app on any IRIS version
calls it over HTTP, and each tool is bound to whichever IRIS instance actually
holds the logic or the data.

See ../../DESIGN.md for why this exists and how the pieces fit.
"""

__version__ = "0.1.0"
