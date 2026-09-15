from etl.pipeline.fact_perizinan.pipeline import (
    run_fact_perizinan_pipeline,
)


def main():
    result = run_fact_perizinan_pipeline(
        dry_run=True
    )

    print(
        "FACT PERIZINAN PIPELINE DRY RUN PASSED"
    )

    print(
        f"Fact rows           : "
        f"{result['fact_rows']}"
    )

    print(
        f"Daily coverage rows : "
        f"{result['daily_coverage_rows']}"
    )

    print(
        f"Loaded rows         : "
        f"{result['loaded_rows']}"
    )

    print(
        f"Dry run             : "
        f"{result['dry_run']}"
    )


if __name__ == "__main__":
    main()
