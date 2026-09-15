from etl.load.fact_perizinan.load_fact_perizinan import (
    load_fact_perizinan,
)


def main():
    print(
        "Loader fact_perizinan import OK"
    )

    print(
        f"Function: {load_fact_perizinan.__name__}"
    )


if __name__ == "__main__":
    main()
