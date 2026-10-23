from dataclasses import dataclass
from typing import Callable, List, Dict, Any, Optional

@dataclass
class ReportDefinition:
    slug: str
    title: str
    description: str
    builder_func: Callable
    columns: List[Dict[str, str]]
    supported_filters: List[str]
    totals: List[str]
    export_supported: bool = True
    display_in_millions: bool = False

class ReportRegistry:
    def __init__(self):
        self._reports = {}

    def register(self, report_def: ReportDefinition):
        self._reports[report_def.slug] = report_def

    def get_report(self, slug: str) -> Optional[ReportDefinition]:
        return self._reports.get(slug)

    def get_all(self) -> List[ReportDefinition]:
        return list(self._reports.values())

registry = ReportRegistry()
