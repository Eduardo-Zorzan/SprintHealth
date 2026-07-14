import customtkinter as ctk


def populate_reassignment_table(reassign_table, reassign_count_label, reassignments, rel_x, rel_w):
    """Populate the reassignment table with data."""
    for child in reassign_table.winfo_children():
        child.destroy()

    if not reassignments:
        ctk.CTkLabel(
            reassign_table,
            text="No reassignments found in the selected period.",
            font=ctk.CTkFont(size=13),
            text_color="#888",
        ).grid(row=0, column=0, columnspan=5, pady=20)
        reassign_count_label.configure(text="0 reassignments found")
        return

    reassign_count_label.configure(text=f"{len(reassignments)} reassignment(s) found")

    row_colors = ["#1e1e1e", "#252525"]

    for i, reassignment in enumerate(reassignments):
        bg_color = row_colors[i % 2]
        row_frame = ctk.CTkFrame(reassign_table, fg_color=bg_color, corner_radius=4, height=36)
        row_frame.grid(row=i, column=0, sticky="ew", padx=0, pady=1)
        row_frame.grid_propagate(False)

        values = [
            str(reassignment['task_id']),
            reassignment['from'],
            reassignment['to'],
            reassignment['date'],
            reassignment['changed_by'],
        ]
        colors = ["#aaa", "#e67e22", "#2ecc71", "#3498db", "#9b59b6"]

        for col, (value, color) in enumerate(zip(values, colors)):
            label = ctk.CTkLabel(
                row_frame,
                text=value,
                font=ctk.CTkFont(size=11),
                text_color=color,
                anchor="center",
            )
            label.place(relx=rel_x[col], rely=0.5, relwidth=rel_w[col], anchor="w")

    print(f"Displayed {len(reassignments)} reassignment(s) in table.")

