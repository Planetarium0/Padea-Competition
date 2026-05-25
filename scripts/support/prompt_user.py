import tkinter as tk


def prompt_user(question: str) -> str:
    result: dict[str, str | None] = {"answer": None}

    def submit() -> None:
        result["answer"] = answer_box.get("1.0", tk.END).strip()
        root.destroy()

    root = tk.Tk()
    root.title("Prompt")

    # Selectable prompt text
    prompt_box = tk.Text(root, height=4, width=50, wrap="word")
    prompt_box.insert("1.0", question)
    prompt_box.config(state="disabled")
    prompt_box.pack(padx=10, pady=10)

    # User response area
    answer_box = tk.Text(root, height=6, width=50)
    answer_box.pack(padx=10, pady=10)

    # Submit button
    button = tk.Button(root, text="Submit", command=submit)
    button.pack(pady=10)

    root.mainloop()

    return result["answer"] or ""
