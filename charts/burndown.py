from matplotlib.figure import Figure


BACKGROUND_COLOR = '#111417'
REMAINING_COLOR = '#4db4ff'
CAPACITY_COLOR = '#a8e063'
IDEAL_COLOR = '#a8a18f'
GRID_COLOR = '#33383d'
TEXT_COLOR = '#e2e2e2'
LABEL_COLOR = '#b8b8b8'
AXIS_COLOR = '#aaa'

BURNDOWN_SERIES = (
    ('remaining', 'Remaining', REMAINING_COLOR, 'actual_remaining'),
    ('capacity', 'Remaining Capacity', CAPACITY_COLOR, 'remaining_capacity'),
    ('ideal', 'Ideal Trend', IDEAL_COLOR, 'ideal_trend'),
)


def format_metric(value):
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip('0').rstrip('.')
    return str(value)


def format_tooltip_value(value):
    if value is None:
        return "No data"
    text = format_metric(float(value))
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def format_date(value):
    if hasattr(value, "strftime"):
        return value.strftime('%d/%m/%Y')
    return str(value)


def nearest_burndown_index(xdata, total_points):
    if xdata is None or total_points <= 0:
        return None
    index = int(round(xdata))
    if index < 0 or index >= total_points:
        return None
    return index


def get_burndown_tooltip_data(burndown_data, index):
    dates = burndown_data.get('dates') or []
    if index < 0 or index >= len(dates):
        raise IndexError("Burndown tooltip index out of range.")

    series = []
    for key, label, color, data_key in BURNDOWN_SERIES:
        values = burndown_data.get(data_key) or []
        value = values[index] if index < len(values) else None
        series.append({
            'key': key,
            'label': label,
            'color': color,
            'value': value,
            'formatted_value': format_tooltip_value(value),
        })

    return {
        'index': index,
        'date': dates[index],
        'date_label': format_date(dates[index]),
        'series': series,
    }


def _numeric_values(values):
    return [value for value in values if value is not None]


def _summary_date(summary, dates, key, fallback_index):
    value = summary.get(key)
    if value is None and dates:
        value = dates[fallback_index]
    return format_date(value) if value is not None else ""


def build_burndown_figure(burndown_data):
    """Build a dark-theme burndown Matplotlib figure."""
    if not burndown_data or not burndown_data.get('dates'):
        return None, None, {}

    dates = burndown_data['dates']
    labels = [format_date(day) for day in dates]
    x = list(range(len(dates)))
    actual = burndown_data['actual_remaining']
    capacity = burndown_data['remaining_capacity']
    ideal = burndown_data['ideal_trend']
    summary = burndown_data.get('summary', {})
    x_actual = [idx for idx, value in enumerate(actual) if value is not None]
    actual_values = _numeric_values(actual)

    fig = Figure(figsize=(18, 10), dpi=100)
    fig.patch.set_facecolor(BACKGROUND_COLOR)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BACKGROUND_COLOR)

    if actual_values:
        ax.fill_between(x_actual, actual_values, color=REMAINING_COLOR, alpha=0.95, label='Remaining')
        ax.plot(x_actual, actual_values, color=REMAINING_COLOR, linewidth=2)
    else:
        ax.plot([], [], color=REMAINING_COLOR, linewidth=2, label='Remaining')
    ax.plot(x, capacity, color=CAPACITY_COLOR, linewidth=2, linestyle='--', label='Remaining Capacity')
    ax.plot(x, ideal, color=IDEAL_COLOR, linewidth=2, label='Ideal Trend')

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=0, ha='center', color=AXIS_COLOR)
    ax.tick_params(axis='y', colors=AXIS_COLOR)
    ax.grid(True, axis='y', color=GRID_COLOR, alpha=0.6, linewidth=0.8)
    ax.grid(False, axis='x')

    for spine in ax.spines.values():
        spine.set_color(AXIS_COLOR)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    max_candidates = actual_values + _numeric_values(capacity) + _numeric_values(ideal) + [1]
    max_value = max(max_candidates)
    ax.set_ylim(0, max_value * 1.15)
    ax.set_xlim(-0.5, len(x) - 0.5)

    start_label = _summary_date(summary, dates, 'start_date', 0)
    end_label = _summary_date(summary, dates, 'end_date', -1)
    fig.text(0.03, 0.94, f"{start_label} - {end_label}", color=LABEL_COLOR, fontsize=13)

    fig.text(0.92, 0.915, format_metric(summary.get('remaining_work', 0)),
             color=TEXT_COLOR, fontsize=18, ha='right')
    fig.text(0.92, 0.89, "Remaining Work, Remaining", color=LABEL_COLOR, fontsize=12, ha='right')

    legend = ax.legend(loc='upper left', bbox_to_anchor=(0.0, -0.12), ncol=3,
                       frameon=False, fontsize=12, handlelength=1.2, handletextpad=0.5)
    for text in legend.get_texts():
        text.set_color('#d0d0d0')

    fig.subplots_adjust(left=0.06, right=0.96, top=0.84, bottom=0.18)

    series_values = {
        'x': x,
        'remaining': actual,
        'capacity': capacity,
        'ideal': ideal,
    }
    return fig, ax, series_values


def plot_burndown(burndown_data, output_path="sprint_burndown.png"):
    """Save a dark-theme burndown chart PNG."""
    fig, _, _ = build_burndown_figure(burndown_data)
    if fig is None:
        print("No burndown data to plot.")
        return None

    fig.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    fig.clear()
    print(f"Saved burndown graph: {output_path}")
    return output_path

