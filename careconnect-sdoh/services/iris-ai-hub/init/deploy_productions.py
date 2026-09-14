"""
Deploy CareConnect pyprod productions into IRIS.
Run via: irispython /init/deploy_productions.py
Requires Embedded Python (runs inside IRIS container).
"""
import sys
import os

sys.path.insert(0, "/src/CareConnect/productions")
sys.path.insert(0, "/src/CareConnect")

def deploy(cls_name, module_name):
    try:
        mod = __import__(module_name)
        cls = getattr(mod, cls_name)
        result = cls.deploy(force=True, dry_run=False)
        print(f"OK: {cls_name} deployed — {result}")
        return True
    except Exception as e:
        print(f"WARN: {cls_name} deploy failed — {e}")
        return False

if __name__ == "__main__":
    deploy("PatientOnboardingProd", "patient_onboarding")
    deploy("SDoHFollowUpProd", "sdoh_followup")
    print("Production deployment complete")
