# Implementation notes

Design decisions and platform gotchas found while building the workbench. Read this before changing the event chain.

## Event chain

1. App button **Drop extract** copies `staging/policy_extract_2026_q3.csv` to `incoming/` and starts job 01.
2. Job 01 runs the declarative pipeline and writes a `PENDING` row to `extract_approvals`.
3. Approving in the app runs job 02, which rebuilds `experience_mart`.
4. A **table-update** trigger on `experience_mart` fires job 03 (assumption models), which registers `@challenger`.
5. Propose/approve in the app sets `@champion` and inserts into `model_champion_events`.
6. A **table-update** trigger on `model_champion_events` fires job 05 (BEL projection).

Job 02 also has a schedule (deployed paused). Job 07 is continuous (deployed paused). Job 99 is the manual end-to-end DAG.

## Platform constraints and workarounds

- **Serverless only.** All jobs use serverless environments. The Ray + spot job lives in `docs/illustrative/x_ray_spot.yml` for workspaces with classic compute.
- **Model-update trigger** (`trigger.model`, `MODEL_ALIAS_SET`) may not be enabled in your workspace. The workaround is the `model_champion_events` table plus a table-update trigger. The original block is commented in `resources/05_bel_projection.yml`.
- **File-arrival trigger** needs file events on the catalog's external location. On AWS the storage role also needs bucket-notification permissions. The app button starts job 01 directly, and the trigger block is commented in `resources/01_extract_ingest.yml`.
- **Table-update triggers need the table to exist when the job is created**, so `scripts/bootstrap.sql` runs *before* `bundle deploy` and creates a placeholder `experience_mart`.
- **The schema is not bundle-managed.** This avoids the chicken-and-egg problem with table-update triggers, and stops `bundle destroy` from wiping data. Volumes are bundle-managed.
- **`bundle deploy` resets anything changed through the API** (pause states, triggers) back to the YAML.

## Technical gotchas

- **UC model registration requires a signature.** Custom `pyfunc` classes without type hints get none, so pass `signature=infer_signature(...)` explicitly. Cast category dtypes to `str` first.
- **AQE coalesces tiny shuffles.** `groupBy().applyInPandas()` over ~1,000 groups can land on a handful of tasks. `repartition(n, key)` before the groupBy restores parallelism.
- **Shipping the local package to serverless UDF workers:** `pyspark.cloudpickle.register_pickle_by_value(module)` (see `src/notebooks/common.py::register_lib_for_udfs`). No wheel needed.
- **Notebook imports:** `src/notebooks/common.py` is a plain module (no notebook header), importable from the notebook folder, and it adds `src/` to `sys.path` for `actuarial_lib`.
- **Serverless streaming:** only use `trigger(availableNow=True)`. A continuous job re-launches it.

## App permissions

- `CAN_MANAGE_RUN` on a job isn't enough to pause/unpause it, which needs `CAN_MANAGE`. Jobs 02 and 07 grant that.
- UC access for the app service principal (`USE` / `SELECT` / `MODIFY` / `EXECUTE` / **`MANAGE`** for alias changes) is granted in SQL by `scripts/deploy_app.sh`.
- The app derives catalog/schema from the bundle-granted landing volume (`LANDING_VOLUME`). It finds the Genie space by title unless `GENIE_SPACE_ID` is set. `deploy_app.sh` grants the app `CAN_RUN` on the space.
- Apps reject PATs, so you can't curl the deployed app with one. Smoke-test by running the backend locally (see README).

## Demo hygiene

- Each extract drop adds a `PENDING` approval. Approving more than one double-counts 2026 experience, so run `scripts/reset_demo.sh` after testing.
- Every mart rebuild registers a new mortality challenger version (v3, v4…). Check version numbers before quoting them.
