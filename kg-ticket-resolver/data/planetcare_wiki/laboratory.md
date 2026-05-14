# Laboratory — PlanetCare Knowledge Base

*Last updated: 2025-10-08 | Maintainer: Lab Informatics Team*

## Overview

PC-Lab manages laboratory order entry, result routing, specimen tracking, 
and instrument interfaces for clinical laboratory workflows.

---

## KB-PC-0010: Critical Value Notifications Not Triggering

**Applies to:** PC-Lab 4.x  
**Category:** Result Routing

**Problem:** Critical lab values are not generating alerts to clinical staff.

**Resolution:**
1. Verify critical value thresholds in PC-Lab > Configuration > Critical Values
2. Check that the notifying role is assigned to active users
3. Confirm the notification rule is enabled for the affected test type
4. Test with a mock result in the lab sandbox environment

---

## Knowledge Gaps

- Result routing failures when instrument interface disconnects *(frequent — no documented fix)*
- Specimen tracking gaps for STAT orders *(reported by 3 hospitals, unresolved)*

*Run the KB Mining notebook to auto-generate articles for these gaps.*
