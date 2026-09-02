"""Regenerate the small synthetic visual-evaluation PNG corpus."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
SIZE = (480, 300)


def canvas(title):
    image = Image.new("RGB", SIZE, "white")
    draw = ImageDraw.Draw(image)
    draw.text((15, 12), title, fill="black")
    return image, draw


def save(name, painter):
    image, draw = canvas(name.replace("-", " ").title())
    painter(draw)
    image.save(ROOT / f"{name}.png", optimize=True)


save("pie-chart", lambda d: (
    d.pieslice((40, 55, 250, 265), 0, 194, fill="#4472c4"),
    d.pieslice((40, 55, 250, 265), 194, 298, fill="#ed7d31"),
    d.pieslice((40, 55, 250, 265), 298, 360, fill="#a5a5a5"),
    d.text((285, 80), "Category A 54%", fill="black"),
    d.text((285, 120), "Category B 29%", fill="black"),
    d.text((285, 160), "Other 17%", fill="black"),
))
save("line-chart", lambda d: (
    d.line((55, 250, 440, 250), fill="black", width=2), d.line((55, 55, 55, 250), fill="black", width=2),
    d.line((65, 220, 185, 175, 305, 125, 425, 80), fill="#4472c4", width=4),
    d.text((55, 260), "1940", fill="black"), d.text((175, 260), "1960", fill="black"),
    d.text((295, 260), "1990", fill="black"), d.text((410, 260), "2020", fill="black"),
    d.text((65, 205), "10", fill="black"), d.text((410, 62), "40", fill="black"),
))
save("bar-chart", lambda d: (
    d.rectangle((70, 170, 145, 250), fill="#4472c4"), d.rectangle((200, 110, 275, 250), fill="#ed7d31"),
    d.rectangle((330, 60, 405, 250), fill="#70ad47"), d.text((85, 255), "A 20", fill="black"),
    d.text((215, 255), "B 35", fill="black"), d.text((345, 255), "C 48", fill="black"),
))
save("process-diagram", lambda d: (
    d.rectangle((30, 110, 120, 175), outline="black", width=3), d.text((68, 135), "A", fill="black"),
    d.line((120, 142, 195, 142), fill="black", width=3), d.polygon((195, 142, 182, 134, 182, 150), fill="black"),
    d.rectangle((200, 110, 290, 175), outline="black", width=3), d.text((238, 135), "B", fill="black"),
    d.line((290, 142, 365, 142), fill="black", width=3), d.polygon((365, 142, 352, 134, 352, 150), fill="black"),
    d.rectangle((370, 110, 460, 175), outline="black", width=3), d.text((408, 135), "C", fill="black"),
))
save("branching-diagram", lambda d: (
    d.rectangle((185, 45, 295, 95), outline="black", width=3), d.text((220, 63), "Start", fill="black"),
    d.line((240, 95, 240, 130), fill="black", width=3), d.line((100, 130, 380, 130), fill="black", width=3),
    d.line((100, 130, 100, 175), fill="black", width=3), d.line((380, 130, 380, 175), fill="black", width=3),
    d.rectangle((35, 175, 165, 230), outline="black", width=3), d.text((70, 195), "Path A", fill="black"),
    d.rectangle((315, 175, 445, 230), outline="black", width=3), d.text((350, 195), "Path B", fill="black"),
))
save("table", lambda d: (
    [d.line((35, y, 445, y), fill="black", width=2) for y in (65, 110, 155, 200, 245)],
    [d.line((x, 65, x, 245), fill="black", width=2) for x in (35, 180, 315, 445)],
    d.text((55, 80), "Region", fill="black"), d.text((205, 80), "2023", fill="black"), d.text((345, 80), "2024", fill="black"),
    d.text((55, 125), "North", fill="black"), d.text((215, 125), "18", fill="black"), d.text((355, 125), "24", fill="black"),
    d.text((55, 170), "South", fill="black"), d.text((215, 170), "21", fill="black"), d.text((355, 170), "19", fill="black"),
))
save("meaningful-photo", lambda d: (
    d.rectangle((40, 70, 440, 260), fill="#cfe8ff"), d.ellipse((90, 110, 180, 200), fill="#f4c542"),
    d.rectangle((250, 105, 390, 235), fill="#888888"), d.rectangle((275, 135, 305, 235), fill="#d9edf7"),
    d.rectangle((335, 135, 365, 235), fill="#d9edf7"), d.text((55, 270), "Solar panels beside a community building", fill="black"),
))
save("decorative-background", lambda d: (
    d.ellipse((20, 80, 190, 250), fill="#d9e2f3"), d.ellipse((290, 70, 460, 240), fill="#fce4d6"),
    d.text((160, 135), "Course Overview", fill="black"),
))
save("text-dominant", lambda d: (
    d.text((45, 75), "Three review principles", fill="black"), d.text((65, 120), "1. Preserve evidence", fill="black"),
    d.text((65, 155), "2. Record provenance", fill="black"), d.text((65, 190), "3. Flag uncertainty", fill="black"),
))
save("ambiguous-visual", lambda d: (
    d.line((60, 230, 160, 90, 260, 180, 410, 70), fill="#777777", width=5),
    d.ellipse((145, 75, 175, 105), fill="#ed7d31"), d.ellipse((245, 165, 275, 195), fill="#70ad47"),
    d.text((60, 250), "Unlabeled schematic", fill="black"),
))
