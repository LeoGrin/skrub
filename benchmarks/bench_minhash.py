import pickle
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from argparse import ArgumentParser

from pathlib import Path

from utils import monitor, parse_func_repr, find_result, default_parser
from dirty_cat import MinHashEncoder
from dirty_cat.tests.utils import generate_data


benchmark_name = "minhash_batch_comparison"


@monitor(
    memory=True,
    time=True,
    parametrize={
        "dataset_size": ["medium"],
        "batched": [True, False],
        "n_jobs": [1, 4, 8, 16, 32, 64],
        "batch_per_job": [1, 2, 4],
    },
    save_as=benchmark_name,
    repeat=10,
)
def benchmark(
    dataset_size: str,
    batched: bool,
    n_jobs: int,
    batch_per_job: int,
) -> None:
    X = data[dataset_size]
    MinHashEncoder(batch=batched, n_jobs=n_jobs, 
    batch_per_job=batch_per_job).fit(X).transform(X)


def plot(res: pd.DataFrame):
    sns.set_theme(style="ticks", palette="pastel")

    rows = []
    for i, ser in res.iterrows():
        times = eval(str(ser["time"]))
        memories = eval(str(ser["memory"]))
        _, _, kwargs = parse_func_repr(ser["call"])
        for time, memory in zip(times, memories):
            rows.append((kwargs["batched"], kwargs["batch_per_job"], 
            kwargs["n_jobs"], time, memory))

    df = pd.DataFrame(rows, columns=["batched", "batch_per_job", 
    "n_jobs", "time", "memory"])

    # Create a new columns merging batched and batch_per_job
    # If batch is False, ignore batch_per_job
    df["config"] = df.apply(
        lambda row: f"batched={row['batched']}, batch_per_job={row['batch_per_job']}"
        if row["batched"] == 'True'
        else "batched=False",
        axis=1,
    )

    sns.boxplot(x="n_jobs", y="time", hue="config", data=df)
    plt.show()


if __name__ == "__main__":
    _args = ArgumentParser(
        description="Benchmark for the batch feature of the MinHashEncoder.",
        parents=[default_parser],
    ).parse_args()

    # Generate the data if not already on disk, and keep them in memory.
    data = {}  # Will hold the datasets in memory.
    _data_info = {
        "small": 10_000,
        "medium": 100_000,
    }
    for name, size in _data_info.items():
        data_file = Path(f"data_{name}.pkl")
        if data_file.is_file():
            with data_file.open("rb") as fl:
                data.update({name: pickle.load(fl)})
        else:
            with data_file.open("wb") as fl:
                _gen = generate_data(size).reshape(-1, 1)
                pickle.dump(_gen, fl)
                data.update({name: _gen})

    if _args.run:
        df = benchmark()
    else:
        result_file = find_result(benchmark_name)
        df = pd.read_csv(result_file)

    if _args.plot:
        plot(df)
