import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding='utf-8')

WIDTH = 2500
HEIGHT = 843

# Tuned font size: exactly 130px Bold Sans-serif
font_main = ImageFont.truetype('C:/Windows/Fonts/msjhbd.ttc', 130)

# Create base canvas with crisp off-white / light slate 50
img = Image.new('RGB', (WIDTH, HEIGHT), color=(248, 250, 252)) # Slate 50
draw = ImageDraw.Draw(img)

# 3-Grid columns: strictly 2-4 Chinese characters, 130px text, 300px icon
columns = [
    {
        "x0": 0, "x1": 833,
        "title": "商品型錄",
        "card_bg": (255, 255, 255),
        "card_border": (226, 232, 240),      # Slate 200
        "icon_bg": (239, 246, 255),          # Blue 50
        "icon_border": (191, 219, 254),      # Blue 200
        "accent": (37, 99, 235),             # Blue 600
        "icon_type": "catalog"
    },
    {
        "x0": 833, "x1": 1667,
        "title": "訂單進度",
        "card_bg": (255, 255, 255),
        "card_border": (226, 232, 240),      # Slate 200
        "icon_bg": (236, 253, 245),          # Emerald 50
        "icon_border": (167, 243, 208),      # Emerald 200
        "accent": (5, 150, 105),             # Emerald 600
        "icon_type": "tracking"
    },
    {
        "x0": 1667, "x1": 2500,
        "title": "聯絡客服",
        "card_bg": (255, 255, 255),
        "card_border": (226, 232, 240),      # Slate 200
        "icon_bg": (245, 243, 255),          # Violet 50
        "icon_border": (221, 214, 254),      # Violet 200
        "accent": (124, 58, 237),            # Violet 600
        "icon_type": "support"
    },
]

for col in columns:
    pad_x = 20
    pad_y = 20
    cx0 = col["x0"] + pad_x
    cx1 = col["x1"] - pad_x
    cy0 = pad_y
    cy1 = HEIGHT - pad_y

    card_center_x = (cx0 + cx1) // 2

    # Draw rounded rectangle for clean white card
    draw.rounded_rectangle(
        [(cx0, cy0), (cx1, cy1)],
        radius=36,
        fill=col["card_bg"],
        outline=col["card_border"],
        width=3
    )

    # Vector Icon Circle: diameter 300px (radius 150px)
    icon_cy = cy0 + 260
    icon_bg_r = 150
    draw.ellipse(
        [(card_center_x - icon_bg_r, icon_cy - icon_bg_r),
         (card_center_x + icon_bg_r, icon_cy + icon_bg_r)],
        fill=col["icon_bg"],
        outline=col["icon_border"],
        width=4
    )

    if col["icon_type"] == "catalog":
        bx, by = card_center_x, icon_cy
        draw.rectangle([(bx - 60, by - 30), (bx + 60, by + 66)], outline=col["accent"], width=9)
        draw.arc([(bx - 36, by - 75), (bx + 36, by - 6)], start=180, end=0, fill=col["accent"], width=9)
        draw.line([(bx - 24, by + 12), (bx + 24, by + 12)], fill=col["accent"], width=8)
    elif col["icon_type"] == "tracking":
        bx, by = card_center_x, icon_cy
        draw.rectangle([(bx - 70, by - 36), (bx + 20, by + 42)], outline=col["accent"], width=9)
        draw.polygon([(bx + 20, by - 9), (bx + 56, by - 9), (bx + 70, by + 15), (bx + 70, by + 42), (bx + 20, by + 42)], outline=col["accent"], width=9)
        draw.ellipse([(bx - 48, by + 30), (bx - 18, by + 60)], fill=col["icon_bg"], outline=col["accent"], width=8)
        draw.ellipse([(bx + 32, by + 30), (bx + 62, by + 60)], fill=col["icon_bg"], outline=col["accent"], width=8)
    elif col["icon_type"] == "support":
        bx, by = card_center_x, icon_cy
        draw.rounded_rectangle([(bx - 68, by - 52), (bx + 68, by + 38)], radius=26, outline=col["accent"], width=9)
        draw.polygon([(bx - 20, by + 38), (bx - 6, by + 64), (bx + 12, by + 38)], fill=col["icon_bg"], outline=col["accent"])
        draw.line([(bx - 20, by + 38), (bx + 12, by + 38)], fill=col["icon_bg"], width=13)
        for dx in (-30, 0, 30):
            draw.ellipse([(bx + dx - 8, by - 14), (bx + dx + 8, by + 2)], fill=col["accent"])

    # Tuned CTA Text: 130px Bold
    t_box = font_main.getbbox(col["title"])
    tw = t_box[2] - t_box[0]
    th = t_box[3] - t_box[1]
    title_y = cy0 + 490
    draw.text((card_center_x - tw // 2, title_y), col["title"], font=font_main, fill=(15, 23, 42))

    # Bottom accent pill bar
    bar_w = 180
    bar_h = 10
    draw.rounded_rectangle(
        [(card_center_x - bar_w // 2, cy1 - 60), (card_center_x + bar_w // 2, cy1 - 60 + bar_h)],
        radius=5,
        fill=col["accent"]
    )

    # Subtle column separator
    if col["x1"] < WIDTH:
        draw.line([(col["x1"], 40), (col["x1"], HEIGHT - 40)], fill=(226, 232, 240), width=2)

# Save images
assets_dir = Path("d:/3dollar_erp/assets")
assets_dir.mkdir(parents=True, exist_ok=True)
project_img_path = assets_dir / "rich_menu_2500x843.png"

artifacts_dir = Path(r"C:\Users\pigmao\.gemini\antigravity\brain\40498827-37c8-4e09-8e69-e29221964926")
artifact_img_path = artifacts_dir / "rich_menu_preview.png"

img.save(project_img_path, format="PNG", optimize=True)
img.save(artifact_img_path, format="PNG", optimize=True)

size_kb = project_img_path.stat().st_size / 1024
print(f"Generated 130px Rich Menu image:")
print(f"- Project path: {project_img_path} ({size_kb:.1f} KB)")
print(f"- Artifact path: {artifact_img_path}")
