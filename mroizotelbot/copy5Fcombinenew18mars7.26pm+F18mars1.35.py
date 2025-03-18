"""
Telegram Bot with Reddit Integration, AI Chat, Voice/Text Conversion, and Translation.

Features:
- Reddit posting and commenting
- AI Chat (DeepSeek and Mistral)
- Voice-to-text conversion (Google and OpenRouter)
- Text-to-speech conversion
- Text translation
- Multi-language support
"""
import os
import asyncio
import logging
import praw
import time
import aiohttp
import schedule
from dotenv import load_dotenv
import nest_asyncio
from gtts import gTTS
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import speech_recognition as sr
from googletrans import Translator, LANGUAGES
from io import BytesIO
from typing import Optional
import argostranslate.package
import argostranslate.translate

# region Initial Setup
nest_asyncio.apply()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
load_dotenv()

# Environment Configuration
ENV_VARS = {
    "TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
    "REDDIT_CLIENT_ID": os.getenv("REDDIT_CLIENT_ID"),
    "REDDIT_CLIENT_SECRET": os.getenv("REDDIT_CLIENT_SECRET"),
    "REDDIT_USERNAME": os.getenv("REDDIT_USERNAME"),
    "REDDIT_PASSWORD": os.getenv("REDDIT_PASSWORD"),
    "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
    "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY")
}

for var_name, var_value in ENV_VARS.items():
    if not var_value:
        raise ValueError(f"Missing environment variable: {var_name}")

# Reddit Client Setup
reddit = praw.Reddit(
    client_id=ENV_VARS["REDDIT_CLIENT_ID"],
    client_secret=ENV_VARS["REDDIT_CLIENT_SECRET"],
    username=ENV_VARS["REDDIT_USERNAME"],
    password=ENV_VARS["REDDIT_PASSWORD"],
    user_agent="telegram_reddit_bot"
)

# Global Constants
COMMENT_INTERVAL = 1200  # 20 minutes in seconds
timestamp_last_comment = 0
# endregion

# region Core Bot Functions
async def start(update: Update) -> None:
    """
    Initialize bot interaction.
    
    Sends a welcome message to the user when they start the bot.
    """
    await update.message.reply_text("🤖 Welcome! Use /commands for features")
COMMAND_DESCRIPTIONS = [
    "/start - Initialize bot",
    "/post [sub] [title] [content] - Reddit post",
    "/comment [sub] - Comment on latest post",
    "/auto_comment [sub] - Auto-comment every 20min",
    "/voice - Speech-to-text (Google)",
    "/voice_openrouter - Speech-to-text (AI)",
    "/text_to_voice [lang] [text] - Generate audio",
    "/deepseek [query] - DeepSeek AI chat",
    "/chat [query] - Mistral AI chat",
    "/translate [src] [dest] [text] - Translate text",
    "/languages - Show language codes",
    "/commands - Display this panel",
    "🔗 [Sticker](https://t.me/addstickers/Flatericamsh)",
    "📸 [Instagram](https://www.instagram.com/am_.shi)",
    "🔗 [LinkedIn](https://www.linkedin.com/in/amir-shirkhodaee)",
    "🔗 [GitHub](https://github.com/Amsh23)",
    "🔗 [Portfolio](https://amsh23.github.io/my-portfolio/)",
    "🔗 [Telegram Channel](https://t.me/mafolieee)",
    "✉️ ProtonMail: mrhflateric@proton.me"
]

async def command_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display all available commands"""
    await update.message.reply_text("\n".join(COMMAND_DESCRIPTIONS), parse_mode="Markdown")
# endregion

# region Reddit Integration
async def reddit_post_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /post command for Reddit submissions"""
    args = context.args
    subreddit_name = args[0]
    try:
        subreddit = reddit.subreddit(subreddit_name)
        # Check if subreddit exists by attempting to fetch its details
        subreddit.id
        submission = subreddit.submit(args[1], selftext=" ".join(args[2:]))
        await update.message.reply_text(f"✅ Posted: {submission.url}")
    except praw.exceptions.PRAWException as e:
        await update.message.reply_text(f"❌ Subreddit error: {str(e)}")
    except Exception as e:
        await update.message.reply_text(f"❌ Post failed: {str(e)}")
        "Authorization": f"Bearer {ENV_VARS['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [
            {"role": "system", "content": "Generate relevant Reddit comment"},
            {"role": "user", "content": f"Post: {title}\n{content}"}
        ]
    }
    
        try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://openrouter.ai/api/v1/chat/completions", 
                                  headers=headers, json=payload) as response:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://openrouter.ai/api/v1/chat/completions", 
                                      headers=headers, json=payload) as response:
                    try:
                        post = next(reddit.subreddit(subreddit).new(limit=1))
                        if comment := await generate_comment(post.title, post.selftext):
                            post.reply(comment)
                            logging.info(f"💬 Commented on {post.id}")
                    except StopIteration:
                        logging.info(f"No new posts in r/{subreddit}")
            return None
        try:
            post = next(reddit.subreddit(subreddit).new(limit=1))
            if comment := await generate_comment(post.title, post.selftext):
                post.reply(comment)
                logging.info(f"💬 Commented on {post.id}")
        except Exception as e:
            logging.error(f"Auto-comment error: {str(e)}")
        await asyncio.sleep(COMMENT_INTERVAL)

async def start_auto_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enable automatic commenting"""
    if not context.args:
        await update.message.reply_text("❌ Format: /auto_comment subreddit")
        return
    
    subreddit = context.args[0]
    asyncio.create_task(auto_comment_task(subreddit))
    await update.message.reply_text(f"🔄 Auto-commenting started in r/{subreddit}")
# endregion

# region AI Services
async def deepseek_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle DeepSeek AI requests"""
    if not context.args:
        await update.message.reply_text("❌ Ask: /deepseek your_question")
        return
    
    headers = {"Authorization": f"Bearer {ENV_VARS['DEEPSEEK_API_KEY']}"}
    payload = {"question": " ".join(context.args)}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.deepseek.com/v1/ask", 
                                  headers=headers, json=payload) as response:
                data = await response.json()
                await update.message.reply_text(data.get("answer", "⚠️ No response"))
    except Exception as e:
        await update.message.reply_text(f"❌ API Error: {str(e)}")

async def mistral_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Mistral AI chat requests"""
    if not context.args:
        await update.message.reply_text("❌ Ask: /chat your_question")
        return
    
    headers = {
        "Authorization": f"Bearer {ENV_VARS['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [{"role": "user", "content": " ".join(context.args)}]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://openrouter.ai/api/v1/chat/completions", 
                                  headers=headers, json=payload) as response:
                data = await response.json()
                reply = data['choices'][0]['message']['content']
                await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"❌ Chat error: {str(e)}")
# endregion

# region Conversion Services
async def google_voice_to_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert voice messages using Google's API"""
    if not update.message.voice:
        await update.message.reply_text("❌ Send a voice message")
        return
    
    try:
        voice_file = await update.message.voice.get_file()
        recognizer = sr.Recognizer()
        
        with BytesIO() as buffer:
            await voice_file.download(out=buffer)
            buffer.seek(0)
            
            with sr.AudioFile(buffer) as source:
                audio = await context.bot.run_async(recognizer.record, source)
                text = recognizer.recognize_google(audio)
                await update.message.reply_text(f"🔊 Transcription: {text}")
    except Exception as e:
        await update.message.reply_text(f"❌ Conversion error: {str(e)}")

async def openrouter_voice_to_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert voice using OpenRouter's API"""
    if not update.message.voice:
        await update.message.reply_text("❌ Send a voice message")
        return
    
    try:
        voice_file = await update.message.voice.get_file()
        headers = {"Authorization": f"Bearer {ENV_VARS['OPENROUTER_API_KEY']}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/voice-to-text",
                headers=headers,
                data={"file": await voice_file.download_as_bytearray()}
            ) as response:
                data = await response.json()
                await update.message.reply_text(f"🤖 Transcription: {data.get('text', '⚠️ Error')}")
    except Exception as e:
        await update.message.reply_text(f"❌ AI processing failed: {str(e)}")

async def text_to_speech(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert text to audio using gTTS"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ Format: /text_to_voice lang text")
        return
    
    lang, text = context.args[0], " ".join(context.args[1:])
    try:
        tts = gTTS(text, lang=lang)
        with BytesIO() as audio_buffer:
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)
            await update.message.reply_voice(voice=audio_buffer)
    except Exception as e:
        await update.message.reply_text(f"❌ Synthesis error: {str(e)}")
# endregion

# region Translation Services
async def install_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Install specific language package for Argos Translate"""
    if len(context.args) < 2:
        await update.message.reply_text("❌ Format: /install_language src dest")
        return
    
    src, dest = context.args[0], context.args[1]
    
    try:
        argostranslate.package.update_package_index()
        available_packages = argostranslate.package.get_available_packages()
        package_to_install = next((pkg for pkg in available_packages if pkg.from_code == src and pkg.to_code == dest), None)
        
        if package_to_install:
            argostranslate.package.install_from_path(package_to_install.download())
            await update.message.reply_text(f"✅ Language package for {src} to {dest} installed successfully.")
        else:
            await update.message.reply_text(f"❌ No language package found for {src} to {dest}.")
    except Exception as e:
        await update.message.reply_text(f"❌ Installation failed: {str(e)}")

async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text translation requests using Argos Translate"""
    if len(context.args) < 3:
        await update.message.reply_text("❌ Format: /translate src dest text")
        return
    try:
        # Check if the specific language package is already installed
        installed_languages = argostranslate.translate.get_installed_languages()
        from_lang = next((lang for lang in installed_languages if lang.code == src), None)
        to_lang = next((lang for lang in installed_languages if lang.code == dest), None)
        
        if not from_lang or not to_lang:
            await install_language(update, context)
            installed_languages = argostranslate.translate.get_installed_languages()
            from_lang = next((lang for lang in installed_languages if lang.code == src), None)
            to_lang = next((lang for lang in installed_languages if lang.code == dest), None)
        
        if from_lang and to_lang:
            translation = from_lang.get_translation(to_lang)
            translated_text = translation.translate(text)
            await update.message.reply_text(f"🌍 {translated_text}")
        else:
            await update.message.reply_text("❌ Translation failed: Language not installed")
    except Exception as e:
        await update.message.reply_text(f"❌ Translation failed: {str(e)}")
    languages = "\n".join([f"{code}: {name}" for code, name in LANGUAGES.items()])
    await update.message.reply_text(f"🗣 Supported Languages:\n{languages}")
# endregion

# region Application Setup
async def configure_bot_commands(application: Application) -> None:
    """Set up bot command menu"""
    commands = [
        BotCommand("start", "Initialize bot"),
        BotCommand("commands", "Show all features"),
        BotCommand("post", "Create Reddit post"),
        BotCommand("comment", "Comment on post"),
        BotCommand("auto_comment", "Auto-comment system"),
        BotCommand("voice", "Voice-to-text (Google)"),
        BotCommand("voice_openrouter", "Voice-to-text (AI)"),
        BotCommand("text_to_voice", "Generate speech"),
        BotCommand("deepseek", "DeepSeek AI chat"),
        BotCommand("chat", "Mistral AI chat"),
        BotCommand("translate", "Translate text"),
        BotCommand("languages", "Language codes"),
        BotCommand("install_language", "Install language package")
    ]
    """Main application entry point: sets up the bot, adds handlers, and starts polling"""
    await application.bot.set_my_commands(commands)

async def main() -> None:
    try:
        application = Application.builder().token(ENV_VARS["TOKEN"]).build()
    except Exception as e:
        logging.error(f"Failed to initialize the bot: {str(e)}")
        return
    handlers = [
        CommandHandler("start", start),
        CommandHandler("commands", command_panel),
        CommandHandler("post", reddit_post_command),
        CommandHandler("auto_comment", start_auto_comment),
        CommandHandler("deepseek", deepseek_query),
        CommandHandler("voice", google_voice_to_text),
        CommandHandler("voice_openrouter", openrouter_voice_to_text),
        CommandHandler("text_to_voice", text_to_speech),
        CommandHandler("chat", mistral_chat),
        CommandHandler("translate", translate_text),
        CommandHandler("languages", show_language_codes),
        CommandHandler("install_language", install_language)
    ]
    handlers = [
    handlers = [
        CommandHandler("start", start),
        CommandHandler("commands", command_panel),
        CommandHandler("post", reddit_post_command),
        CommandHandler("auto_comment", start_auto_comment),
        CommandHandler("deepseek", deepseek_query),
        CommandHandler("voice", google_voice_to_text),
        CommandHandler("voice_openrouter", openrouter_voice_to_text),
        CommandHandler("text_to_voice", text_to_speech),
        CommandHandler("chat", mistral_chat),
        CommandHandler("translate", translate_text),
        CommandHandler("languages", show_language_codes),
        CommandHandler("install_language", install_language)
    ]
    
    for handler in handlers:
        application.add_handler(handler)

    await configure_bot_commands(application)
    logging.info("Bot is operational")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
# endregion