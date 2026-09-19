import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessagingApiBlob,
)
from linebot.v3.oauth import ChannelAccessToken
from src.channel_ui.line_bot.rich_menu import build_rich_menu_request

# 1. Read .env
env_path = project_root / ".env"
env_vars = {}
with open(env_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env_vars[k.strip()] = v.strip()

channel_id = env_vars.get("LINE_CHANNEL_ID")
channel_secret = env_vars.get("LINE_CHANNEL_SECRET")

if not channel_id or not channel_secret:
    print("Error: LINE_CHANNEL_ID or LINE_CHANNEL_SECRET not found in .env")
    sys.exit(1)

print("1. Exchanging credentials for Stateless Access Token v3...")
oauth_client = ChannelAccessToken()
token_res = oauth_client.issue_stateless_channel_token_by_client_secret(
    client_id=str(channel_id),
    client_secret=str(channel_secret),
)
token = token_res.access_token
print("Token acquired successfully!")

# 2. Upload Rich Menu
image_path = project_root / "assets" / "rich_menu_2500x843.png"
if not image_path.exists():
    print(f"Error: Image not found at {image_path}")
    sys.exit(1)

print(f"Image found at {image_path} ({image_path.stat().st_size / 1024:.1f} KB)")

config = Configuration(access_token=token)
with ApiClient(config) as api_client:
    messaging_api = MessagingApi(api_client)
    messaging_blob_api = MessagingApiBlob(api_client)

    # 2.1 Clean up old rich menus (optional/idempotent check)
    existing = messaging_api.get_rich_menu_list()
    print(f"Existing rich menus count: {len(existing.richmenus)}")
    for rm in existing.richmenus:
        print(f"Deleting older rich menu: {rm.rich_menu_id} ({rm.name})")
        messaging_api.delete_rich_menu(rm.rich_menu_id)

    # 2.2 Create Rich Menu
    print("2. Creating new Rich Menu specification...")
    req = build_rich_menu_request()
    res = messaging_api.create_rich_menu(req)
    rich_menu_id = res.rich_menu_id
    print(f"Rich Menu created with ID: {rich_menu_id}")

    # 2.3 Upload Image
    print("3. Uploading 2500x843 Light Theme PNG image...")
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    messaging_blob_api.set_rich_menu_image(
        rich_menu_id=rich_menu_id,
        body=img_bytes,
        _headers={"Content-Type": "image/png"},
    )
    print("Image uploaded successfully!")

    # 2.4 Set Default Rich Menu for all users
    print("4. Setting as default Rich Menu for all users...")
    messaging_api.set_default_rich_menu(rich_menu_id)
    print(f"SUCCESS: Rich Menu {rich_menu_id} is now the default for all users!")
