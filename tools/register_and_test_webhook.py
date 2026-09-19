import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from linebot.v3.oauth import ChannelAccessToken

sys.stdout.reconfigure(encoding='utf-8')

project_root = Path(__file__).resolve().parent.parent
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

# 1. Exchange Stateless Token
client = ChannelAccessToken()
res = client.issue_stateless_channel_token_by_client_secret(
    client_id=str(channel_id),
    client_secret=str(channel_secret),
)
token = res.access_token

webhook_url = "https://eyed-penny-motorcycle-asset.trycloudflare.com/api/line/webhook"
print(f"Setting Webhook URL to: {webhook_url}")

# 2. PUT /v2/bot/channel/webhook/endpoint
put_req = urllib.request.Request(
    "https://api.line.me/v2/bot/channel/webhook/endpoint",
    data=json.dumps({"endpoint": webhook_url}).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    },
    method="PUT",
)
try:
    with urllib.request.urlopen(put_req) as resp:
        print(f"Set Webhook Endpoint: HTTP {resp.status}")
except urllib.error.HTTPError as e:
    print(f"Failed to set webhook: HTTP {e.code} - {e.read().decode('utf-8')}")
    sys.exit(1)

# 3. GET /v2/bot/channel/webhook/endpoint to verify
get_req = urllib.request.Request(
    "https://api.line.me/v2/bot/channel/webhook/endpoint",
    headers={"Authorization": f"Bearer {token}"},
    method="GET",
)
with urllib.request.urlopen(get_req) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    print(f"Verified Webhook Endpoint: {data}")

# 4. POST /v2/bot/channel/webhook/test
test_req = urllib.request.Request(
    "https://api.line.me/v2/bot/channel/webhook/test",
    headers={"Authorization": f"Bearer {token}"},
    method="POST",
)
try:
    with urllib.request.urlopen(test_req) as resp:
        test_data = json.loads(resp.read().decode("utf-8"))
        print(f"LINE Webhook Test Result: {test_data}")
except urllib.error.HTTPError as e:
    print(f"Webhook test failed: HTTP {e.code} - {e.read().decode('utf-8')}")
