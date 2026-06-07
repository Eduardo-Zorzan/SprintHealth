import math
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
        plt.savefig(f"sprint_health_{safe_name}.png")
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


def generate_all_output(data):
    """Generate individual PNGs per person and a single combined image."""
    plot_graphs_per_person(data)
    combined_path = plot_all_graphs(data)
    return combined_path
