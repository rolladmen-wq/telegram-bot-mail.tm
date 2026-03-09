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

# --- មុខងារសម្រាប់លុបកូដ HTML (ឧ. <p>, <strong>) ឱ្យអក្សរស្អាត ---
def clean_html(raw_html):
    clean_text = re.sub(r'<[^>]+>', '', raw_html)
    return clean_text.strip()

# --- មុខងារ /start ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    welcome_text = (
        "សួស្តី! ខ្ញុំជា Bot សម្រាប់ឆែកមើលសារពីគណនី mail.tm របស់អ្នក។\n\n"
        "👉 ប្រើ /login ដើម្បីចូលគណនី\n"
        "👉 ប្រើ /check ដើម្បីមើលសារដោយដៃ (Manual Check)\n\n"
        "🔔 ចំណាំ៖ ពេលអ្នក Login រួចរាល់ ខ្ញុំនឹងផ្ញើសារថ្មីៗជូនអ្នកដោយស្វ័យប្រវត្តិ (Auto-Forward) នៅពេលមានគេផ្ញើចូល!"
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

    data = {"address": email, "password": password}
    
    try:
        token_res = requests.post(f"{API_URL}/token", json=data)
        if token_res.status_code == 200:
            token = token_res.json()['token']
            user_emails[chat_id] = {
                "address": email,
                "password": password,
                "token": token,
                "seen_messages": [] 
            }
            bot.send_message(chat_id, "✅ Login ទទួលបានជោគជ័យ! ឥឡូវនេះអ្នកអាចទុក Bot ចោលបាន ខ្ញុំនឹងផ្ញើសារប្រាប់អ្នកភ្លាមៗពេលមានសារចូលថ្មី។")
            
            headers = {"Authorization": f"Bearer {token}"}
            res = requests.get(f"{API_URL}/messages", headers=headers)
            if res.status_code == 200:
                msgs = res.json().get('hydra:member', [])
                for m in msgs:
                    user_emails[chat_id]["seen_messages"].append(m['id'])
                    
        else:
             bot.send_message(chat_id, "❌ Login បរាជ័យ។ អ៊ីមែល ឬលេខសម្ងាត់មិនត្រឹមត្រូវទេ។ សូមវាយ /login ម្តងទៀត។")
    except Exception as e:
        bot.send_message(chat_id, f"❌ មានកំហុសប្រព័ន្ធ៖ {e}")

# --- មុខងារ /check (មើលសារដោយដៃ) ---
@bot.message_handler(commands=['check'])
def check_email(message):
    chat_id = message.chat.id
    if chat_id not in user_emails:
        bot.send_message(chat_id, "⚠️ អ្នកមិនទាន់បាន Login ទេ។ សូមប្រើបញ្ជា /login ជាមុនសិន។")
        return
    
    bot.send_message(chat_id, "⏳ កំពុងឆែកមើលសារ...")
    token = user_emails[chat_id]['token']
    seen_list = user_emails[chat_id]['seen_messages']
    headers = {"Authorization": f"Bearer {token}"}

    try:
        res = requests.get(f"{API_URL}/messages", headers=headers)
        messages = res.json().get('hydra:member', [])

        if not messages:
            bot.send_message(chat_id, "📭 មិនមានសារចូលទេ (Inbox ទទេ)។")
        else:
            bot.send_message(chat_id, f"📬 អ្នកមានសារសរុបចំនួន {len(messages)} នៅក្នុងប្រអប់សំបុត្រ។\n(ខាងក្រោមជាសារ ៥ ចុងក្រោយ៖)")
            
            for msg in messages[:5]: 
                msg_id = msg['id']
                if msg_id not in seen_list:
                    status = "🆕 **សារថ្មី**"
                    seen_list.append(msg_id) 
                else:
                    status = "📭 **សារចាស់**"

                msg_res = requests.get(f"{API_URL}/messages/{msg_id}", headers=headers)
                msg_detail = msg_res.json()

                sender = msg_detail.get('from', {}).get('address', 'Unknown')
                subject = msg_detail.get('subject', 'គ្មានប្រធានបទ')
                
                raw_text = msg_detail.get('text', 'មិនមានអត្ថបទ')
                text_content = clean_html(raw_text)[:500] 
                
                created_at_str = msg_detail.get('createdAt', '')
                try:
                    time_part = created_at_str[:19] 
                    dt_utc = datetime.strptime(time_part, "%Y-%m-%dT%H:%M:%S")
                    dt_local = dt_utc + timedelta(hours=7) 
                    
                    date_part = dt_local.strftime('%d/%m/%Y')
                    time_part_only = dt_local.strftime('%H:%M:%S')
                    time_str = f"{date_part} ម៉ោង {time_part_only}"
                except Exception as e:
                    print(f"Check time error: {e}")
                    time_str = "មិនស្គាល់ម៉ោង"

                email_text = f"{status}\n"
                email_text += f"⏰ ពេលវេលា៖ {time_str}\n"
                email_text += f"👤 ពី៖ {sender}\n"
                email_text += f"📝 ប្រធានបទ៖ {subject}\n"
                email_text += f"💬 ខ្លឹមសារ៖ \n{text_content}...\n"
                
                bot.send_message(chat_id, email_text, parse_mode='Markdown')

    except Exception as e:
        bot.send_message(chat_id, f"❌ មានកំហុសក្នុងការទាញយកសារ៖ {e}")

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
                    messages = res.json().get('hydra:member', [])
                    
                    for msg in messages:
                        msg_id = msg['id']
                        if msg_id not in seen_list:
                            seen_list.append(msg_id)
                            
                            msg_res = requests.get(f"{API_URL}/messages/{msg_id}", headers=headers)
                            if msg_res.status_code == 200:
                                msg_detail = msg_res.json()
                                sender = msg_detail.get('from', {}).get('address', 'Unknown')
                                subject = msg_detail.get('subject', 'គ្មានប្រធានបទ')
                                
                                raw_text = msg_detail.get('text', 'មិនមានអត្ថបទ')
                                text_content = clean_html(raw_text)[:500]
                                
                                created_at_str = msg_detail.get('createdAt', '')
                                try:
                                    time_part = created_at_str[:19] 
                                    dt_utc = datetime.strptime(time_part, "%Y-%m-%dT%H:%M:%S")
                                    dt_local = dt_utc + timedelta(hours=7) 
                                    
                                    date_part = dt_local.strftime('%d/%m/%Y')
                                    time_part_only = dt_local.strftime('%H:%M:%S')
                                    time_str = f"{date_part} ម៉ោង {time_part_only}"
                                except Exception as e:
                                    print(f"Auto-forward time error: {e}")
                                    time_str = "មិនស្គាល់ម៉ោង"

                                email_text = "🔔 **អ្នកមានសារថ្មីចូល!** 🔔\n"
                                email_text += f"⏰ ពេលវេលា៖ {time_str}\n"
                                email_text += f"👤 ពី៖ {sender}\n"
                                email_text += f"📝 ប្រធានបទ៖ {subject}\n"
                                email_text += f"💬 ខ្លឹមសារ៖ \n{text_content}...\n"
                                
                                bot.send_message(chat_id, email_text, parse_mode='Markdown')
            except Exception as e:
                print(f"មានបញ្ហាក្នុងការ Auto-check: {e}")
        
        time.sleep(10) 

# ==========================================
# កូដ Web Server បញ្ឆោត Render កុំឲ្យបិទ Bot
# ==========================================
def keep_alive():
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Bot is running smoothly on Render!")
            
        # បន្ថែមមុខងារ do_HEAD ថ្មីនៅទីនេះ ដើម្បីដោះស្រាយ Error 501
        def do_HEAD(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
    
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('', port), RequestHandler)
    server.serve_forever()

# បើកឱ្យ Bot ដំណើរការជាប់ជានិច្ច
if __name__ == '__main__':
    bot.set_my_commands([
        BotCommand("start", "ចាប់ផ្តើមប្រើប្រាស់ Bot"),
        BotCommand("login", "ចូលគណនី mail.tm របស់អ្នក"),
        BotCommand("check", "ឆែកមើលសារដោយដៃ")
    ])
    print("Bot កំពុងដំណើរការ... (បានភ្ជាប់ Menu, Auto-Forward និង Web Server រួចរាល់)")
    
    # ឲ្យ Web Server និង Auto-Forward ដើរនៅពីក្រោយ (Background Threads)
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=auto_check_new_emails, daemon=True).start()
    
    # បើកដំណើរការ Bot Telegram

    bot.polling(none_stop=True)

