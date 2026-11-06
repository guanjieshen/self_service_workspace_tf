"""The contract between the app and the self-service jobs it runs.

The app is one central copy; the jobs are deployed to the hub, one per workspace it serves. Both
check a request, so both must agree on the rules, the parameters and the tags, and a change
to one side has to change the other in the same pull request. These tests read both sides
(portal.py, and each job's notebook and its bundle definition) and fail where they differ.
"""
import pathlib
import re
import sys
import unittest

APP = pathlib.Path(__file__).resolve().parent.parent
ROOT = APP.parent.parent
sys.path.insert(0, str(APP))
import portal  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
import app_build  # noqa: E402
import yaml  # noqa: E402

JOBS = ("personal_schema", "team_folder")   # their notebooks, and the rules the app shares with them
DEPLOYED = ("personal_schema",)             # in the jobs bundle (the folder job is not, for now)
BUNDLE = yaml.safe_load((ROOT / "bundle/jobs/resources/jobs.yml").read_text())["resources"]


def notebook(kind):
    return (ROOT / "bundle/jobs/notebooks" / f"{kind}.py").read_text()


def checks(kind):
    """The notebook's checks: {variable: pattern} from its re.fullmatch(r"...", variable) lines."""
    return {var: pattern for pattern, var in re.findall(r're\.fullmatch\(r"([^"]+)", (\w+)\)', notebook(kind))}


def notebook_parameters(kind):
    """The parameters the notebook reads (its dbutils.widgets.text loop)."""
    found = re.search(r"for name in \(([^)]*)\):\s*\n\s*dbutils\.widgets\.text", notebook(kind)).group(1)
    return set(found.replace('"', "").replace(" ", "").split(","))


def job_parameters(kind):
    """The job's parameters: its bundle definition's, or (not deployed) its notebook's."""
    if kind in BUNDLE["jobs"]:
        return {p["name"] for p in BUNDLE["jobs"][kind]["parameters"]}
    return notebook_parameters(kind)


def job_tags(kind):
    """The tag names the job gets: its bundle definition's, and those the build adds per workspace."""
    s = {"jobs": yaml.safe_load((ROOT / "config/self-service/app.yaml").read_text())["jobs"],
         "hub": {"host": "https://adb-9.9.azuredatabricks.net"}}
    w = {"name": "example", "bu": "EX", "host": "https://adb-1.1.azuredatabricks.net", "catalog": "ex_citizen_dev"}
    target = app_build.jobs_target(s, w, [])["targets"]["example"]["resources"]
    return set(BUNDLE["jobs"][kind]["tags"]) | set(target["jobs"][kind]["tags"])


class SentParameters(unittest.TestCase):
    """What the app passes to run_now is exactly what each job declares."""

    def sent(self, kind):
        sent = []
        jobs = type("Jobs", (), {"run_now": lambda self, job_id, job_parameters: sent.append(job_parameters) or type("R", (), {"run_id": 1})(),
                                 "list_runs": lambda self, **kw: []})()
        tags = {"personal_schema": {"cd_self_service": "personal_schema", "cd_catalog": "c", "cd_prefix": "cd_", "cd_workspace": "w"},
                "team_folder": {"cd_self_service": "team_folder", "cd_root": "/Workspace", "cd_workspace": "w"}}
        listed = [type("J", (), {"job_id": i, "settings": type("S", (), {"tags": t})()})() for i, t in enumerate(tags.values())]
        client = type("C", (), {"jobs": jobs})()
        client.jobs.list = lambda: listed
        db = type("DB", (), {"record_request": lambda self, r: None, "run_started": lambda self, *a: None,
                             "requests_of": lambda self, user: []})()   # every request is recorded first
        p = portal.Portal({"workspaces": [{"name": "w", "bu": "B", "host": "h"}]}, lambda host: client, store=db)
        if kind == "personal_schema":
            p.request_schema("w", "ana@contoso.com")
        else:
            p.request_folder("w", "ana@contoso.com", "fin-docs", reason="Notebooks for the month-end close.")
        return set(sent[0])

    def test_personal_schema(self):
        self.assertEqual(self.sent("personal_schema"), job_parameters("personal_schema"))

    def test_team_folder(self):
        self.assertEqual(self.sent("team_folder"), job_parameters("team_folder"))

    def test_the_schema_job_is_named_for_every_kind_it_makes(self):
        self.assertEqual(BUNDLE["jobs"]["personal_schema"]["name"], "${var.business_unit} schema requests",
                         "personal, project, team and temporary: not 'personal schema'")

    def test_the_temporary_schema_cleanup_runs_every_day_on_its_own(self):
        job = yaml.safe_load((ROOT / "bundle/hub/resources/cleanup.yml").read_text())["resources"]["jobs"]["temporary_cleanup"]
        self.assertEqual([t["task_key"] for t in job["tasks"]], ["cleanup"], "one task: it summarizes too")
        self.assertEqual((job["schedule"]["quartz_cron_expression"], job["schedule"]["pause_status"]), ("0 0 6 * * ?", "UNPAUSED"))
        self.assertEqual(job["max_concurrent_runs"], 1)
        self.assertEqual({p["name"] for p in job["parameters"]}, {"dry_run"}, "dry_run, and nothing else")
        self.assertIn('dbutils.widgets.text("dry_run", "")', notebook("temporary_cleanup"), "the notebook reads it")

    def test_the_notebooks_read_the_same_parameters(self):
        for kind in DEPLOYED:
            with self.subTest(kind=kind):
                self.assertEqual(notebook_parameters(kind), job_parameters(kind))


class Rules(unittest.TestCase):
    """The app refuses exactly what the jobs refuse, so a request it accepts does not fail later."""

    def test_personal_schema(self):
        found = checks("personal_schema")
        self.assertEqual(found["user"], portal.EMAIL)
        self.assertEqual(found["schema"], portal.SCHEMA)
        self.assertEqual(found["owner_group"], portal.GROUP)   # a team schema's group

    def test_team_folder(self):
        found = checks("team_folder")
        self.assertEqual(found["folder"], portal.FOLDER)
        self.assertEqual(found["requested_by"], portal.EMAIL)
        self.assertEqual(found["owner_group"], portal.GROUP)
        reserved = re.search(r"folder in \(([^)]*)\)", notebook("team_folder")).group(1)
        self.assertEqual(tuple(re.findall(r'"([^"]+)"', reserved)), portal.RESERVED_FOLDERS)

    def test_the_request_id_the_app_makes_is_one_the_jobs_take(self):
        for kind in JOBS:
            with self.subTest(kind=kind):
                self.assertRegex(portal.new_request_id(), "^" + checks(kind)["request_id"] + "$")

    def test_the_personal_schema_is_named_the_same_way(self):
        naming = re.search(r"^personal = (.+)$", notebook("personal_schema"), re.M).group(1)
        for email in ("ana@contoso.com", "Ana.Lopez-Diaz@contoso.com", "o'brien@contoso.com", "_x_@contoso.com"):
            for prefix in ("cd_", "sb_"):
                with self.subTest(email=email, prefix=prefix):
                    job = eval(naming, {"re": re}, {"prefix": prefix, "user": email.strip().lower()})
                    self.assertEqual(portal.schema_name(email.lower(), prefix), job)


class Tags(unittest.TestCase):
    """How the app finds each job, and what it reads from it."""

    def test_the_jobs_set_the_tags_the_app_reads(self):
        read = set(re.findall(r'"(cd_\w+)"', (APP / "portal.py").read_text()))
        set_by_jobs = set().union(*(job_tags(kind) for kind in DEPLOYED)) | {"cd_root"}   # cd_root: the folder job's, not deployed
        self.assertEqual(read - set_by_jobs, set(), "tags the app reads but no job sets")

    def test_the_app_finds_every_job_by_its_kind(self):
        for kind in DEPLOYED:
            with self.subTest(kind=kind):
                self.assertEqual(BUNDLE["jobs"][kind]["tags"]["cd_self_service"], kind)
                self.assertIn(kind, portal.TASKS)


if __name__ == "__main__":
    unittest.main()
