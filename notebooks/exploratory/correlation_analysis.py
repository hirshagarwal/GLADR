import marimo

__generated_with = "0.23.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    from pathlib import Path
    from scripts.ingest_data import import_excel

    import pandas as pd

    import sys
    sys.path.insert(0, '.')
    return (import_excel,)


@app.cell
def load_raw_excel(import_excel):
    import_excel("data/main_sheet/XLSX/Raw 19_04_26.xlsx"),
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
