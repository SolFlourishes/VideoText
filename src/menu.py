"""
menu.py

Development menu for selecting the pipeline stage.
"""


def select_start_stage():
    """
    Ask the user where to begin the pipeline.

    Returns:
        str
    """

    print()
    print("=" * 40)
    print("VideoText Development Mode")
    print("=" * 40)
    print("1. Full Proceess")
    print("2. OCR")
    print("3. Reading Order")
    print("4. Slide Consolidation")
    print("5. Excel Export")
    print()

    choice = input("Select stage [1]: ").strip()

    if choice == "" or choice == "1":
        return "video"

    if choice == "2":
        return "ocr"

    if choice == "3":
        return "reading_order"

    if choice == "4":
        return "slide_consolidation"

    if choice == "5":
        return "excel"

    print("Invalid selection. Starting Full Pipeline.")

    return "video"