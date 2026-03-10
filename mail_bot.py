import telebot
import requests
import time
import threading
import re
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta
from telebot.types import BotCommand

# ១. ដាក់ Token របស់ Bot អ្នកនៅទីនេះ
BOT_TOKEN = '8617120717:AAFmGvnIBbuKAsOWzieU2lvHqdocisLcXyo'
bot = telebot.TeleBot(BOT_TOKEN)

API_URL = "https://api.mail.tm"
user_emails = {} 

# --- មុខងារសម្រាប់លុបកូដ HTML ឱ្យអក្សរស្អាត ---
def clean_html(raw_html):
    return re.sub(r'<[^>]+>', '', raw_html).strip()

# --- ជំនួយការផ្ញើសារ និងកត់ត្រា ID ដើម្បីទុកលុបពេលវាយ /clean ---
def send_and_track(chat_id, text, parse_mode=None):
    try:
        msg = bot.send_message(chat_id, text, parse_mode=parse_mode)
        if chat_id in user_emails:
            if "msg_ids" not in user_emails[chat_id]:
                user_emails[chat_id]["msg_ids"] = []
            user_emails[chat_id]["msg_ids"].append(msg.message_id)
        return msg
    except Exception as e:
        print(f"Error sending message: {e}")
        return None

# --- មុខងារ /start ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    welcome_text = (
        "សួស្តី! ខ្ញុំជា Bot សម្រាប់ឆែកមើលសារពីគណនី mail.tm របស់អ្នក។\n\n"
        "👉 ប្រើ /login ដើម្បីចូលគណនី\n"
        "👉 ប្រើ /check ដើម្បីមើលសារដោយដៃ\n"
        "👉 ប្រើ /clean ដើម្បីសម្អាតអេក្រង់ Bot ឱ្យស្រឡះ\n\n"
        "🔔 ចំណាំ៖ ពេល Login រួចរាល់ ខ្ញុំនឹងផ្ញើសារថ្មីៗជូនអ្នកដោយស្វ័យប្រវត្តិ!"
    )
    bot.send_message(chat_id, welcome_text)

# --- មុខងារ /login ---
@bot.message_handler(commands=['login'])
def login_email(message):
    msg = bot.reply_to(message, "សូមបញ្ចូលអាសយដ្ឋានអ៊ីមែល (Email Address) របស់អ្នក៖")
    bot.register_next_step_handler(msg, process_email_step)

def process_email_step(message):
    email = message.text.strip()
    msg = bot.reply_to(message, f"អ៊ីមែល៖ {email}\n\nសូមបញ្ចូលលេខសម្ងាត់ (Password) របស់អ្នក៖")
    bot.register_next_step_handler(msg, process_password_step, email)

def process_password_step(message, email):
    password = message.text.strip()
    chat_id = message.chat.id
    bot.send_message(chat_id, "⏳ កំពុងព្យាយាមភ្ជាប់ទៅគណនីរបស់អ្នក...")

    try:
        token_res = requests.post(f"{API_URL}/token", json={"address": email, "password": password})
        if token_res.status_code == 200:
            token = token_res.json()['token']
            # បន្ថែម msg_ids សម្រាប់ទុកកត់ត្រាសារលើអេក្រង់
            user_emails[chat_id] = {"address": email, "password": password, "token": token, "seen_messages": [], "msg_ids": []}
            send_and_track(chat_id, "✅ Login ទទួលបានជោគជ័យ! ឥឡូវនេះអ្នកអាចទុក Bot ចោលបាន។")
            
            res = requests.get(f"{API_URL}/messages", headers={"Authorization": f"Bearer {token}"})
            if res.status_code == 200:
                for m in res.json().get('hydra:member', []):
                    user_emails[chat_id]["seen_messages"].append(m['id'])
        else:
             bot.send_message(chat_id, "❌ Login បរាជ័យ។ អ៊ីមែល ឬលេខសម្ងាត់មិនត្រឹមត្រូវទេ។")
    except Exception as e:
        bot.send_message(chat_id, f"❌ មានកំហុសប្រព័ន្ធ៖ {e}")

# --- មុខងារ /check (មើលសារដោយដៃ) ---
@bot.message_handler(commands=['check'])
def check_email(message):
    chat_id = message.chat.id
    if chat_id not in user_emails:
        bot.send_message(chat_id, "⚠️ សូមប្រើបញ្ជា /login ជាមុនសិន។")
        return
    
    send_and_track(chat_id, "⏳ កំពុងឆែកមើលសារ...")
    token = user_emails[chat_id]['token']
    seen_list = user_emails[chat_id]['seen_messages']
    headers = {"Authorization": f"Bearer {token}"}

    try:
        res = requests.get(f"{API_URL}/messages", headers=headers)
        messages = res.json().get('hydra:member', [])

        if not messages:
            send_and_track(chat_id, "📭 មិនមានសារចូលទេ (Inbox ទទេ)។")
        else:
            for msg in messages[:5]: 
                msg_id = msg['id']
                status = "🆕 **សារថ្មី**" if msg_id not in seen_list else "📭 **សារចាស់**"
                if msg_id not in seen_list: seen_list.append(msg_id) 

                msg_detail = requests.get(f"{API_URL}/messages/{msg_id}", headers=headers).json()
                sender = msg_detail.get('from', {}).get('address', 'Unknown')
                subject = msg_detail.get('subject', 'គ្មានប្រធានបទ')
                text_content = clean_html(msg_detail.get('text', ''))[:500] 
                
                try:
                    dt_utc = datetime.strptime(msg_detail.get('createdAt', '')[:19], "%Y-%m-%dT%H:%M:%S")
                    dt_local = dt_utc + timedelta(hours=7) 
                    time_str = f"{dt_local.strftime('%d/%m/%Y')} ម៉ោង {dt_local.strftime('%H:%M:%S')}"
                except:
                    time_str = "មិនស្គាល់ម៉ោង"

                code_match = re.search(r'\b\d{4,8}\b', text_content)
                code_alert = "👇 **លេខកូដនៅសារខាងក្រោម (ចុចដើម្បី Copy)** 👇\n" if code_match else ""

                email_text = f"{status}\n⏰ ពេលវេលា៖ {time_str}\n👤 ពី៖ {sender}\n📝 ប្រធានបទ៖ {subject}\n{code_alert}💬 ខ្លឹមសារ៖ \n{text_content}...\n"
                send_and_track(chat_id, email_text, parse_mode='Markdown')

                if code_match:
                    otp = code_match.group(0)
                    send_and_track(chat_id, f"`{otp}`", parse_mode='Markdown')

    except Exception as e:
        send_and_track(chat_id, f"❌ មានកំហុស៖ {e}")

# --- មុខងារ /clean (សម្អាតសារពីលើអេក្រង់ Telegram) ---
@bot.message_handler(commands=['clean'])
def clean_bot_chat(message):
    chat_id = message.chat.id
    
    # លុបបញ្ជា /clean ដែលអតិថិជនវាយបញ្ចូលដើម្បីកុំឱ្យរញ៉េរញ៉ៃ
    try:
        bot.delete_message(chat_id, message.message_id)
    except:
        pass

    if chat_id not in user_emails or "msg_ids" not in user_emails[chat_id]:
        bot.send_message(chat_id, "⚠️ មិនមានសារដែលត្រូវលុបទេ ឬអ្នកមិនទាន់ Login។")
        return
        
    msg_ids = user_emails[chat_id]["msg_ids"]
    if not msg_ids:
        return

    # វានឹងលុបសារដែលបានកត់ត្រាទុកម្តងមួយៗ
    deleted_count = 0
    for m_id in msg_ids:
        try:
            bot.delete_message(chat_id, m_id)
            deleted_count += 1
        except:
            pass
            
    # Reset បញ្ជីដែលបានលុបរួច
    user_emails[chat_id]["msg_ids"] = [] 
    
    # លោតសារជោគជ័យ រួចលុបវាចោលវិញដោយស្វ័យប្រវត្តិក្នុងរយៈពេល ៣ វិនាទី
    success_msg = bot.send_message(chat_id, f"✅ បានសម្អាតអេក្រង់រួចរាល់! (សារក្នុង mail.tm នៅរក្សាទុកដដែល)")
    threading.Timer(3.0, lambda: bot.delete_message(chat_id, success_msg.message_id)).start()

# ==========================================
# មុខងារឆែកសារដោយស្វ័យប្រវត្តិ (Auto-Forward)
# ==========================================
def auto_check_new_emails():
    while True:
        for chat_id, user_data in list(user_emails.items()):
            token = user_data['token']
            seen_list = user_data['seen_messages']
            headers = {"Authorization": f"Bearer {token}"}
            
            try:
                res = requests.get(f"{API_URL}/messages", headers=headers)
                if res.status_code == 200:
                    for msg in res.json().get('hydra:member', []):
                        msg_id = msg['id']
                        if msg_id not in seen_list:
                            seen_list.append(msg_id)
                            msg_detail = requests.get(f"{API_URL}/messages/{msg_id}", headers=headers).json()
                            sender = msg_detail.get('from', {}).get('address', 'Unknown')
                            subject = msg_detail.get('subject', 'គ្មានប្រធានបទ')
                            text_content = clean_html(msg_detail.get('text', ''))[:500]
                            
                            try:
                                dt_utc = datetime.strptime(msg_detail.get('createdAt', '')[:19], "%Y-%m-%dT%H:%M:%S")
                                dt_local = dt_utc + timedelta(hours=7) 
                                time_str = f"{dt_local.strftime('%d/%m/%Y')} ម៉ោង {dt_local.strftime('%H:%M:%S')}"
                            except:
                                time_str = "មិនស្គាល់ម៉ោង"

                            code_match = re.search(r'\b\d{4,8}\b', text_content)
                            code_alert = "👇 **លេខកូដនៅសារខាងក្រោម (ចុចដើម្បី Copy)** 👇\n" if code_match else ""

                            email_text = f"🔔 **អ្នកមានសារថ្មីចូល!** 🔔\n⏰ ពេលវេលា៖ {time_str}\n👤 ពី៖ {sender}\n📝 ប្រធានបទ៖ {subject}\n{code_alert}💬 ខ្លឹមសារ៖ \n{text_content}...\n"
                            send_and_track(chat_id, email_text, parse_mode='Markdown')

                            if code_match:
                                otp = code_match.group(0)
                                send_and_track(chat_id, f"`{otp}`", parse_mode='Markdown')
            except:
                pass
        time.sleep(10) 

# ==========================================
# កូដ Web Server សម្រាប់បង្ហោះលើ Render ឱ្យដើរ 24/7
# ==========================================
def keep_alive():
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Bot is running smoothly!")
        def do_HEAD(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
    port = int(os.environ.get('PORT', 8080))
    HTTPServer(('', port), RequestHandler).serve_forever()

if __name__ == '__main__':
    bot.set_my_commands([
        BotCommand("start", "ចាប់ផ្តើម"),
        BotCommand("login", "ចូលគណនី"),
        BotCommand("check", "ឆែកសារ"),
        BotCommand("clean", "សម្អាតអេក្រង់ (Clear Screen)") 
    ])
    print("Bot កំពុងដំណើរការ...")
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=auto_check_new_emails, daemon=True).start()
    bot.polling(none_stop=True)
