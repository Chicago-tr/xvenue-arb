import os
from datetime import datetime, timedelta

import numpy as np
from dotenv import load_dotenv
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import PandasUDFType, col, pandas_udf
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StructField,
    StructType,
    TimestampType,
)
from scipy import stats
from update import update_ts


def run_spark():
    load_dotenv()
    PJAR = os.getenv("PJAR")
    JDBC_URL = os.getenv("JDBC_URL")

    spark = (
        SparkSession.builder.appName("CryptoAnalysis")
        .config("spark.jars", PJAR)
        .getOrCreate()
    )
    # Read etl state to extract the most recently analyzed data date (will use this so we don't analyse the same data twice)
    etl_df = (
        spark.read.format("jdbc")
        .option("url", JDBC_URL)
        .option("dbtable", "etl_state")
        .option("driver", "org.postgresql.Driver")
        .load()
        .filter(F.col("id") == "bars_and_cross_spread_1m")
    )

    # Retrieving the latest timestamp we processed or setting a default
    etl_row = etl_df.select("last_processed").head(1)
    if etl_row:
        last_processed_ts = etl_row[0]["last_processed"]

    else:
        default_date = datetime.fromtimestamp(0)
        last_processed_ts = default_date

    # Loading the prices table
    quotes_df = (
        spark.read.format("jdbc")
        .option("url", JDBC_URL)
        .option("dbtable", "prices")
        .option("driver", "org.postgresql.Driver")
        .load()
    )

    next_minute = (last_processed_ts + timedelta(minutes=1)).replace(
        second=0, microsecond=0
    )
    # Take only data past timestamp cutoff and then begin at the next full minute boundary
    quotes_df_filtered = quotes_df.filter(F.col("timestamp") > F.lit(last_processed_ts))
    quotes_df_filtered_minute = quotes_df_filtered.filter(
        F.col("timestamp") >= F.lit(next_minute)
    )

    # Get the latest timestamp for rows that are actually written
    max_ts_row = quotes_df_filtered_minute.agg(F.max("timestamp").alias("max_ts")).head(1)
    new_last_ts = None
    if max_ts_row and max_ts_row[0]["max_ts"] is not None:
        new_last_ts = max_ts_row[0]["max_ts"]

    # Table with derived columns
    quotes_with_features = (
        quotes_df_filtered_minute.withColumn(
            "mid_price", F.round(((F.col("bid") + F.col("ask")) / 2), 2)
        )
        .withColumn("spread", F.col("ask") - F.col("bid"))
        .withColumn(
            "rel_spread_bps", (F.col("spread") / F.col("mid_price")) * F.lit(10000.0)
        )
    )

    # Create column with minute buckets
    quotes_bucketed = quotes_with_features.withColumn(
        "bar_ts", F.date_trunc("minute", F.col("timestamp"))
    )

    # Use buckets to aggregate by exchange, asset, and time
    bars_1m = quotes_bucketed.groupBy("exchange_id", "symbol_id", "bar_ts").agg(
        F.first("mid_price").alias("open_mid"),
        F.max("mid_price").alias("high_mid"),
        F.min("mid_price").alias("low_mid"),
        F.last("mid_price").alias("close_mid"),
        F.avg("spread").alias("avg_spread"),
        F.avg("rel_spread_bps").alias("avg_rel_spread_bps"),
    )

    cross_ex_spread = (
        bars_1m.groupBy("symbol_id", "bar_ts")
        .agg(
            F.min("close_mid").alias("min_mid"),
            F.max("close_mid").alias("max_mid"),
        )
        .withColumn("cross_spread", F.col("max_mid") - F.col("min_mid"))
        .withColumn(
            "cross_spread_bps",
            (F.col("cross_spread") / F.col("min_mid")) * F.lit(10000.0),
        )
    )

    # Can print tables directly here (debugging), examples:
    #
    # cross_ex_spread.show(10, truncate=False)
    # bars_1m.show(10, truncate=False)
    # quotes_with_features.printSchema()
    # quotes_with_features.show(5, truncate=False)
    # quotes_bucketed.printSchema()
    # quotes_bucketed.show(5)

    # Writes analysis tables to psql database
    bars_1m_final = bars_1m.dropDuplicates(["symbol_id", "exchange_id", "bar_ts"])
    c_spread_final = cross_ex_spread.dropDuplicates(["symbol_id", "bar_ts"])

    bars_1m_final.write.format("jdbc").option("url", JDBC_URL).option(
        "dbtable", "bars_1m"
    ).option("driver", "org.postgresql.Driver").mode("append").save()

    c_spread_final.write.format("jdbc").option("url", JDBC_URL).option(
        "dbtable", "cross_ex_spread_1m"
    ).option("driver", "org.postgresql.Driver").mode("append").save()

    VENUE_PAIRS = [{"target": 2, "ref": 1}, {"target": 1, "ref": 2}]

    output_schema = StructType(
        [
            StructField("symbol_id", LongType(), True),
            StructField("bar_ts", TimestampType(), True),
            StructField("residual", DoubleType(), True),
            StructField("residual_bps", DoubleType(), True),
            StructField("regression_beta", DoubleType(), True),
        ]
    )

    @pandas_udf(output_schema, PandasUDFType.GROUPED_MAP)
    def compute_regression_residuals(pdf):
        # Rolling OLS: Using all available history up to max of 500 bars
        pdf = pdf.sort_values("bar_ts").reset_index(drop=True)
        residuals = np.full(len(pdf), np.nan)
        residual_bps = np.full(len(pdf), np.nan)
        betas = np.full(len(pdf), np.nan)

        for i in range(20, len(pdf)):  # Start after 20 bars minimum
            # Dynamic window: all available (500 max)
            window_start = max(0, (i - 500))
            window_slice = pdf.loc[window_start:i, ["close_mid", "ref_price"]]

            # validation using 15+ points
            y = window_slice["close_mid"].dropna()
            x = window_slice["ref_price"].dropna()

            if len(y) >= 15 and len(x) == len(y):
                slope, intercept, _, _, _ = stats.linregress(x, y)
                predicted = intercept + slope * pdf.loc[i, "ref_price"]
                residuals[i] = pdf.loc[i, "close_mid"] - predicted
                residual_bps[i] = (residuals[i] / pdf.loc[i, "close_mid"]) * 10000
                betas[i] = slope

        pdf = pdf.copy()
        pdf["residual"] = residuals
        pdf["residual_bps"] = residual_bps
        pdf["regression_beta"] = betas
        return pdf[["symbol_id", "bar_ts", "residual", "residual_bps", "regression_beta"]].reset_index(
            drop=True
        )

    bars_1m_reg = (
        spark.read.format("jdbc")
        .option("url", JDBC_URL)
        .option("dbtable", "bars_1m")
        .option("driver", "org.postgresql.Driver")
        .load()
    )

    cutoff_output = last_processed_ts
    cutoff_threshold = F.current_timestamp() - F.expr("INTERVAL 4 HOURS")
    bars_last_four_hours = bars_1m_reg.filter(col("bar_ts") > cutoff_threshold)
    recent_output_bars = bars_1m_reg.filter(col("bar_ts") > cutoff_output)

    # Can check here if bar count looks good

    # print(f"Full context: {bars_1m_reg.count()} bars")
    # print(f"New output: {recent_output_bars.count()} bars")

    recent_bars = bars_1m_reg.filter(col("bar_ts") > next_minute)

    print(f"Processing {recent_bars.count()} recent bars")
    active_symbols = recent_bars.select("symbol_id").distinct()
    print(f"Active symbols: {active_symbols.count()}")

    # Join target and reference venue prices
    for pair in VENUE_PAIRS:
        target_id = pair["target"]
        ref_id = pair["ref"]

        regression_bars = (
            bars_last_four_hours.alias("target")
            .filter(col("exchange_id") == target_id)
            .join(
                bars_last_four_hours.alias("ref")
                .filter(col("exchange_id") == ref_id)
                .select("symbol_id", "bar_ts", col("close_mid").alias("ref_price")),
                ["symbol_id", "bar_ts"],
                "inner",
            )
            .select(
                col("target.symbol_id").alias("symbol_id"),
                col("target.bar_ts").alias("bar_ts"),
                col("target.close_mid").alias("close_mid"),
                col("ref_price"),
            )
            .groupBy("symbol_id")
            .apply(compute_regression_residuals)
        )

        new_regression_results = regression_bars.filter(
            col("bar_ts") > F.lit(cutoff_output)
        )
        # Write to new table
        new_regression_results.select(
            col("symbol_id"),
            col("bar_ts"),
            F.lit(target_id).alias("target_exchange_id"),
            F.lit(ref_id).alias("ref_exchange_id"),
            col("residual"),
            col("residual_bps").alias("regression_residual_bps"),
            col("regression_beta"),
        ).write.format("jdbc").option("url", JDBC_URL).option(
            "dbtable", "cross_ex_regression"
        ).option("driver", "org.postgresql.Driver").mode("append").save()

    if new_last_ts is not None:
        print("Updating last_processed to:", new_last_ts)
        update_ts(new_last_ts)

    spark.stop()
    return


if __name__ == "__main__":
    run_spark()
