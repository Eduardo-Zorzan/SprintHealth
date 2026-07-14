"""Compatibility facade for chart generation helpers."""

from charts.burndown import (
    build_burndown_figure,
    format_metric,
    format_tooltip_value,
    get_burndown_tooltip_data,
    nearest_burndown_index,
    plot_burndown,
)
from charts.time_registration import (
    generate_all_output,
    plot_all_graphs,
    plot_graphs_per_person,
)

__all__ = [
    "build_burndown_figure",
    "format_metric",
    "format_tooltip_value",
    "generate_all_output",
    "get_burndown_tooltip_data",
    "nearest_burndown_index",
    "plot_all_graphs",
    "plot_burndown",
    "plot_graphs_per_person",
]

