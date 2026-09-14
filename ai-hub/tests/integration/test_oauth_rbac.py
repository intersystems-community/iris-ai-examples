"""
Integration tests for Sample.AI.OAuth RBAC example (feature 048-oauth-rbac-example).

Must run inside irispython (embedded Python context) against a live IRIS 2026.3+
instance with the Sample.AI.OAuth.* classes compiled.

Run:
    irispython -m pytest tests/integration/test_oauth_rbac.py -v

Skips automatically when run outside irispython or when SKIP_IRIS_TESTS=true.
"""

import os
import sys
import inspect

import pytest

SKIP_IRIS_TESTS = os.environ.get("SKIP_IRIS_TESTS", "false").lower() == "true"


def _is_embedded() -> bool:
    try:
        import iris  # noqa: F401
        site_pkg = os.path.dirname(os.path.dirname(inspect.getfile(iris)))
        return os.path.exists(os.path.join(site_pkg, "iris_ep.py"))
    except Exception:
        return False


requires_embedded = pytest.mark.skipif(
    not _is_embedded() or SKIP_IRIS_TESTS,
    reason="Must run inside irispython (embedded Python context) with SKIP_IRIS_TESTS=false",
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _metadata(role: str):
    """Build a %DynamicObject with Role=<role> — simulates <Requirement> tag value."""
    import iris
    obj = iris.cls("%Library.DynamicObject")._New()
    obj._Set("Role", role)
    return obj


def _empty_meta():
    """Build an empty %DynamicObject (no Role key) — used instead of None for metadata."""
    import iris
    return iris.cls("%Library.DynamicObject")._New()


def _call_obj(name: str):
    """Build a minimal tools/call %DynamicObject."""
    import iris
    return iris.cls("%Library.DynamicObject")._FromJSON(
        '{"name":"' + name + '","arguments":{}}'
    )


def _is_ok(sc) -> bool:
    import iris
    return bool(iris.cls("%SYSTEM.Status").IsOK(sc))


def _error_text(sc) -> str:
    import iris
    return str(iris.cls("%SYSTEM.Status").GetErrorText(sc))


# ── Phase 2 — RBACPolicy unit tests ─────────────────────────────────────────

@requires_embedded
class TestRBACPolicy:

    def test_can_execute_no_role_required_passes(self):
        """Tool with no Role requirement must always pass %CanExecute (empty metadata)."""
        import iris
        policy = iris.cls("Sample.AI.OAuth.RBACPolicy")._New()
        sc = policy._CanExecute("GetStatus", _call_obj("GetStatus"), _empty_meta())
        assert _is_ok(sc), f"No-role tool must always pass: {_error_text(sc)}"

    def test_can_execute_no_role_required_empty_metadata(self):
        """Empty metadata object (no Role key) must pass %CanExecute."""
        import iris
        policy = iris.cls("Sample.AI.OAuth.RBACPolicy")._New()
        meta = iris.cls("%Library.DynamicObject")._New()
        sc = policy._CanExecute("GetStatus", _call_obj("GetStatus"), meta)
        assert _is_ok(sc), f"Empty metadata must pass: {_error_text(sc)}"

    def test_can_list_no_role_required_passes(self):
        """Tool with no Role metadata must always be listed."""
        import iris
        policy = iris.cls("Sample.AI.OAuth.RBACPolicy")._New()
        result = policy._CanList("GetStatus", _empty_meta())
        assert result == 1, "%CanList with empty metadata must return 1"

    def test_can_list_empty_metadata_passes(self):
        """Empty metadata (no Role key) must be listed."""
        import iris
        policy = iris.cls("Sample.AI.OAuth.RBACPolicy")._New()
        meta = iris.cls("%Library.DynamicObject")._New()
        result = policy._CanList("GetStatus", meta)
        assert result == 1, "%CanList with empty metadata must return 1"

    def test_can_execute_percent_all_grants_access(self):
        """Session with %All must pass %CanExecute for any role-gated tool."""
        import iris
        meta = _metadata("SampleReader")
        policy = iris.cls("Sample.AI.OAuth.RBACPolicy")._New()
        sc = policy._CanExecute("GetStatus", _call_obj("GetStatus"), meta)
        assert _is_ok(sc), f"%All must pass SampleReader gate: {_error_text(sc)}"

    def test_can_list_percent_all_grants_access(self):
        """Session with %All must pass %CanList for any role-gated tool."""
        import iris
        meta = _metadata("SampleReader")
        policy = iris.cls("Sample.AI.OAuth.RBACPolicy")._New()
        result = policy._CanList("GetStatus", meta)
        assert result == 1, f"%All must allow SampleReader-gated tool: got {result}"


# ── Phase 2 — RoleDiscovery unit tests ──────────────────────────────────────

@requires_embedded
class TestRoleDiscovery:

    def _make_tool(self, name: str, role: str = "") -> object:
        """Build a minimal tool descriptor %DynamicObject."""
        import iris
        tool = iris.cls("%Library.DynamicObject")._New()
        tool._Set("name", name)
        if role:
            meta = iris.cls("%Library.DynamicObject")._New()
            meta._Set("Role", role)
            tool._Set("metadata", meta)
        return tool

    def _catalog(self, *tools) -> object:
        """Build a %DynamicArray of tool descriptors."""
        import iris
        arr = iris.cls("%Library.DynamicArray")._New()
        for t in tools:
            arr._Push(t)
        return arr

    def _get_names(self, arr) -> list:
        """Extract names from a %DynamicArray of tool descriptors."""
        import iris
        count = arr._Size()
        return [arr._Get(i)._Get("name") for i in range(count)]

    def test_resolve_returns_a_status_not_a_catalog(self):
        """%Resolve must return %Status — the catalog is modified in place.

        The superclass signature is %Resolve(catalog) As %Status. A version that
        returns %DynamicArray does not compile, and a version named Resolve()
        compiles but is never called. Both were shipped here once.
        """
        import iris
        discovery = iris.cls("Sample.AI.OAuth.RoleDiscovery")._New()
        sc = discovery._Resolve(self._catalog())
        assert _is_ok(sc), f"%Resolve must return OK: {_error_text(sc)}"

    def test_resolve_no_role_tools_always_pass(self):
        """Tools without a Role requirement must survive %Resolve regardless of $Roles."""
        import iris
        discovery = iris.cls("Sample.AI.OAuth.RoleDiscovery")._New()
        catalog = self._catalog(
            self._make_tool("GetStatus"),
            self._make_tool("WriteNote"),
        )
        sc = discovery._Resolve(catalog)
        assert _is_ok(sc), f"%Resolve must return OK: {_error_text(sc)}"
        count = catalog._Size()
        assert count == 2, f"Tools without Role must survive %Resolve: got {count}"

    def test_resolve_empty_catalog_stays_empty(self):
        """Empty catalog must survive %Resolve without error."""
        import iris
        discovery = iris.cls("Sample.AI.OAuth.RoleDiscovery")._New()
        catalog = self._catalog()
        sc = discovery._Resolve(catalog)
        assert _is_ok(sc), f"%Resolve must return OK: {_error_text(sc)}"
        assert catalog._Size() == 0, "Empty catalog must stay empty"


# ── Phase 3 — OAuthMCPService.VerifyPrerequisites ────────────────────────────

@requires_embedded
class TestVerifyPrerequisites:

    def test_verify_fails_cleanly_when_rs_absent(self):
        """VerifyPrerequisites must return $$$ERROR when ResourceServer is absent."""
        import iris
        sc = iris.cls("Sample.AI.OAuth.OAuthMCPService").VerifyPrerequisites(
            "SampleOAuth_XYZ_NotReal_048"
        )
        assert not _is_ok(sc), (
            "VerifyPrerequisites must return error when ResourceServer absent"
        )

    def test_verify_returns_status(self):
        """VerifyPrerequisites must return a %Status (not raise an exception)."""
        import iris
        try:
            sc = iris.cls("Sample.AI.OAuth.OAuthMCPService").VerifyPrerequisites(
                "SampleOAuth_XYZ_NotReal_048"
            )
            assert sc is not None
        except Exception as exc:
            pytest.fail(f"VerifyPrerequisites raised an exception: {exc}")


# ── Phase 6 — Setup.PrintChecklist ───────────────────────────────────────────

@requires_embedded
class TestSetup:

    def test_print_checklist_returns_ok(self):
        """PrintChecklist must return $$$OK without raising."""
        import iris
        try:
            sc = iris.cls("Sample.AI.OAuth.Setup").PrintChecklist("SampleOAuth")
            assert _is_ok(sc), f"PrintChecklist must return OK: {_error_text(sc)}"
        except Exception as exc:
            pytest.fail(f"PrintChecklist raised: {exc}")

    def test_create_skeleton_is_callable(self):
        """CreateSkeleton must not raise even on a namespace with no OAuth2 records.

        Smoke test — we do not assert record creation because %SYS write may not
        be permitted in all embedded contexts.
        """
        import iris
        try:
            sc = iris.cls("Sample.AI.OAuth.Setup").CreateSkeleton(
                "SampleOAuth_Test_048_Transient"
            )
            assert sc is not None
        except Exception as exc:
            pytest.fail(f"CreateSkeleton raised unexpectedly: {exc}")


# ── Mock-based deny/allow path tests (no $Roles manipulation) ────────────────
#
# Test.MockRBACPolicy and Test.MockRoleDiscovery override GetCallerRoles() so
# the role check is deterministic regardless of the session's $Roles value.
# These cover the deny and allow branches that the embedded SuperUser session
# cannot reach (because $Roles always contains %All for that user).

@requires_embedded
class TestRBACPolicyMocked:
    """Deterministic RBAC tests using Test.MockRBACPolicy."""

    def _mock_policy(self, roles: str):
        import iris
        p = iris.cls("Test.MockRBACPolicy")._New()
        p.MockRoles = roles
        return p

    def test_can_execute_denies_when_role_absent(self):
        """%CanExecute must deny when required role not in MockRoles."""
        policy = self._mock_policy("SampleReader")
        sc = policy._CanExecute("WriteNote", _call_obj("WriteNote"), _metadata("SampleWriter"))
        assert not _is_ok(sc), "%CanExecute must deny SampleWriter for SampleReader session"
        err = _error_text(sc)
        assert "SampleWriter" in err or "Role" in err or "required" in err.lower(), (
            f"Error must name the missing role: {err}"
        )

    def test_can_execute_allows_when_role_present(self):
        """%CanExecute must pass when required role is in MockRoles."""
        policy = self._mock_policy("SampleReader,SampleWriter")
        sc = policy._CanExecute("WriteNote", _call_obj("WriteNote"), _metadata("SampleWriter"))
        assert _is_ok(sc), f"%CanExecute must pass when role present: {_error_text(sc)}"

    def test_can_execute_allows_percent_all(self):
        """%CanExecute must pass for any role when MockRoles contains %All."""
        policy = self._mock_policy("%All")
        sc = policy._CanExecute("AdminReset", _call_obj("AdminReset"), _metadata("SampleAdmin"))
        assert _is_ok(sc), f"%All must bypass role gate: {_error_text(sc)}"

    def test_can_execute_denies_empty_roles(self):
        """%CanExecute must deny when MockRoles is empty and a role is required."""
        policy = self._mock_policy("")
        sc = policy._CanExecute("GetStatus", _call_obj("GetStatus"), _metadata("SampleReader"))
        assert not _is_ok(sc), "%CanExecute must deny when no roles and role is required"

    def test_can_list_denies_when_role_absent(self):
        """%CanList must return 0 when required role not in MockRoles."""
        policy = self._mock_policy("SampleReader")
        result = policy._CanList("AdminReset", _metadata("SampleAdmin"))
        assert result == 0, f"%CanList must return 0 for missing role: got {result}"

    def test_can_list_allows_when_role_present(self):
        """%CanList must return 1 when required role is in MockRoles."""
        policy = self._mock_policy("SampleAdmin")
        result = policy._CanList("AdminReset", _metadata("SampleAdmin"))
        assert result == 1, f"%CanList must return 1 when role present: got {result}"

    def test_can_list_allows_percent_all(self):
        """%CanList must return 1 for any role when MockRoles contains %All."""
        policy = self._mock_policy("%All")
        result = policy._CanList("AdminReset", _metadata("SampleAdmin"))
        assert result == 1, f"%All must allow any tool: got {result}"

    def test_can_list_denies_empty_roles(self):
        """%CanList must return 0 when MockRoles is empty and a role is required."""
        policy = self._mock_policy("")
        result = policy._CanList("GetStatus", _metadata("SampleReader"))
        assert result == 0, f"%CanList must deny when no roles: got {result}"

    def test_error_message_names_required_role(self):
        """The denial error from %CanExecute must name the required role and tool."""
        policy = self._mock_policy("")
        sc = policy._CanExecute("WriteNote", _call_obj("WriteNote"), _metadata("SampleWriter"))
        err = _error_text(sc)
        assert "WriteNote" in err or "SampleWriter" in err, (
            f"Error must reference the tool or role: {err}"
        )


@requires_embedded
class TestRoleDiscoveryMocked:
    """Deterministic %Resolve() tests using Test.MockRoleDiscovery."""

    def _make_tool(self, name: str, role: str = "") -> object:
        import iris
        tool = iris.cls("%Library.DynamicObject")._New()
        tool._Set("name", name)
        if role:
            meta = iris.cls("%Library.DynamicObject")._New()
            meta._Set("Role", role)
            tool._Set("metadata", meta)
        return tool

    def _catalog(self, *tools) -> object:
        import iris
        arr = iris.cls("%Library.DynamicArray")._New()
        for t in tools:
            arr._Push(t)
        return arr

    def _get_names(self, arr) -> list:
        return [arr._Get(i)._Get("name") for i in range(arr._Size())]

    def _mock_discovery(self, roles: str):
        import iris
        d = iris.cls("Test.MockRoleDiscovery")._New()
        d.MockRoles = roles
        return d

    def _filtered(self, roles: str, *tools) -> list:
        """Run %Resolve for a role string and return the surviving tool names."""
        discovery = self._mock_discovery(roles)
        catalog = self._catalog(*tools)
        sc = discovery._Resolve(catalog)
        assert _is_ok(sc), f"%Resolve must return OK: {_error_text(sc)}"
        return self._get_names(catalog)

    def test_empty_roles_filters_all_gated_tools(self):
        """%Resolve with empty roles must exclude all role-gated tools."""
        names = self._filtered(
            "",
            self._make_tool("GetStatus", "SampleReader"),
            self._make_tool("WriteNote", "SampleWriter"),
            self._make_tool("AdminReset", "SampleAdmin"),
        )
        assert names == [], f"Empty roles must filter all gated tools: got {names}"

    def test_empty_roles_passes_ungated_tools(self):
        """%Resolve with empty roles must include tools with no Role requirement."""
        names = self._filtered(
            "",
            self._make_tool("Ping"),
            self._make_tool("GetStatus", "SampleReader"),
        )
        assert names == ["Ping"], f"Only ungated Ping must survive: got {names}"

    def test_reader_role_shows_only_reader_tools(self):
        """SampleReader session must see only SampleReader-gated tools."""
        names = self._filtered(
            "SampleReader",
            self._make_tool("GetStatus", "SampleReader"),
            self._make_tool("WriteNote", "SampleWriter"),
            self._make_tool("AdminReset", "SampleAdmin"),
        )
        assert names == ["GetStatus"], f"Reader must see only GetStatus: got {names}"

    def test_multi_role_session_sees_multiple_tools(self):
        """Session with Reader+Writer roles must see both Reader and Writer tools."""
        names = self._filtered(
            "SampleReader,SampleWriter",
            self._make_tool("GetStatus", "SampleReader"),
            self._make_tool("WriteNote", "SampleWriter"),
            self._make_tool("AdminReset", "SampleAdmin"),
        )
        assert set(names) == {"GetStatus", "WriteNote"}, (
            f"Reader+Writer must see GetStatus+WriteNote: got {names}"
        )

    def test_removal_preserves_the_order_of_survivors(self):
        """Filtering walks the array backwards; survivors must keep catalog order."""
        names = self._filtered(
            "SampleReader,SampleAdmin",
            self._make_tool("GetStatus", "SampleReader"),
            self._make_tool("WriteNote", "SampleWriter"),
            self._make_tool("AdminReset", "SampleAdmin"),
        )
        assert names == ["GetStatus", "AdminReset"], (
            f"%Remove() must not scramble surviving order: got {names}"
        )

    def test_percent_all_leaves_full_catalog(self):
        """%All role must leave the catalog unfiltered."""
        names = self._filtered(
            "%All",
            self._make_tool("GetStatus", "SampleReader"),
            self._make_tool("WriteNote", "SampleWriter"),
            self._make_tool("AdminReset", "SampleAdmin"),
        )
        assert len(names) == 3, f"%All must keep all 3 tools: got {names}"

    def test_ungated_tools_always_included(self):
        """Tools with no Role requirement survive regardless of roles."""
        names = self._filtered(
            "",
            self._make_tool("Ping"),
            self._make_tool("Health"),
            self._make_tool("AdminReset", "SampleAdmin"),
        )
        assert "Ping" in names and "Health" in names, (
            f"Ungated tools must always be included: got {names}"
        )
