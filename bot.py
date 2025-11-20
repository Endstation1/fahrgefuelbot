import json
import schedule
import time
import openai
import requests
from datetime import datetime
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackQueryHandler, CallbackContext

# ===== Load config =====
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

TELEGRAM_TOKEN = config["TELEGRAM_TOKEN"]
ADMIN_ID = int(config["ADMIN_ID"])
CHANNEL_ID = config["CHANNEL_ID"]
OPENAI_API_KEY = config["OPENAI_API_KEY"]
GOOGLE_API_KEY = config["GOOGLE_API_KEY"]
GOOGLE_CX = config["GOOGLE_CX"]
MODEL = config["MODEL"]
DAILY_TIME = config["DAILY_TIME"]
TOPICS = config["TOPICS"]
STYLE_PROMPT = config["STYLE_PROMPT"]

openai.api_key = OPENAI_API_KEY
bot = Bot(token=TELEGRAM_TOKEN)

selected_story = {}
awaiting_photos = {}
final_text = {}

def search_in_google(query):
    url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_API_KEY}&cx={GOOGLE_CX}&q={query}"
    r = requests.get(url).json()
    results = []
    if "items" in r:
        for item in r["items"][:5]:
            results.append({
                "title": item["title"],
                "snippet": item.get("snippet", ""),
                "link": item["link"]
            })
    return results

def process_story(title, snippet, topic):
    prompt = f"""{STYLE_PROMPT}
Hashtag: {topic}.
Length: {'up to 1000 characters' if topic == '#коротко' else 'up to 1900 characters'}.
Story:
Title: {title}
Description: {snippet}"""
    resp = openai.ChatCompletion.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are an emotional automotive storyteller."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.8
    )
    return resp.choices[0].message.content

def daily_job_callback(bot_instance):
    topic = TOPICS[str(datetime.now().weekday())]
    stories = search_in_google(f"{topic} car story")
    proposals = []
    for s in stories[:3]:
        text = process_story(s["title"], s["snippet"], topic)
        proposals.append(text)
    selected_story[ADMIN_ID] = proposals
    for i, p in enumerate(proposals, start=1):
        keyboard = [[InlineKeyboardButton(f"Выбрать вариант {i}", callback_data=f"choose_{i}")]]
        bot_instance.send_message(chat_id=ADMIN_ID, text=p, reply_markup=InlineKeyboardMarkup(keyboard))

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    if query.data.startswith("choose_"):
        idx = int(query.data.split("_")[1]) - 1
        final_text[ADMIN_ID] = selected_story[ADMIN_ID][idx]
        query.edit_message_reply_markup(None)
        query.message.reply_text("Напиши правки или отправь 'Без правок'.")
    elif query.data == "publish":
        awaiting_photos[ADMIN_ID] = True
        query.message.reply_text("Отправь 5–7 фото для публикации.")
    elif query.data == "cancel":
        query.message.reply_text("Публикация отменена.")

def message_handler(update: Update, context: CallbackContext):
    text = update.message.text
    if ADMIN_ID != update.message.chat_id:
        return
    if ADMIN_ID in final_text and text and text.lower() != "без правок" and ADMIN_ID not in awaiting_photos:
        prompt = f"Перепиши текст с учётом правок: {text}. Исходный текст:\n{final_text[ADMIN_ID]}"
        resp = openai.ChatCompletion.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are an emotional automotive storyteller."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8
        )
        final_text[ADMIN_ID] = resp.choices[0].message.content
    if ADMIN_ID in final_text and ADMIN_ID not in awaiting_photos:
        keyboard = [
            [InlineKeyboardButton("📤 Опубликовать", callback_data="publish")],
            [InlineKeyboardButton("🚫 Отмена", callback_data="cancel")]
        ]
        update.message.reply_text(final_text[ADMIN_ID], reply_markup=InlineKeyboardMarkup(keyboard))
    if ADMIN_ID in awaiting_photos and update.message.photo:
        photo_file = update.message.photo[-1].get_file()
        photo_path = f"/tmp/{photo_file.file_unique_id}.jpg"
        photo_file.download(photo_path)
        if f"{ADMIN_ID}_photos" not in context.bot_data:
            context.bot_data[f"{ADMIN_ID}_photos"] = []
        context.bot_data[f"{ADMIN_ID}_photos"].append(photo_path)
        if len(context.bot_data[f"{ADMIN_ID}_photos"]) >= 5:
            media = []
            for i, p in enumerate(context.bot_data[f"{ADMIN_ID}_photos"]):
                if i == 0:
                    media.append(InputMediaPhoto(open(p, "rb"), caption=final_text[ADMIN_ID]))
                else:
                    media.append(InputMediaPhoto(open(p, "rb")))
            bot.send_media_group(chat_id=CHANNEL_ID, media=media)
            update.message.reply_text("✅ Пост опубликован!")
            awaiting_photos.pop(ADMIN_ID)
            context.bot_data.pop(f"{ADMIN_ID}_photos")

updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CallbackQueryHandler(button_handler))
dp.add_handler(MessageHandler(Filters.text | Filters.photo, message_handler))

schedule.every().day.at(DAILY_TIME).do(lambda: daily_job_callback(updater.bot))

updater.start_polling()
bot.send_message(chat_id=ADMIN_ID, text="Бот запущен ✅")
