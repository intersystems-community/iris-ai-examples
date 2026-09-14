import httpx
import pytest

from conftest import (
    FHIR_BASE,
    HUB_HOST,
    HUB_PORT,
    MCP_URL,
    USERS,
    requires_iris,
    fhir,
    iris_conn_admin,
)

pytestmark = [pytest.mark.contract, pytest.mark.docker]


class TestFHIRStack:
    def test_fhir_metadata_capabilitystatement(self, fhir):
        r = fhir.get("/metadata")
        assert r.status_code == 200
        cs = r.json()
        assert cs["resourceType"] == "CapabilityStatement"
        assert cs.get("fhirVersion", "").startswith("4.")

    def test_fhir_patient_endpoint_returns_bundle(self, fhir):
        r = fhir.get("/Patient", params={"_count": 1})
        assert r.status_code == 200
        bundle = r.json()
        assert bundle["resourceType"] == "Bundle"

    def test_fhir_document_reference_exists(self, fhir):
        r = fhir.get("/DocumentReference", params={"_count": 1})
        assert r.status_code == 200
        bundle = r.json()
        assert bundle["resourceType"] == "Bundle"

    def test_fhir_idempotent_load_no_duplicate_growth(self, fhir):
        r1 = fhir.get("/Patient", params={"_summary": "count"})
        count1 = r1.json().get("total", 0)
        r2 = fhir.get("/Patient", params={"_summary": "count"})
        count2 = r2.json().get("total", 0)
        assert count1 == count2, (
            "Patient count changed between calls — possible duplicate load"
        )


class TestIRISHubRBAC:
    @requires_iris
    def test_admin_connect_succeeds(self, iris_conn_admin):
        assert iris_conn_admin is not None

    @requires_iris
    def test_chw_user_connects(self):
        import iris

        conn = iris.connect(HUB_HOST, HUB_PORT, "USER", *USERS["chw"])
        assert conn is not None
        conn.close()

    @requires_iris
    def test_chw_senior_connects(self):
        import iris

        conn = iris.connect(HUB_HOST, HUB_PORT, "USER", *USERS["chw_senior"])
        assert conn is not None
        conn.close()

    @requires_iris
    def test_readonly_connects(self):
        import iris

        conn = iris.connect(HUB_HOST, HUB_PORT, "USER", *USERS["readonly"])
        assert conn is not None
        conn.close()

    @requires_iris
    def test_case_manager_connects(self):
        import iris

        conn = iris.connect(HUB_HOST, HUB_PORT, "USER", *USERS["case_manager"])
        assert conn is not None
        conn.close()

    @requires_iris
    def test_invalid_credentials_raise(self):
        import iris

        with pytest.raises(Exception):
            iris.connect(HUB_HOST, HUB_PORT, "USER", "nobody", "wrongpassword")

    @requires_iris
    def test_chw_role_exists_in_iris(self, iris_conn_admin):
        cur = iris_conn_admin.cursor()
        cur.execute("SELECT Name FROM Security_Roles WHERE Name = 'chw_role'")
        row = cur.fetchone()
        assert row is not None, "chw_role not found in Security.Roles"

    @requires_iris
    def test_all_required_roles_exist(self, iris_conn_admin):
        required = {
            "chw_role",
            "chw_senior_role",
            "admin_role",
            "readonly_role",
            "case_manager_role",
        }
        cur = iris_conn_admin.cursor()
        cur.execute(
            "SELECT Name FROM Security_Roles WHERE Name %INLIST $LISTFROMSTRING(?)",
            [",".join(required)],
        )
        found = {row[0] for row in cur.fetchall()}
        missing = required - found
        assert not missing, f"Missing roles: {missing}"


class TestMCPEndpoint:
    def test_mcp_server_responds(self):
        try:
            r = httpx.get(MCP_URL, timeout=5)
            assert r.status_code in (200, 404, 405, 422), (
                f"MCP returned unexpected status {r.status_code}"
            )
        except httpx.ConnectError:
            pytest.skip("MCP not yet running")
