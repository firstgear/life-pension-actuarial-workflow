# Demo script — Life & Pension Actuarial Workbench (20 minutes)

**Audience:** a life & pension insurer's Head of Data plus the actuarial modelling & development team (actuaries, statisticians, engine developers). They are not Databricks users yet.
**You:** the presenter, screen-sharing the deployed Databricks App and the workspace.
**App:** `https://lp-actuarial-workbench-<workspace-id>.<cloud>.databricksapps.com` (printed by `scripts/deploy_app.sh`)
**Workspace:** your workspace, catalog/schema `<catalog>.lp_actuarial`

**One-line message:** *"Databricks orchestrates your actuarial workloads and scales the heavy calculations. It does some of the maths, not all of it, and it integrates with the engines you already run. You lift what you do today onto one governed platform, one low-risk step at a time."*

**Format:** **GO** = where to be · **DO** = the click · **SAY** = the words (each ≤ ~25 s) · **IF-ASKED** = likely question and answer.
**Ground rules:** all data is synthetic, so say it once at the start and once more if a number gets attention. Speed-ups are measured on this demo book, not benchmarked on the customer's estate. Never say "replace Prophet/Radar/Igloo/ResQ". The phrase is *integrate*.

---

## Timeline at a glance

| Time | Stop (app page) | Databricks capability shown | Live action |
|---|---|---|---|
| 0:00–2:00 | Home | Platform POV, Apps | — |
| 2:00–5:00 | 1 · Data Ingestion | Event-started job, declarative pipeline + DQ, HITL | **Drop extract** (starts a ~3-min job) |
| 5:00–7:00 | 2 · Experience Mart → 9 · Genie | Spark SQL, Delta versions, Genie with reasoning | Ask one Genie question |
| 7:00 → | 1 · Data Ingestion (back) | Approval gate | **Approve extract** |
| 7:00–12:00 | 3 · Assumption Models → 4 · Model Factory | statsmodels / lifelines / LightGBM, MLflow, Spark fan-out, Ray | Show results; optionally launch a factory run |
| 12:00–15:00 | 5 · Deployment & Approval | UC registry aliases, four-eyes approval, model-update event | **Propose → Approve** (fires projection) |
| 15:00–18:00 | 6 · Projection → 7 · Stochastic & Stress | mapInPandas, nested Monte Carlo, compute choices | Show new BEL from the triggered run |
| 18:00–20:00 | 8 · Governance → 10 · Orchestration & Compute | Audit, reproducibility, 6 trigger types, PoC | Close |

Two live jobs run *while you talk*: the extract drop (2:30, done by ~6:00) and the approval (13:00, projection done by ~16:00). That's why the order is what it is.

---

## 0:00–2:00 · Open — the question on the table (Home)

**GO:** Home (`/`).
**SAY:** "Thanks for the time. I'd like to show rather than tell. This is a working actuarial workbench on Databricks. The data is synthetic, a 100,000-policy book shaped like a typical policy-administration experience extract, but the methods and the platform are real. Please react to the *workflow*, not the numbers."

**DO:** point at the problem panel (on-prem in-house engines, R + SQL Server, on-prem hardware up for renewal).
**SAY:** "Here's a setup we see at many insurers: in-house reserving and pricing engines, estimation in R on SQL Server data, all on fixed on-premises hardware that's coming up for renewal. The question on the table: can Databricks cut calculation times for the GLM estimation and the heavy ETL, and scale it?"

**SAY (two questions — say this explicitly):** "I'd split that into two questions. One: can Databricks be the governed data-and-orchestration layer *around* your estimation process? I'm confident that's a strong yes, and you'll see it. Two: should some of the *computation* also move here? That one I don't want to assume. It's what a PoC should benchmark against what you run today."

**DO:** sweep the flow spine and the KPI tiles (policies, life-years, deaths, BEL, champions).
**SAY:** "The flow is a quarter in an actuary's life: an extract arrives, it's validated and approved, it feeds a mart, assumptions get re-estimated, a new assumption is approved, liabilities are re-projected and stressed. Every step is a job, every model is governed, every number is traceable."

**IF-ASKED — "Is this our data?"** "No, it's fully synthetic and seeded so it's reproducible. The decrement rates were planted on purpose, so you'll see the GLM recover them."

---

## 2:00–5:00 · 1 · Data Ingestion — the extract lands (live)

**GO:** 1 · Data Ingestion.
**SAY:** "Today an extract comes off SQL Server and gets massaged by hand or in .NET. Here it's a file landing in a governed volume in Unity Catalog."

**DO:** click **Drop new policy admin extract (2026 Q1–Q3)**. *(Job 01 starts immediately; a run tracker appears under the banner. Pipeline + profiling take ~3 min.)*
**SAY:** "I've just dropped this year's quarterly extract into the landing volume, and the ingest job has started. In production you wouldn't even need the button: a *file-arrival trigger* on that folder starts the job the moment a file lands. The job runs a Lakeflow declarative pipeline with data-quality expectations: missing keys, negative exposure, impossible ages."

**DO:** point at **DQ rules — rows quarantined** and **Quarantine — sample of rejected rows** (they show the baseline load; the new extract adds 37 bad rows in a few minutes).
**SAY:** "Bad rows aren't dropped silently. They're quarantined, so the actuary can see exactly what was rejected and why. And nothing touches an assumption until a human approves the extract. We'll come back to approve it in a few minutes, once the pipeline's done."

**IF-ASKED — "How does the data get here from SQL Server?"** "Lakeflow Connect can stream SQL Server tables in incrementally with CDC, or your existing export lands files exactly like this. Either way it's the same governed landing zone. Step one of a PoC is usually just that."
**IF-ASKED — "Why a button, not the file-arrival trigger?"** "For the demo I want it on cue. The trigger config is in the bundle (`resources/01_extract_ingest.yml`, commented). It needs file events on the storage location, which not every sandbox storage role allows. Where file events work, it's a two-line change."

---

## 5:00–7:00 · 2 · Experience Mart, then 9 · Genie (self-service)

**GO:** 2 · Experience Mart.
**SAY:** "This is the GLM-ready mart: approved experience joined to the policy master, aggregated to risk cells. Exposure in life-years, deaths, disabilities, surrenders, paid-ups, and expected deaths on a standard table. It's Spark SQL on serverless, so the same code runs on 800 thousand rows or 80 million."

**DO:** point at **A/E vs standard table, by calendar year** (≈0.93) and **Delta history — every rebuild is a version**.
**SAY:** "Every rebuild is a version. If an auditor asks what the mart looked like when an assumption was set, that's one query, not a restore. And writing this table is itself an event: it fires the assumption-model job through a *table-update trigger*."

**GO:** 9 · Actuarial AI (Genie). **DO:** ask *"Which age bands have A/E against the standard table above 1.0?"* (or click the sample question).
**SAY:** "And for anyone outside the modelling team, like finance, risk, or a product owner, this is Genie. It's plain English over the same governed tables, with the same permissions. It shows its reasoning and the SQL, and it knows our definitions: A/E is deaths over expected deaths, and rates are exposure-weighted, never averaged."

**IF-ASKED — "Can it be wrong?"** "Yes, which is why it shows the SQL and the reasoning. The instructions encode your definitions, and you curate trusted example queries. It's self-service with a paper trail, not a black box."

**GO:** back to 1 · Data Ingestion (the extract should be PENDING by now). **DO:** **Approve**.
**SAY:** "The extract is profiled: rows received, rows quarantined, exposure, deaths, and the A/E against the current champion. I approve it. That rebuilds the mart, and the mart change re-runs the assumption models. A chain of events, no orchestration code."

---

## 7:00–12:00 · 3 · Assumption Models and 4 · Model Factory (hero)

**GO:** 3 · Assumption Models.
**SAY:** "This is where your team lives. Mortality is a Poisson GLM in statsmodels: log-linear in age with a calendar-year trend, plus sex, scheme, product, duration and salary band, offset by log exposure. It's the same model you'd write in R."

**DO:** walk the relativities and KPIs.
**SAY:** "And it finds what we planted: men about 1.33 times women, life annuitants around 0.83 (annuitant selection), disability-cover members around 1.6, roughly 9.6% more mortality per year of age, and about 1.3% improvement per calendar year. Confidence intervals included. It's a rating table an actuary and a regulator can read."

**DO:** point at **Actual vs expected by segment — champion vs challenger vs standard table**, salary band rows.
**SAY:** "Here's why there's a challenger. The champion has no socio-economic factor. Look at A/E by salary band: low earners run at 1.18, high earners at 0.84, so the champion is mispricing longevity across the book. The challenger adds salary band, those A/Es go to 1.00, and AIC drops by about 185. That's the case we'll take to approval in a minute."

**DO:** scroll to disability (Cox model, KM curves) and lapse.
**SAY:** "Same pattern for the other decrements: disability recovery in lifelines as a Cox model, and lapse as a logistic GLM versus LightGBM. The GLM stays champion because it's explainable. LightGBM is the challenger that tells us *where* the GLM is wrong. Average-rate products after the 2022 rate rise: actual lapse 3.0%, the GLM says 2.5%, LightGBM says 2.9%. The point isn't to swap in the black box. The ML shows you which interaction to add to the GLM."
**SAY:** "Every one of these fits is an MLflow run, registered in Unity Catalog with @champion and @challenger aliases. Nothing lives on a laptop."

**GO:** 4 · Model Factory.
**SAY:** "Now the thing your servers are sized for: not one GLM but thousands. One fit per segment, scheme × sex × product × region × period, times 50 bootstrap replicates for parameter uncertainty."
**DO:** point at the KPIs (last run: ~9,200 GLM fits; parallel ~1.4 min vs ~8 min sequential, ≈6× on this small serverless allocation).
**SAY:** "Over nine thousand GLMs. One after another, that's about eight minutes. Fanned out with Spark it's under a minute and a half, and the statistics are *unchanged*: plain statsmodels inside a function. Spark ships each segment to a worker. It's the same principle that turns your overnight batch into minutes, and the speed-up grows with the number of workers, because the fits are independent."
**DO:** point at the bootstrap chart (heaviest and lightest segments).
**SAY:** "And because fits are cheap, you get uncertainty for free. Every segment's mortality at 65 with a bootstrap 95% interval."

**DO:** **Parallel engine** card → Ray tab.
**SAY:** "When the unit of work is Python *logic* rather than a data operation, say a projection engine, nested simulation, stateful workers or parameter sweeps, Ray is the better fit. It's the same kernel as Ray tasks on a cluster with spot workers. Spark for data parallelism, Ray for logic parallelism. If your next-generation engine is Python, NumPy, Numba or JAX, Ray scales it without rewriting it into Spark. If you keep your existing engine, you orchestrate it from here and don't need Ray at all."

**IF-ASKED — "Is a single GLM faster on Databricks?"** "Honestly, not necessarily. A single statsmodels fit is a single-machine computation. The win is running thousands concurrently and elastically, plus everything around it. Single-fit speed is exactly what I'd benchmark in a PoC."
**IF-ASKED — "Can we keep R?"** "Yes. R runs in notebooks and jobs too. The orchestration, governance and lineage don't care about the language."

---

## 12:00–15:00 · 5 · Deployment & Approval — four eyes (live)

**GO:** 5 · Deployment & Approval.
**SAY:** "An assumption change is a governed decision, not a file copy. The actuary proposes, the chief actuary approves."
**DO:** **Mortality model — champion vs challenger** card: v1 vs v2 (AIC, deviance, factors).
**DO:** **Propose challenger for approval**. Type the rationale: *"Add salary band: A/E by salary band 1.18/0.84 → 1.00; AIC −185."* → propose.
**SAY:** "The proposal records who, when, why and the evidence."
**DO:** in **Pending approvals — chief actuary** (the "acting as Chief Actuary" toggle is on), add a note → **Approve → @champion**.
**SAY:** "On approval, the Unity Catalog alias @champion moves to version 2, @previous_champion keeps version 1 for rollback, and that event re-runs the best-estimate liability projection by itself. Nobody exports parameters to a spreadsheet and re-keys them into the valuation engine."

**IF-ASKED — "Can the same person propose and approve?"** "Not in real life. Four-eyes is enforced server-side; the toggle is only there so I can play both roles in a demo."
**IF-ASKED — "And rollback?"** "One click. The alias moves back, and that's also an event and an audit row."

---

## 15:00–18:00 · 6 · Projection and 7 · Stochastic & Stress

**GO:** 6 · Projection Engine. **DO:** select the newest run (*Triggered by: model trigger*, mortality model v2).
**SAY:** "There it is. The projection job fired from the champion change, loaded version 2 from the registry, and projected 80 years of cash flows for about 11,000 model points: annuities from retirement, disability and health claims, expenses, discounted to a best-estimate liability. The total BEL tile shows the figure for the sample book. The kernel is vectorised NumPy, and Spark fans the model points out."
**DO:** point at **Net liability cash flows by scheme** and **What-if — re-run the projection job** (don't necessarily run it).
**SAY:** "And an actuary can ask what-if questions on discount rate, mortality or lapse without a ticket to IT."

**GO:** 7 · Stochastic & Stress.
**SAY:** "Stresses shaped like the Solvency II standard formula. Longevity minus 20% adds about 9% to BEL, rates down 100 basis points about 15%, and a 40% mass lapse is minus 31%." *(Illustrative calibration.)*
**DO:** point at **Nested structure** and the distribution.
**SAY:** "And the nested case, which is where compute really bites: 1,000 outer real-world scenarios, and inside each one a risk-neutral Monte Carlo valuing the interest-rate guarantee on average-rate savings. That's half a billion inner paths. Every outer scenario is independent, so it fans out over Spark tasks. The same array code runs in Numba, or in PyTorch on serverless GPU when the inner simulation gets heavy. This is where Ray and GPUs earn their keep, and where *you* pick the engine per workload."

**IF-ASKED — "Is this your SCR?"** "No. It's a 99.5th-percentile proxy on a toy ESG to show the shape of the workload. Your internal model stays your internal model."

---

## 18:00–20:00 · 8 · Governance → 10 · Orchestration & Compute — close

**GO:** 8 · Governance.
**SAY:** "The auditor's question: which data, which code, which model, who approved it? Here: the mart's Delta version, the code version, the MLflow run, the approval with names and notes, and every event in an append-only audit log, including the one we just made."

**GO:** 10 · Orchestration & Compute. **DO:** point at **Job & trigger catalogue**.
**SAY:** "Every job you saw is defined in an Asset Bundle, as code in Git. And look at the triggers: a *table updates* (mart → assumption models), a *model is promoted* (champion → projection), a *schedule* for the nightly mart, a *continuous* A/E monitor, and *manual* or app-started runs like the extract drop. File arrival is one config block away. All of it on serverless, with retries, dependencies and full run history."
**DO (optional, 10 s):** unpause **07 A/E monitor (continuous)**, then pause it again. **DO (optional):** open **99 End-to-end valuation run** in the Jobs UI to show the DAG.

**DO:** **Integrate, don't rip out** → **Proposed PoC — two tracks**.
**SAY (close):** "So, back to the two questions. Platform fit: I think you've seen it, with governed data, events instead of scripts, and approvals and lineage built in. Engine fit is the honest open question, so let's measure it. A two-track PoC on your own experience data. Track A: data prep here, your existing engine as-is, results back for comparison. Track B: data prep *and* the GLM estimation here. Same metrics for both: end-to-end runtime, estimation runtime, concurrency, peak compute, cost per run, statistical equivalence to your R results, reproducibility, operational effort. Then you decide on evidence, not on a hardware renewal date."
**SAY:** "Which GLM suite would you want to see first?"

---

## Backup sections (not in the 20 minutes)

- **Mart scale-up:** 2 · Experience Mart → **Rebuild mart** with scale factor 100 (≈84M policy-years) to show Spark data parallelism. Takes a few minutes; run it before the session if you want the benchmark tile.
- **Disability deep-dive:** 3 · Assumption Models → Cox hazard ratios and KM curves by onset age (pairs well with disability-modelling and IBNR discussions).
- **What-if projection:** 6 · Projection → set discount 2.0%, run, and compare with base in **Projection runs**.
- **The code:** workspace → `.bundle/lp-actuarial-demo/demo/files/src/notebooks` and `resources/*.yml`, e.g. `03a_mortality_glm.py` to show it's ordinary statsmodels.

## Genie questions (already provisioned in the space)

1. What is the actual vs expected mortality by scheme for the champion and challenger models?
2. Which age bands have A/E against the standard table above 1.0?
3. Show deaths, exposure and the crude mortality rate by age band and sex since 2020
4. How did total BEL change between the last two projection runs, and which model version did each use?
5. What is the impact of the longevity and interest-rate-down stresses on BEL?
6. Compare surrender rates for average-rate vs market-rate products before and after 2022
7. Which policy admin extracts are pending approval and how many rows were quarantined?
8. Who approved the current mortality champion and when?

Good live picks: **#2** (shows reasoning and the A/E definition), **#4** (joins governance and results), **#8** (audit trail in plain English).

## Pre-demo checklist (T-30 min)

1. Run `./scripts/reset_demo.sh`. It restores champion v1, clears dropped extracts and pending approvals, and rebuilds the mart.
2. Start the app if stopped: `databricks apps start lp-actuarial-workbench`. Open every page once to warm it.
3. Make sure the SQL warehouse *Serverless Starter Warehouse* is running (open Genie once).
4. Check 3 · Assumption Models shows **v1 champion / v2 challenger**, 4 · Model Factory has a run with ~9,000 fits, 7 · Stochastic has a run.
5. Have tabs ready: the app, the Jobs list filtered on "Actuarial Workbench", the `lp_actuarial` schema in Catalog Explorer, and the MLflow experiment `lp-actuarial-assumption-models`.
6. After the demo: `databricks apps stop lp-actuarial-workbench` (apps don't auto-stop).

## Guardrails

- Synthetic data. Speed-ups are measured on this demo book on a small serverless allocation, not a customer benchmark.
- Integrate, don't replace: Prophet/ResQ/Radar/Igloo and their in-house engines can stay; Databricks orchestrates them and feeds them governed data.
- No other customer names on screen. Industry references stay anonymised.
