"""Policy experience data: bronze -> silver with data-quality expectations.

Lakeflow Declarative Pipeline (serverless). Auto Loader picks up every extract that
lands in extract_landing/incoming/ exactly once; expectations drop and quarantine bad rows,
and the pipeline UI shows the DQ metrics per expectation.
"""
import dlt
from pyspark.sql import functions as F

LANDING = spark.conf.get("landing_path")

POLICY_YEARS_SCHEMA = """
policy_id STRING, calendar_year INT, age INT, duration_years INT, exposure_years DOUBLE,
death INT, disability_incidence INT, surrender INT, paid_up INT, status_start STRING
"""

DQ_RULES = {
    "policy_id_present": "policy_id IS NOT NULL",
    "exposure_in_range": "exposure_years > 0 AND exposure_years <= 1",
    "age_plausible": "age BETWEEN 15 AND 115",
    "events_binary": "death IN (0, 1) AND surrender IN (0, 1) AND paid_up IN (0, 1)",
}
ALL_RULES = " AND ".join(f"({r})" for r in DQ_RULES.values())


@dlt.table(name="bronze_policy_years",
           comment="Raw experience rows exactly as received, one row per policy x calendar year, with source file lineage.")
def bronze_policy_years():
    return (spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "csv")
            .option("header", "true")
            .schema(POLICY_YEARS_SCHEMA)
            .load(f"{LANDING}/incoming/")
            .withColumn("source_file", F.col("_metadata.file_name"))
            .withColumn("ingested_at", F.current_timestamp()))


@dlt.table(name="silver_policy_years",
           comment="Validated experience. Rows failing any DQ rule are dropped here and kept in quarantine_policy_years.")
@dlt.expect_all_or_drop(DQ_RULES)
def silver_policy_years():
    return dlt.read_stream("bronze_policy_years")


@dlt.table(name="quarantine_policy_years",
           comment="Rows that failed a data-quality rule — kept for the actuary to inspect, never silently lost.")
def quarantine_policy_years():
    return dlt.read_stream("bronze_policy_years").where(f"NOT ({ALL_RULES}) OR ({ALL_RULES}) IS NULL")


def _ref(name):
    return (spark.read.format("csv").option("header", "true").option("inferSchema", "true")
            .load(f"{LANDING}/reference/{name}.csv"))


@dlt.table(name="silver_policies", comment="Policy master data (synthetic): scheme, product, member attributes, benefits.")
@dlt.expect_or_drop("policy_id_present", "policy_id IS NOT NULL")
def silver_policies():
    return (_ref("policies").withColumn("birth_date", F.to_date("birth_date"))
            .withColumn("entry_date", F.to_date("entry_date")))


@dlt.table(name="silver_disability_claims", comment="Disability (loss of earning capacity) claims with duration and outcome — survival data.")
def silver_disability_claims():
    return _ref("disability_claims")


@dlt.table(name="silver_base_mortality", comment="Standard mortality table qx by age and sex with annual improvement rates.")
def silver_base_mortality():
    return _ref("base_mortality")


@dlt.table(name="silver_economic_scenarios", comment="Real-world economic scenario set (1,000 scenarios x 60 years): short rate, equity return, inflation.")
def silver_economic_scenarios():
    return _ref("economic_scenarios")
