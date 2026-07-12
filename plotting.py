import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _autolabel(ax, rects):
    """Annotate each bar with its value, skipping zero-height bars."""
    for rect in rects:
        height = rect.get_height()
        if height != 0:
            ax.annotate(f'{round(height, 2)}',
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3 if height > 0 else -13),
                        textcoords="offset points",
                        ha='center', va='bottom' if height > 0 else 'top',
                        fontsize=9, fontweight='bold')


def plot_graphs_per_person(data):
    """Save an individual PNG bar chart for each person in data."""
    plt.close('all')
    if not data:
        return print("No data to plot.")

    path_logs = "logs/img"
    Path(path_logs).mkdir(parents=True, exist_ok=True)

    for person, daily in data.items():
        dates = sorted(daily.keys())
        labels = [d.strftime('%d/%m') for d in dates]
        comp = [daily[d]['completed'] for d in dates]
        rem = [daily[d]['remaining_dec'] for d in dates]

        fig, ax = plt.subplots(figsize=(12, 6))
        x = range(len(dates))
        rects1 = ax.bar([i - 0.2 for i in x], comp, 0.4, label='Comp. Added', color='#2ecc71')
        rects2 = ax.bar([i + 0.2 for i in x], rem, 0.4, label='Rem. Decr.', color='#3498db')

        _autolabel(ax, rects1)
        _autolabel(ax, rects2)

        ax.set_title(f"Sprint Health: {person}", fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45)
        ax.legend()
        plt.tight_layout()
        plt.grid(True, alpha=0.3)

        safe_name = "".join(c for c in person if c.isalnum() or c in (' ', '_')).replace(' ', '_').lower()
        plt.savefig(f"{path_logs}/sprint_health_{safe_name}.png")
        print(f"Saved graph: sprint_health_{safe_name}.png")
        plt.close(fig)


def plot_all_graphs(data):
    """Create a single combined PNG with all people's charts in a 2-column grid."""
    if not data:
        return None

    n_cols = 2
    n_rows = math.ceil(len(data) / n_cols)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(24, 8 * n_rows))

    # Ensure axes is always a 2D array for uniform indexing
    if n_rows == 1 and n_cols == 1:
        axes = [[axes]]
    elif n_rows == 1:
        axes = [axes]
    elif n_cols == 1:
        axes = [[ax] for ax in axes]

    sorted_people = sorted(data.keys())

    for idx, person in enumerate(sorted_people):
        row = idx // n_cols
        col = idx % n_cols
        ax = axes[row][col]
        daily = data[person]

        dates = sorted(daily.keys())
        labels = [d.strftime('%d/%m') for d in dates]
        comp = [daily[d]['completed'] for d in dates]
        rem = [daily[d]['remaining_dec'] for d in dates]

        x = range(len(dates))
        rects1 = ax.bar([i - 0.2 for i in x], comp, 0.4, label='Comp. Added', color='#2ecc71')
        rects2 = ax.bar([i + 0.2 for i in x], rem, 0.4, label='Rem. Decr.', color='#3498db')

        _autolabel(ax, rects1)
        _autolabel(ax, rects2)

        ax.set_title(f"Sprint Health: {person}", fontsize=14, fontweight='bold')
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, rotation=45)
        ax.legend()
        ax.grid(True, alpha=0.3)

    # Hide unused axes when the number of people is odd
    total_slots = n_rows * n_cols
    for idx in range(len(sorted_people), total_slots):
        row = idx // n_cols
        col = idx % n_cols
        axes[row][col].set_visible(False)

    fig.tight_layout(pad=3.0)

    output_path = "sprint_health_combined.png"
    fig.savefig(output_path, dpi=200)
    print(f"Saved combined graph: {output_path}")
    plt.close(fig)

    return output_path


def _format_metric(value):
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip('0').rstrip('.')
    return str(value)


def plot_burndown(burndown_data, output_path="sprint_burndown.png"):
    """Save a dark-theme burndown chart PNG."""
    plt.close('all')
    if not burndown_data or not burndown_data.get('dates'):
        print("No burndown data to plot.")
        return None

    dates = burndown_data['dates']
    labels = [day.strftime('%d/%m/%Y') for day in dates]
    x = list(range(len(dates)))
    actual = burndown_data['actual_remaining']
    capacity = burndown_data['remaining_capacity']
    ideal = burndown_data['ideal_trend']
    summary = burndown_data.get('summary', {})
    x_actual = [idx for idx, value in enumerate(actual) if value is not None]
    actual_values = [value for value in actual if value is not None]

    fig, ax = plt.subplots(figsize=(18, 10))
    fig.patch.set_facecolor('#111417')
    ax.set_facecolor('#111417')

    if actual_values:
        ax.fill_between(x_actual, actual_values, color='#4db4ff', alpha=0.95, label='Remaining')
        ax.plot(x_actual, actual_values, color='#4db4ff', linewidth=2)
    else:
        ax.plot([], [], color='#4db4ff', linewidth=2, label='Remaining')
    ax.plot(x, capacity, color='#a8e063', linewidth=2, linestyle='--', label='Remaining Capacity')
    ax.plot(x, ideal, color='#a8a18f', linewidth=2, label='Ideal Trend')

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=0, ha='center', color='#aaa')
    ax.tick_params(axis='y', colors='#aaa')
    ax.grid(True, axis='y', color='#33383d', alpha=0.6, linewidth=0.8)
    ax.grid(False, axis='x')

    for spine in ax.spines.values():
        spine.set_color('#aaa')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    max_value = max(actual_values + capacity + ideal + [1])
    ax.set_ylim(0, max_value * 1.15)
    ax.set_xlim(-0.5, len(x) - 0.5)

    start_label = summary.get('start_date', dates[0]).strftime('%d/%m/%Y')
    end_label = summary.get('end_date', dates[-1]).strftime('%d/%m/%Y')
    fig.text(0.03, 0.94, f"{start_label} - {end_label}", color='#b8b8b8', fontsize=13)

    metric_color = '#e2e2e2'
    label_color = '#b8b8b8'
    fig.text(0.03, 0.85, "Completed", color=label_color, fontsize=13)
    fig.text(0.09, 0.842, f"{_format_metric(summary.get('completed_percent', 0))}%",
             color=metric_color, fontsize=24)

    fig.text(0.30, 0.85, "Average\nburndown", color=label_color, fontsize=13, ha='center')
    fig.text(0.36, 0.842, _format_metric(summary.get('average_burndown', 0)),
             color=metric_color, fontsize=24)

    fig.text(0.57, 0.85, "Items not\nestimated", color='#6bbcff', fontsize=13, ha='center')
    fig.text(0.62, 0.842, _format_metric(summary.get('items_not_estimated', 0)),
             color=metric_color, fontsize=24)

    fig.text(0.92, 0.915, _format_metric(summary.get('remaining_work', 0)),
             color=metric_color, fontsize=18, ha='right')
    fig.text(0.92, 0.89, "Remaining Work, Remaining", color=label_color, fontsize=12, ha='right')
    fig.text(0.92, 0.83, _format_metric(summary.get('total_scope_increase', 0)),
             color=metric_color, fontsize=20, ha='right')
    fig.text(0.84, 0.815, "Total Scope\nIncrease", color=label_color, fontsize=12, ha='right')

    legend = ax.legend(loc='upper left', bbox_to_anchor=(0.0, -0.12), ncol=3,
                       frameon=False, fontsize=12, handlelength=1.2, handletextpad=0.5)
    for text in legend.get_texts():
        text.set_color('#d0d0d0')

    fig.subplots_adjust(left=0.06, right=0.96, top=0.76, bottom=0.18)

    fig.savefig(output_path, dpi=200, facecolor=fig.get_facecolor())
    print(f"Saved burndown graph: {output_path}")
    plt.close(fig)
    return output_path


def generate_all_output(data):
    """Generate individual PNGs per person and a single combined image."""
    plot_graphs_per_person(data)
    combined_path = plot_all_graphs(data)
    return combined_path
