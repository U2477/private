import re
import sys
import unicodedata
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CommandHandler
import google.generativeai as genai
from flask import Flask
import threading

# Flask web server
app = Flask(__name__)

@app.route("/")
def health_check():
    return "The bot is working!"

def run_server():
    app.run(host="0.0.0.0", port=8080)

# Start the Flask web server in a separate thread
server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

class ArabicContentModerator:
    def __init__(self, gemini_api_key):
        # Configure Gemini
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel('gemini-pro')
        
        # Comprehensive list of Iraqi and Arabic bad words
        self.bad_words = self._compile_bad_words()

    def _compile_bad_words(self):
        """
        Comprehensive list of Iraqi and Arabic bad words
        Includes various spelling variations and transliterations
        """
        bad_words = [
            # Common Iraqi slurs/insults
            'حمار', 'كلب', 'عاهر', 'زنية', 'كواد',
            'منيوج',
            'خوات كحبة', 'كس', 'مأجور', 'عميل',
            'طيزك', 'طيز', 'عاهرة', 'زنا', 'كحبه',
            'منيوج',
            'تلوزه', 'تلوزة', 'صرمك', 'صرم',
            
            # Vulgar terms
            'عرص', 'قحبة', 'منييجه', 'شرموطة', 
            
            # Offensive regional terms
            'عير', 'ايجت', 'منيجة', 'كسم', 'كلخ',
            
            # Transliterated bad words
            'kos', 'kuss', 'khara', 'khara2', 
            'manyak', 'manak', 'sharmota',
            
            # Variations of offensive words
            'ح م ا ر', 'ك ل ب', 'ع ا ه ر'
        ]
        
        # Generate variations (with and without spaces, different spellings)
        extended_words = []
        for word in bad_words:
            # Original word
            extended_words.append(word)
            
            # Remove spaces
            extended_words.append(word.replace(' ', ''))
            
            # Add common Arabic letter substitutions
            variations = [
                word.replace('ا', 'أ'),
                word.replace('ا', 'إ'),
                word.replace('ه', 'ة')
            ]
            extended_words.extend(variations)
        
        return set(extended_words)

    def normalize_arabic_text(self, text):
        """
        Normalize Arabic text to handle various writing styles
        - Remove diacritics
        - Normalize Arabic letters
        - Remove extra spaces
        """
        # Remove diacritics
        text = ''.join(char for char in unicodedata.normalize('NFKD', text) 
                       if not unicodedata.combining(char))
        
        # Normalize Arabic letters
        text = text.replace('ى', 'ي')
        text = text.replace('ة', 'ه')
        text = text.replace('أ', 'ا')
        text = text.replace('إ', 'ا')
        
        # Remove extra spaces and convert to lowercase
        text = ' '.join(text.split()).lower()
        
        return text

    def contains_bad_words(self, text):
        """
        Check if text contains bad words
        Supports multiple detection methods
        """
        # Normalize text
        normalized_text = self.normalize_arabic_text(text)
        
        # Direct word matching
        for bad_word in self.bad_words:
            if bad_word.lower() in normalized_text:
                return True
        
        # Gemini additional check for nuanced content
        try:
            prompt = f"""
            لا تمسح الرسالة اذا لم تتعرف على معنى الكلمة لاتمسح الرسائل اذا لم تعرف معناها
            .قم بتحليل النص تحليلا سهلا بالعربية وحدد الألفاظ الجنسية فقط مثل نيج و كس 
            لا تمسح السب العادي فقط السب القوي جدا
            Text: '{text}'
            
            Provide a boolean response:
            - Respond with 'TRUE' if the text contains any inappropriate content
            - Respond with 'FALSE' if the text is completely clean
            
            Be extremely precise and consider cultural sensitivities.
            """
            
            response = self.model.generate_content(prompt)
            return 'TRUE' in response.text.upper()
        
        except Exception as e:
            print(f"Gemini moderation check failed: {e}")
            return False

class ContentModerationBot:
    def __init__(self, telegram_token, gemini_api_key):
        # Telegram bot setup
        self.telegram_token = telegram_token
        
        # Content moderator
        self.moderator = ArabicContentModerator(gemini_api_key)

    async def start_command(self, update: Update, context):
        """Handler for the /start command"""
        await update.message.reply_text(
            "مرحبا! أنا بوت الرقابة. سأساعد في الحفاظ على نظافة المحادثة وإزالة المحتوى غير اللائق."
        )

    async def help_command(self, update: Update, context):
        """Provide help information"""
        help_text = (
            "الأوامر المتاحة:\n"
            "/start - بدء تشغيل البوت\n"
            "/help - عرض رسالة المساعدة\n"
            "سأقوم تلقائيًا بمراقبة الرسائل في الدردشة."
        )
        await update.message.reply_text(help_text)

    async def moderate_message(self, update: Update, context):
        # Ignore messages from channels or without text
        if not update.message or not update.message.text:
            return

        # Get message text
        message_text = update.message.text
        chat = update.effective_chat
        bot = context.bot

        # Check for inappropriate content
        try:
            # Perform content moderation
            if self.moderator.contains_bad_words(message_text):
                try:
                    # Delete the message
                    await update.message.delete()
                    
                    # Send warning
                    warning_message = f"⚠️ تم حذف رسالة من {update.effective_user.mention_html()} بسبب محتوى غير لائق."
                    await bot.send_message(
                        chat_id=chat.id, 
                        text=warning_message,
                        parse_mode='HTML'
                    )
                except Exception as delete_error:
                    print(f"Could not delete message: {delete_error}")
        
        except Exception as moderation_error:
            print(f"Moderation check failed: {moderation_error}")

    def run(self):
        # Create the Application and pass it your bot's token
        application = Application.builder().token(self.telegram_token).build()
        
        # Add command handlers
        application.add_handler(CommandHandler('start', self.start_command))
        application.add_handler(CommandHandler('help', self.help_command))
        
        # Add message handler
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.moderate_message
        ))
        
        # Start the bot
        print("البوت قيد التشغيل...")
        application.run_polling(drop_pending_updates=True)

def get_api_keys():
    """
    Collect API keys with a simple inline input method
    """
    # Option 1: Hardcoded keys (RECOMMENDED FOR TESTING ONLY)
    TELEGRAM_BOT_TOKEN = 'xxxxxxxxxxxxxxxz'
    GOOGLE_GEMINI_API_KEY = 'AIzaSyAseXen26vnBIoaxxxxxxxxxxxxxx'

    # Validate keys
    if TELEGRAM_BOT_TOKEN == 'YOUR_TELEGRAM_BOT_TOKEN' or GOOGLE_GEMINI_API_KEY == 'YOUR_GOOGLE_GEMINI_API_KEY':
        print("❌ خطأ: يجب عليك استبدال مفاتيح API!")
        print("الخطوات للحصول على المفاتيح:")
        print("1. رمز بوت تليجرام: تحدث مع @BotFather على تليجرام")
        print("2. مفتاح Google Gemini API: زر https://makersuite.google.com/app/apikey")
        sys.exit(1)

    return TELEGRAM_BOT_TOKEN, GOOGLE_GEMINI_API_KEY

def main():
    # Get API keys
    telegram_token, gemini_api_key = get_api_keys()
    
    # Initialize and run the bot
    bot = ContentModerationBot(telegram_token, gemini_api_key)
    bot.run()

if __name__ == "__main__":
    main()
