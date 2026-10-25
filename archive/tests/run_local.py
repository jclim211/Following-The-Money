# Local test: python run_local.py <pipeline_folder> <work_folder>  (needs: pip install pyspark pandas, and Java 17+)
# Expects <work_folder>/test/sample_trans.csv created by make_sample.py
import importlib.util, sys, json
from pyspark.sql import SparkSession
P, S = sys.argv[1], sys.argv[2]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
j1 = load("j1", f"{P}/glue_jobs/01_ingest_clean.py")
j2 = load("j2", f"{P}/glue_jobs/02_account_risk_scoring.py")
spark = SparkSession.builder.master("local[2]").config("spark.sql.shuffle.partitions","4").config("spark.ui.enabled","false").getOrCreate()
spark.sparkContext.setLogLevel("ERROR")
raw = j1.read_raw(spark, f"{S}/test/sample_trans.csv")
clean = j1.clean(raw)
print("raw rows", raw.count(), "clean rows", clean.count())
clean.printSchema()
clean.write.mode("overwrite").partitionBy("txn_date").parquet(f"{S}/test/clean")
cfg = j2.load_config(f"{P}/config/weights.json")
res = j2.run(spark, f"{S}/test/clean", cfg)
res.write.mode("overwrite").partitionBy("txn_date").parquet(f"{S}/test/curated")
df = spark.read.parquet(f"{S}/test/curated").toPandas()
print("account-day rows", len(df), "columns", list(df.columns))
print(df.sort_values(["txn_date","daily_rank"]).head(8)[["txn_date","daily_rank","account_key","risk_score","fan_out","fan_in","pass_through","is_laundering_account"]])
tot = df.is_laundering_account.sum()
for n in [25,50,100,200,500]:
    top = df[df.daily_rank<=n]
    print(f"top {n}/day: recall {100*top.is_laundering_account.sum()/tot:.1f}%  precision {100*top.is_laundering_account.mean():.1f}%")
# baseline
df["base_rank"] = df.groupby("txn_date")["n_txn"].rank(method="first", ascending=False)
for n in [50,100]:
    print(f"baseline top {n}: recall {100*df[df.base_rank<=n].is_laundering_account.sum()/tot:.1f}%")
print("score range", df.risk_score.min(), df.risk_score.max())
print(df.groupby("is_laundering_account")[[c for c in df.columns if c.endswith("_score") and c!="risk_score"]].mean().round(2).T)
