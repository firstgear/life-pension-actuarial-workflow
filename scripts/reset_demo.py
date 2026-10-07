"""Reset the demo to its rehearsed starting state (run ~30 min before the session).

    WAREHOUSE_ID=<id> [CATALOG=main SCHEMA=lp_actuarial] ./scripts/reset_demo.sh [profile]

End state:
  * incoming/ holds only the 2015-2025 baseline; bronze/silver contain only baseline rows
  * extract_approvals: only the baseline (APPROVED); model_approvals: only the bootstrap row
  * experience_mart built from the baseline only
  * mortality_glm: @champion = baseline version (v1), @challenger = latest version, no @previous_champion
  * latest BEL projection uses the champion; continuous A/E monitor paused; app running
The audit log is append-only and is NOT cleared — a DEMO_RESET event is written instead.
"""
import json
import os
import sys
import time
import uuid

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs as J
from databricks.sdk.service.apps import ComputeState

PROFILE = sys.argv[1] if len(sys.argv) > 1 else os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
CATALOG, SCHEMA = os.getenv("CATALOG", "main"), os.getenv("SCHEMA", "lp_actuarial")
WAREHOUSE = os.environ["WAREHOUSE_ID"]  # required: SQL warehouse id
APP = os.getenv("APP", "lp-actuarial-workbench")
S = f"{CATALOG}.{SCHEMA}"
VOL = f"/Volumes/{CATALOG}/{SCHEMA}/extract_landing"
BASELINE = "policy_years_2015_2025.csv"
MORTALITY = f"{S}.mortality_glm"

w = WorkspaceClient(profile=PROFILE)


def step(msg):
    print(f"▶ {msg}", flush=True)


def sql(stmt):
    r = w.statement_execution.execute_statement(statement=stmt, warehouse_id=WAREHOUSE, wait_timeout="50s")
    while r.status.state.value in ("PENDING", "RUNNING"):
        time.sleep(2)
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state.value != "SUCCEEDED":
        raise RuntimeError(f"SQL failed: {r.status.error.message if r.status.error else r.status.state}\n{stmt}")
    return r.result.data_array or [] if r.result else []


def job(prefix):
    for j in w.jobs.list(name=None):
        if j.settings and (j.settings.name or "").startswith(prefix):
            return j.job_id
    raise KeyError(prefix)


def wait_idle(job_id, label):
    while True:
        active = list(w.jobs.list_runs(job_id=job_id, active_only=True))
        if not active:
            return
        print(f"   waiting for {len(active)} active run(s) of {label}…", flush=True)
        time.sleep(15)


def run_and_wait(job_id, label, params=None):
    print(f"   running {label}…", flush=True)
    run = w.jobs.run_now(job_id=job_id, job_parameters=params or {}).result(timeout=__import__("datetime").timedelta(minutes=20))
    state = run.state.result_state.value if run.state and run.state.result_state else "?"
    if state != "SUCCESS":
        raise RuntimeError(f"{label} finished with {state}: {run.run_page_url}")


# --------------------------------------------------------------------------- 1
step("1/8 Stop queued/running ingest runs and clear dropped extracts")
j01 = job("Actuarial Workbench · 01")
for r in w.jobs.list_runs(job_id=j01, active_only=True):
    w.jobs.cancel_run(r.run_id)
time.sleep(5)
removed = 0
for f in w.files.list_directory_contents(f"{VOL}/incoming/"):
    if f.name != BASELINE:
        w.files.delete(f.path)
        removed += 1
print(f"   removed {removed} dropped extract file(s)")

# --------------------------------------------------------------------------- 2
step("2/8 Pipeline: full refresh if bronze holds anything but the baseline")
extra = sql(f"SELECT count(*) FROM {S}.bronze_policy_years WHERE source_file <> '{BASELINE}'")[0][0]
if int(extra) > 0:
    pid = next(p.pipeline_id for p in w.pipelines.list_pipelines() if (p.name or "").startswith("Actuarial Workbench · Extract"))
    upd = w.pipelines.start_update(pid, full_refresh=True).update_id
    while True:
        st = w.pipelines.get_update(pid, upd).update.state.value
        if st in ("COMPLETED", "FAILED", "CANCELED"):
            break
        print(f"   pipeline full refresh: {st}…", flush=True)
        time.sleep(20)
    if st != "COMPLETED":
        raise RuntimeError(f"pipeline full refresh {st}")
else:
    print("   bronze already baseline-only — skipped")

# --------------------------------------------------------------------------- 3
step("3/8 Approvals: keep only the baseline extract and the bootstrap model approval")
sql(f"DELETE FROM {S}.extract_approvals WHERE source_file <> '{BASELINE}'")
sql(f"DELETE FROM {S}.model_approvals WHERE coalesce(reviewed_by, '') <> 'system (bootstrap)'")

# --------------------------------------------------------------------------- 4
step("4/8 Experience mart: rebuild if it contains post-baseline experience")
j02, j03 = job("Actuarial Workbench · 02"), job("Actuarial Workbench · 03")
if int(sql(f"SELECT count(*) FROM {S}.experience_mart WHERE calendar_year > 2025")[0][0]) > 0:
    wait_idle(j02, "job 02")
    run_and_wait(j02, "job 02 (experience mart)", {"scale_factor": "1"})
    time.sleep(90)                      # the table-update trigger starts job 03
    wait_idle(j03, "job 03 (assumption models, table-update trigger)")
else:
    print("   mart is baseline-only — skipped")
wait_idle(j03, "job 03")

# --------------------------------------------------------------------------- 5
step("5/8 Mortality model aliases: champion = baseline, challenger = latest")
boot = sql(f"SELECT model_version FROM {S}.model_approvals WHERE model_name = 'mortality_glm' AND reviewed_by = 'system (bootstrap)'")
base_v = boot[0][0] if boot else "1"
versions = sorted(int(v.version) for v in w.model_versions.list(full_name=MORTALITY))
latest = str(versions[-1])
current = w.registered_models.get(MORTALITY, include_aliases=True)
aliases = {a.alias_name: a.version_num for a in (current.aliases or [])}
w.registered_models.set_alias(MORTALITY, "champion", int(base_v))
w.registered_models.set_alias(MORTALITY, "challenger", int(latest))
if "previous_champion" in aliases:
    w.registered_models.delete_alias(MORTALITY, "previous_champion")
print(f"   @champion v{base_v} (was v{aliases.get('champion')}), @challenger v{latest}")

# --------------------------------------------------------------------------- 6
step("6/8 BEL: re-project on the champion if the latest run used another version")
last = sql(f"SELECT model_version FROM {S}.bel_runs ORDER BY run_ts DESC LIMIT 1")
if not last or str(last[0][0]) != str(base_v):
    j05 = job("Actuarial Workbench · 05")
    wait_idle(j05, "job 05")
    run_and_wait(j05, "job 05 (BEL projection)", {"scenario_label": "Base (champion)", "requested_by": "demo reset"})
else:
    print("   latest projection already on the champion — skipped")

# --------------------------------------------------------------------------- 7
step("7/8 Pause the continuous A/E monitor")
j07 = job("Actuarial Workbench · 07")
w.jobs.update(j07, new_settings=J.JobSettings(continuous=J.Continuous(pause_status=J.PauseStatus.PAUSED)))

sql(f"""INSERT INTO {S}.audit_log VALUES ('{uuid.uuid4()}', current_timestamp(), 'DEMO_RESET', 'schema', '{S}', '',
        current_user(), '{json.dumps({"removed_extracts": removed, "champion": base_v, "challenger": latest})}', 'reset script', '')""")

# --------------------------------------------------------------------------- 8
step("8/8 Make sure the app is running")
app = w.apps.get(APP)
if not app.compute_status or app.compute_status.state != ComputeState.ACTIVE:
    w.apps.start(APP).result()
print(f"✅ Demo reset. Workbench: {w.apps.get(APP).url}")
