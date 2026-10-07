"""Create (or update) the 'Actuarial Genie' space over the demo tables. Idempotent: matched by title.

    WAREHOUSE_ID=<id> [CATALOG=main SCHEMA=lp_actuarial] \
      uv run --with databricks-sdk python scripts/create_genie_space.py [profile]

Prints the space id. The app finds the space by this title (or set GENIE_SPACE_ID in
src/app/app.yaml); scripts/deploy_app.sh runs this and grants the app CAN_RUN on it.
"""
import json
import os
import sys
import uuid

from databricks.sdk import WorkspaceClient

PROFILE = sys.argv[1] if len(sys.argv) > 1 else os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
CATALOG, SCHEMA = os.getenv("CATALOG", "main"), os.getenv("SCHEMA", "lp_actuarial")
WAREHOUSE = os.environ["WAREHOUSE_ID"]  # required: SQL warehouse id
TITLE = "Actuarial Genie — Life & Pension (synthetic)"
S = f"{CATALOG}.{SCHEMA}"

TABLES = ["experience_mart", "ae_results", "mortality_relativities", "bel_runs", "bel_cashflows",
          "stress_results", "stochastic_runs", "extract_approvals", "model_approvals", "audit_log",
          "lapse_assumptions", "lapse_segment_fit", "factory_segment_summary", "model_points"]

INSTRUCTIONS = f"""You are a life & pension actuarial analyst assistant. All data is synthetic.
- Mortality rates are exposure-weighted: rate = SUM(deaths) / SUM(exposure). Never average rates across cells.
- A/E (actual vs expected) = SUM(deaths) / SUM(expected deaths). In experience_mart the standard-table expectation is expected_deaths_std. In ae_results use ae_champion / ae_challenger / ae_standard_table directly.
- Lapse (surrender) rate = SUM(surrenders) / SUM(exposure_pre_retirement).
- Monetary amounts are in EUR. Present large amounts in EUR billions (bn) or millions (m).
- BEL = best-estimate liability. The latest projection is the row in bel_runs with the latest run_ts; bel_by_scheme is a JSON string.
- In stress_results always use the latest stress_run_id (max run_ts); delta_pct is a fraction (0.087 = 8.7%).
- Scheme codes: COMPANY_PENSION, PRIVATE_PENSION, LIFE_ANNUITY, DISABILITY_COVER, HEALTH_COVER. product_type AVERAGE_RATE = with-profits with a guaranteed rate; MARKET_RATE = unit-linked.
- The current champion of a model is the latest APPROVED row in model_approvals for that model_name.
- Explain your reasoning briefly and state which table(s) you used."""

SAMPLE_QUESTIONS = [
    "What is the actual vs expected mortality by scheme for the champion and challenger models?",
    "Which age bands have A/E against the standard table above 1.0?",
    "Show deaths, exposure and the crude mortality rate by age band and sex since 2020",
    "How did total BEL change between the last two projection runs, and which model version did each use?",
    "What is the impact of the longevity and interest-rate-down stresses on BEL?",
    "Compare surrender rates for average-rate vs market-rate products before and after 2022",
    "Which policy admin extracts are pending approval and how many rows were quarantined?",
    "Who approved the current mortality champion and when?",
]

EXAMPLE_SQL = [
    ("A/E against the standard table by scheme and period",
     f"SELECT scheme, period, SUM(deaths) AS deaths, ROUND(SUM(expected_deaths_std), 1) AS expected,\n"
     f"       ROUND(SUM(deaths) / SUM(expected_deaths_std), 3) AS ae\nFROM {S}.experience_mart\nGROUP BY scheme, period\nORDER BY scheme, period"),
    ("Latest BEL projection",
     f"SELECT projection_run_id, run_ts, model_version, scenario_label, ROUND(total_bel_eur / 1e9, 2) AS bel_bn_eur\n"
     f"FROM {S}.bel_runs ORDER BY run_ts DESC LIMIT 1"),
]


def hexid():
    return uuid.uuid4().hex


def serialized():
    return json.dumps({
        "version": 2,
        "config": {"sample_questions": sorted([{"id": hexid(), "question": [q]} for q in SAMPLE_QUESTIONS], key=lambda x: x["id"])},
        "data_sources": {"tables": [{"identifier": f"{S}.{t}"} for t in sorted(TABLES)]},
        "instructions": {
            "text_instructions": [{"id": hexid(), "content": [INSTRUCTIONS]}],
            "example_question_sqls": sorted([{"id": hexid(), "question": [q], "sql": [sql]} for q, sql in EXAMPLE_SQL],
                                            key=lambda x: x["id"]),
        },
    })


def main():
    w = WorkspaceClient(profile=PROFILE)
    existing = None
    for sp in w.api_client.do("GET", "/api/2.0/genie/spaces").get("spaces", []):
        if sp.get("title") == TITLE:
            existing = sp["space_id"]
    body = {"title": TITLE, "warehouse_id": WAREHOUSE, "serialized_space": serialized(),
            "description": "Ask the experience, assumption, projection and governance tables in plain English. Synthetic data."}
    if existing:
        w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{existing}", body=body)
        print(existing)
    else:
        print(w.api_client.do("POST", "/api/2.0/genie/spaces", body=body)["space_id"])


if __name__ == "__main__":
    main()
