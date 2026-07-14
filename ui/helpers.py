class RedirectText:
    def __init__(self, text_widget):
        self.output = text_widget

    def write(self, string):
        self.output.insert("end", string)
        self.output.see("end")

    def flush(self):
        pass


def build_combo_values(options, selected=None):
    values = []
    seen = set()

    def add(value):
        text = (value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            values.append(text)

    for option in options:
        add(option)
    add(selected)
    return values or [""]


def build_sprint_combo_values(sprint_options, selected=None):
    values = []
    seen = set()

    def add(value):
        text = (value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            values.append(text)

    for option in sprint_options:
        add(option)
    add(selected)
    return values
