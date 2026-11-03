
import tempfile
from pathlib import Path

from app.croissant_generator import build_croissant
from app.metadata_schema import ExtractedMetadata, MetadataField


def confirmed(value):
    return MetadataField(
        suggested_value=value,
        value=value,
        source="manual",
        evidence="Test",
        confidence=1,
        status="confirmed",
    )


metadata = ExtractedMetadata(
    title=confirmed("Iris dataset"),
    description=confirmed(
        "Dataset containing flower measurements and species."
    ),
    creators=confirmed(["Test creator"]),
    license=confirmed("MIT"),
    dataset_type=MetadataField(
        suggested_value="Tabular dataset",
        value="Tabular dataset",
        status="suggested",
    ),
    data_modality=confirmed("Tabular"),
)

with tempfile.TemporaryDirectory() as temp_dir:

    directory = Path(temp_dir)

    csv_file = directory / "iris.csv"

    csv_file.write_text(
        "sepal_length,sepal_width,species\n"
        "5.1,3.5,setosa\n"
        "4.9,3.0,setosa\n"
        "6.2,3.4,versicolor\n",
        encoding="utf-8",
    )

    inspection = {
        "dataset": {
            "path": "iris.csv",
            "size": csv_file.stat().st_size,
            "format": ".csv",
            "encoding": "utf-8",
            "delimiter": ",",
            "number_of_records": 3,
            "number_of_columns": 3,
            "columns": [
                {"name": "sepal_length", "inferred_type": "number"},
                {"name": "sepal_width", "inferred_type": "number"},
                {"name": "species", "inferred_type": "string"},
            ],
        }
    }

    result = build_croissant(
        dataset_directory=directory,
        dataset_relative_path="iris.csv",
        output_path=directory / "croissant.json",
        source_content_url=(
            "https://raw.githubusercontent.com/"
            "mwaskom/seaborn-data/master/iris.csv"
        ),
        repository_url="https://github.com/mwaskom/seaborn-data",
        metadata=metadata,
        inspection=inspection,
    )

    print("Geração concluída!")
    print("Título:", result["name"])
    print("Criadores:", result["creator"])
    print("Distribuição:", result["distribution"])
    print("Ficheiro criado:", (directory / "croissant.json").exists())
