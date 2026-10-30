"""Shared helpers for the script tests (standard library only)."""
import importlib.util
import pathlib

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent


def load(script):
    """Import scripts/<script>.py (the file names have hyphens, so not importable by name)."""
    path = SCRIPTS / f"{script}.py"
    spec = importlib.util.spec_from_file_location(script.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def change(rtype, actions, before=None, after=None, name="this", index=None):
    """One entry of a plan's resource_changes."""
    rc = {"address": f"module.m.{rtype}.{name}", "mode": "managed", "type": rtype, "name": name,
          "change": {"actions": actions, "before": before, "after": after}}
    if index is not None:
        rc["index"] = index
    return rc

