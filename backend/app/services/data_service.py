from pathlib import Path

from app.core.config import settings
from app.models.dataset import DatasetSummary


class DataService:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def list_datasets(self) -> list[DatasetSummary]:
        if not self.data_dir.exists():
            return []

        datasets: list[DatasetSummary] = []
        for path in sorted(self.data_dir.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_dir():
                continue

            files = sorted(
                str(file.relative_to(path))
                for file in path.rglob("*")
                if file.is_file()
            )
            datasets.append(
                DatasetSummary(
                    name=path.name,
                    file_count=len(files),
                    files=files,
                )
            )

        return datasets


def get_data_service() -> DataService:
    return DataService(settings.data_dir)
