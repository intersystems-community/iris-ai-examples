# Billing — PlanetCare Knowledge Base

*Last updated: 2025-11-12 | Maintainer: Support Team*

## Overview

PC-Finance handles all billing operations including claim generation, insurance submission, 
invoice management, and revenue cycle workflows.

---

## KB-PC-0001: How to Resubmit a Rejected Claim

**Applies to:** PC-Finance 4.x  
**Category:** Claims Management

**Problem:** Insurance claim rejected with error code CO-4 or CO-97.

**Resolution:**
1. Navigate to PC-Finance > Claims > Rejected Queue
2. Open the rejected claim and review the rejection reason
3. Correct the identified field (diagnosis code, CPT code, or patient eligibility)
4. Click "Resubmit" and confirm the updated claim details
5. Monitor the resubmission in Claims > Pending

**Prevention:** Enable pre-submission eligibility verification in PC-Finance Settings.

---

## KB-PC-0002: Invoice Not Printing After Billing Run

**Applies to:** PC-Finance 4.1+  
**Category:** Invoice Generation

**Problem:** Batch billing run completes but invoices do not appear in the print queue.

**Resolution:**
1. Check PC-PrintService status in System > Services
2. Verify the invoice template is assigned to the correct billing group
3. Re-run the billing batch with "Force Print" option enabled

---

## Knowledge Gaps

The following issue types have been reported but do not yet have KB articles:

- Discount amount mismatches across billing documents *(recurring — see tickets PC-00013 through PC-00040)*
- Batch billing errors causing payment delays *(multiple hospitals affected)*
- Insurance payment delays for specific payer codes

*These gaps will be filled automatically by the KB Mining pipeline.*
