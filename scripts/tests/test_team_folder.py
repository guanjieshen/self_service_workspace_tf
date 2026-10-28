"""terraform/modules/folders/team_folder.py: a workspace folder on request.

The notebook runs top to bottom, so each test runs it with stand-ins for dbutils and the
Databricks SDK and checks what it does to the workspace.
"""
import json
import sys
import types
import unittest

from helpers import ROOT, render_notebook

NOTEBOOK = (ROOT / "terraform/modules/folders/team_folder.py").read_text()
CONFIG = {"root": "/Workspace"}
ME = "ana@contoso.com"



class Exit(Exception):
    """dbutils.notebook.exit: ends the run, successfully."""


class NotFound(Exception):
    pass


class FakeWorkspace:
    """Users (with their groups), groups, service principals and folders."""

    def __init__(self, folders=None):
        self.users_ = {ME: ["fin-data-eng", "fin_builder"], "bo@contoso.com": []}
        self.groups_ = {"fin-data-eng", "fin_builder", "fin-finance"}
        self.sps = {"11111111-2222-3333-4444-555555555555"}
        self.folders = dict(folders or {})   # path -> (object_id, acl)
        self.made, self.patched = [], []
        name = lambda f: f.split('"')[1]
        self.users = types.SimpleNamespace(list=lambda filter, attributes: [
            types.SimpleNamespace(groups=[types.SimpleNamespace(display=g) for g in self.users_[name(filter)]])
        ] if name(filter) in self.users_ else [])
        self.groups = types.SimpleNamespace(list=lambda filter, attributes: [object()] if name(filter) in self.groups_ else [])
        self.service_principals = types.SimpleNamespace(list=lambda filter, attributes: [object()] if name(filter) in self.sps else [])
        self.workspace = types.SimpleNamespace(mkdirs=self.mkdirs, get_status=self.get_status)
        self.api_client = types.SimpleNamespace(do=self.do)

    def mkdirs(self, path):
        self.made.append(path)
        self.folders[path] = (42, [])

    def get_status(self, path):
        if path not in self.folders:
            raise NotFound(path)
        return types.SimpleNamespace(object_id=self.folders[path][0])

    def do(self, method, path, body=None):
        if method == "GET":
            return {"access_control_list": next(acl for oid, acl in self.folders.values() if path.endswith(f"/{oid}"))}
        self.patched.append((path, body["access_control_list"]))


def run(params, w, config=None):
    """Run the notebook against the fake workspace w; returns the exit value."""
    values = {"requested_by": ME, **params}
    out = {}

    def exit_(value):
        out["value"] = json.loads(value)
        raise Exit

    dbutils = types.SimpleNamespace(
        widgets=types.SimpleNamespace(text=lambda name, default: None, get=lambda name: values.get(name, "")),
        notebook=types.SimpleNamespace(exit=exit_))
    sdk, errors = types.ModuleType("databricks.sdk"), types.ModuleType("databricks.sdk.errors")
    sdk.WorkspaceClient, errors.NotFound = (lambda: w), NotFound
    names = ("databricks", "databricks.sdk", "databricks.sdk.errors")
    saved = {k: sys.modules.get(k) for k in names}
    sys.modules.update(dict(zip(names, (types.ModuleType("databricks"), sdk, errors))))
    try:
        exec(compile(render_notebook(NOTEBOOK, {**CONFIG, **(config or {})}), "team_folder.py", "exec"),
             {"dbutils": dbutils})
    except Exit:
        pass
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return out.get("value")


class WorkspaceFolder(unittest.TestCase):
    def test_the_requester_and_their_group_can_manage_it(self):
        w = FakeWorkspace()
        result = run({"folder": "fin-docs", "owner_group": "fin-data-eng", "request_id": "ss-1"}, w)
        self.assertEqual((result["path"], result["owner_group"]), ("/Workspace/fin-docs", "fin-data-eng"))
        self.assertEqual(w.made, ["/Workspace/fin-docs"])
        self.assertEqual(w.patched, [("/api/2.0/permissions/directories/42", [
            {"user_name": ME, "permission_level": "CAN_MANAGE"},
            {"group_name": "fin-data-eng", "permission_level": "CAN_MANAGE"}])],
            "PATCH adds the permissions; it never replaces the folder's others")

    def test_the_reason_is_kept_with_the_run(self):
        result = run({"folder": "fin-docs", "reason": "Notebooks for the month-end close."}, FakeWorkspace())
        self.assertEqual(result["reason"], "Notebooks for the month-end close.")
        with self.assertRaisesRegex(ValueError, "at most 1000 characters"):
            run({"folder": "fin-docs", "reason": "x" * 1001}, FakeWorkspace())

    def test_without_a_group_only_the_requester_can_manage_it(self):
        w = FakeWorkspace()
        run({"folder": "fin-docs"}, w)
        self.assertEqual(w.patched[0][1], [{"user_name": ME, "permission_level": "CAN_MANAGE"}])

    def test_the_group_must_be_the_requesters(self):
        w = FakeWorkspace()
        with self.assertRaisesRegex(ValueError, "is not in the group fin-finance"):
            run({"folder": "fin-docs", "owner_group": "fin-finance"}, w)   # exists, but not theirs
        self.assertEqual((w.made, w.patched), ([], []))

    def test_an_existing_folder_must_be_managed_by_the_requester(self):
        theirs = {"/Workspace/fin-docs": (7, [{"group_name": "fin-finance", "all_permissions": [{"permission_level": "CAN_MANAGE"}]}])}
        w = FakeWorkspace(theirs)
        with self.assertRaisesRegex(ValueError, "already exists"):
            run({"folder": "fin-docs"}, w)
        self.assertEqual(w.patched, [])
        ours = {"/Workspace/fin-docs": (7, [{"group_name": "fin-data-eng", "all_permissions": [{"permission_level": "CAN_MANAGE"}]}])}
        w = FakeWorkspace(ours)
        run({"folder": "fin-docs"}, w)   # e.g. asking again
        self.assertEqual((w.made, w.patched[0][0]), ([], "/api/2.0/permissions/directories/7"))
        inherited = {"/Workspace/fin-docs": (7, [{"group_name": "fin-data-eng", "all_permissions": [{"permission_level": "CAN_MANAGE", "inherited": True}]}])}
        with self.assertRaisesRegex(ValueError, "already exists"):
            run({"folder": "fin-docs"}, FakeWorkspace(inherited))

    def test_refuses_bad_input_before_touching_the_workspace(self):
        for params in ({"folder": "Fin Docs"}, {"folder": "../x"}, {"folder": "users"},
                       {"folder": "fin-docs", "owner_group": 'x" or "1'},
                       {"folder": "fin-docs", "requested_by": "nobody@contoso.com"},
                       {"folder": "fin-docs", "request_id": "x'; DROP"}):
            w = FakeWorkspace()
            with self.subTest(params=params):
                with self.assertRaises(ValueError):
                    run(params, w)
                self.assertEqual((w.made, w.patched), ([], []))

    def test_a_run_cannot_change_the_root(self):
        w = FakeWorkspace()
        run({"folder": "fin-docs", "root": "/Users/x"}, w)
        self.assertEqual(w.made, ["/Workspace/fin-docs"])


if __name__ == "__main__":
    unittest.main()
