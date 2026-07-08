#!/usr/bin/env python3
"""
Apeke Off Bot - A multifunctional Telegram bot
Deployed on Railway with GitHub integration
"""

import os
import io
import sys
import json
import logging
import asyncio
import base64
from datetime import datetime
from urllib.parse import urlparse
from typing import Optional, Tuple

# Third-party imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from PIL import Image
import requests

# ============= CONFIGURATION =============

# Environment variables
TOKEN = os.environ.get("TELEGRAM_TOKEN")
HF_TOKEN = os.environ.get("HF_TOKEN", "")

if not TOKEN:
    logging.error("❌ TELEGRAM_TOKEN environment variable is not set!")
    sys.exit(1)

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============= CONSTANTS =============

SUPPORTED_FORMATS = ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif']
MAX_IMAGE_SIZE = 20 * 1024 * 1024
DEFAULT_QUALITY = 50

# ============= IMAGE GENERATION FUNCTIONS =============

async def generate_image_huggingface(prompt: str) -> Optional[bytes]:
    """Generate image using Hugging Face's Stable Diffusion (Free)."""
    if not HF_TOKEN:
        return None
    
    try:
        # Try multiple free models
        models = [
            "runwayml/stable-diffusion-v1-5",
            "stabilityai/stable-diffusion-2-1",
            "prompthero/openjourney",
            "dreamlike-art/dreamlike-photoreal-2.0"
        ]
        
        for model in models:
            try:
                API_URL = f"https://api-inference.huggingface.co/models/{model}"
                headers = {"Authorization": f"Bearer {HF_TOKEN}"}
                payload = {
                    "inputs": prompt,
                    "parameters": {
                        "negative_prompt": "low quality, blurry, distorted, ugly",
                        "num_inference_steps": 20,
                    }
                }
                
                response = requests.post(API_URL, headers=headers, json=payload, timeout=45)
                
                if response.status_code == 200:
                    logger.info(f"Image generated with model: {model}")
                    return response.content
                elif response.status_code == 503:
                    # Model loading, wait and retry
                    await asyncio.sleep(10)
                    response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
                    if response.status_code == 200:
                        logger.info(f"Image generated with model after wait: {model}")
                        return response.content
                else:
                    logger.warning(f"Model {model} failed: {response.status_code}")
                    continue
            except Exception as e:
                logger.warning(f"Error with model {model}: {e}")
                continue
        
        return None
    except Exception as e:
        logger.error(f"Error in generate_image_huggingface: {e}")
        return None

async def generate_image_pollinations(prompt: str) -> Optional[bytes]:
    """Generate image using Pollinations.ai (Completely Free, No API Key)."""
    try:
        # Pollinations.ai is a free image generation API
        url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ', '%20')}"
        params = {
            "width": 512,
            "height": 512,
            "nologo": "true",
            "seed": "random"
        }
        
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            logger.info("Image generated with Pollinations.ai")
            return response.content
        else:
            logger.error(f"Pollinations.ai failed: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error in generate_image_pollinations: {e}")
        return None

async def generate_image_lexica(prompt: str) -> Optional[bytes]:
    """Generate image using Lexica API (Free)."""
    try:
        url = "https://lexica.art/api/infinite-prompt"
        payload = {"prompt": prompt}
        
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get("images") and len(data["images"]) > 0:
                image_url = data["images"][0]["url"]
                image_response = requests.get(image_url, timeout=30)
                if image_response.status_code == 200:
                    logger.info("Image generated with Lexica")
                    return image_response.content
        return None
    except Exception as e:
        logger.error(f"Error in generate_image_lexica: {e}")
        return None

async def generate_image(prompt: str) -> Optional[bytes]:
    """Generate image using multiple free services with fallback."""
    
    # Try Hugging Face first (if token is set)
    if HF_TOKEN:
        logger.info("Attempting image generation with Hugging Face...")
        result = await generate_image_huggingface(prompt)
        if result:
            return result
    
    # Try Pollinations.ai (No API key required)
    logger.info("Attempting image generation with Pollinations.ai...")
    result = await generate_image_pollinations(prompt)
    if result:
        return result
    
    # Try Lexica as final fallback
    logger.info("Attempting image generation with Lexica...")
    result = await generate_image_lexica(prompt)
    if result:
        return result
    
    logger.error("All image generation methods failed")
    return None

# ============= URL SHORTENER =============

async def shorten_url(long_url: str) -> Optional[str]:
    """Shorten URL using multiple free APIs."""
    try:
        result = urlparse(long_url)
        if not all([result.scheme, result.netloc]):
            return None
    except:
        return None
    
    # Try TinyURL first
    try:
        response = requests.get(
            f"https://tinyurl.com/api-create.php?url={long_url}",
            timeout=10
        )
        if response.status_code == 200:
            short_url = response.text.strip()
            if short_url and short_url.startswith('http'):
                return short_url
    except:
        pass
    
    # Fallback to is.gd
    try:
        response = requests.get(
            f"https://is.gd/create.php?format=simple&url={long_url}",
            timeout=10
        )
        if response.status_code == 200:
            short_url = response.text.strip()
            if short_url and short_url.startswith('http'):
                return short_url
    except:
        pass
    
    return None

# ============= IMAGE PROCESSING =============

async def process_image(image_data: bytes, operation: str, **kwargs) -> Optional[bytes]:
    """Process image with various operations."""
    try:
        if len(image_data) > MAX_IMAGE_SIZE:
            return None
            
        img = Image.open(io.BytesIO(image_data))
        output = io.BytesIO()
        
        if operation == "convert":
            target_format = kwargs.get('format', 'png').upper()
            if target_format not in [f.upper() for f in SUPPORTED_FORMATS]:
                return None
            
            if target_format == 'JPG':
                target_format = 'JPEG'
            
            if target_format == 'JPEG' and img.mode == 'RGBA':
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[3])
                img = rgb_img
            
            img.save(output, format=target_format, quality=95, optimize=True)
            
        elif operation == "resize":
            width = kwargs.get('width', 800)
            height = kwargs.get('height', 600)
            img = img.resize((width, height), Image.Resampling.LANCZOS)
            img.save(output, format=img.format or 'PNG', quality=95, optimize=True)
            
        elif operation == "compress":
            quality = kwargs.get('quality', DEFAULT_QUALITY)
            quality = max(1, min(100, quality))
            
            if img.format == 'JPEG':
                img.save(output, format='JPEG', quality=quality, optimize=True)
            else:
                if img.mode == 'RGBA':
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    rgb_img.paste(img, mask=img.split()[3])
                    img = rgb_img
                img.save(output, format='JPEG', quality=quality, optimize=True)
        else:
            return None
            
        output.seek(0)
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"Error in process_image: {e}")
        return None

# ============= BOT COMMAND HANDLERS =============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    welcome_text = f"""
👋 Welcome to **Apeke Off Bot**!

Hello {user.first_name}! I'm your all-in-one utility bot.

🎨 **Image Generation** - Create images from text (FREE, no API key needed!)
🔄 **Image Conversion** - Convert between formats
🔗 **URL Shortening** - Shorten long URLs
📏 **Image Resizing** - Resize images
🗜️ **Image Compression** - Reduce file sizes

⚠️ **Note:** Image generation uses free services. Quality may vary.

Type /help to see all commands!
"""
    keyboard = [
        [InlineKeyboardButton("📚 Commands", callback_data="help"),
         InlineKeyboardButton("ℹ️ About", callback_data="about")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = """
📚 **Apeke Off Bot - Commands**

**Image Generation:**
🎨 `/image <prompt>` - Generate AI image (FREE)
   Example: `/image a beautiful sunset`

**Image Processing (reply to image):**
🔄 `/convert <format>` - Convert format (png, jpg, webp, etc.)
📏 `/resize <width> <height>` - Resize image
🗜️ `/compress <quality>` - Compress image (1-100)

**Other Tools:**
🔗 `/shorten <url>` - Shorten URL
ℹ️ `/info` - Bot statistics
🆘 `/help` - Show this menu

**Tips for better image generation:**
• Be specific: "a lion with golden mane in sunset"
• Include style: "photorealistic", "digital art", "cinematic"
• Add quality keywords: "4k", "high quality", "detailed"

*Image generation is powered by free AI services*
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /image command."""
    if not context.args:
        await update.message.reply_text(
            "🎨 **Please provide a prompt!**\n\n"
            "Example: `/image a cat wearing a hat`\n"
            "Example: `/image a beautiful lion with golden mane, sunset`\n\n"
            "💡 **Tip:** Add style keywords like 'photorealistic' or 'digital art' for better results!",
            parse_mode='Markdown'
        )
        return
    
    prompt = ' '.join(context.args)
    status_msg = await update.message.reply_text(
        f"🎨 **Generating image...**\n\n"
        f"*Prompt:* {prompt}\n"
        f"⏳ This may take 15-30 seconds...\n\n"
        f"🔄 Trying multiple services...",
        parse_mode='Markdown'
    )
    
    try:
        image_data = await generate_image(prompt)
        
        if image_data:
            await status_msg.delete()
            await update.message.reply_photo(
                photo=io.BytesIO(image_data),
                caption=f"✅ **Generated:** {prompt}\n\n"
                        f"⚡ *Powered by AI (Multiple Services)*",
                parse_mode='Markdown'
            )
        else:
            await status_msg.edit_text(
                "❌ **Failed to generate image.**\n\n"
                "All image generation services are currently unavailable.\n\n"
                "**Possible reasons:**\n"
                "• Services are rate-limited (try again in 1-2 minutes)\n"
                "• Prompt might be too complex (try simpler words)\n"
                "• Free API limits reached (try again later)\n\n"
                "💡 **Try:** `/image a simple sunset` first to test."
            )
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await status_msg.edit_text(
            "❌ **Error generating image.**\n\n"
            "An unexpected error occurred.\n"
            "Please try again with a simpler prompt."
        )

async def shorten_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /shorten command."""
    if not context.args:
        await update.message.reply_text(
            "🔗 Please provide a URL!\nExample: `/shorten https://example.com/long/url`",
            parse_mode='Markdown'
        )
        return
    
    long_url = context.args[0]
    status_msg = await update.message.reply_text(
        "🔗 Shortening URL...",
        parse_mode='Markdown'
    )
    
    try:
        short_url = await shorten_url(long_url)
        
        if short_url:
            await status_msg.edit_text(
                f"✅ **Short URL:** `{short_url}`\n\nOriginal: `{long_url}`",
                parse_mode='Markdown'
            )
        else:
            await status_msg.edit_text(
                "❌ Failed to shorten URL. Please check the URL and try again."
            )
    except Exception as e:
        logger.error(f"URL shortening error: {e}")
        await status_msg.edit_text(
            "❌ Error shortening URL. Please try again."
        )

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /convert command."""
    if not context.args:
        await update.message.reply_text(
            f"🔄 Please specify a format!\nSupported: {', '.join(SUPPORTED_FORMATS)}"
        )
        return
    
    target_format = context.args[0].lower()
    if target_format not in SUPPORTED_FORMATS:
        await update.message.reply_text(
            f"❌ Invalid format!\nSupported: {', '.join(SUPPORTED_FORMATS)}"
        )
        return
    
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text(
            "❌ Please reply to an image with this command!"
        )
        return
    
    status_msg = await update.message.reply_text(
        f"🔄 Converting to {target_format.upper()}..."
    )
    
    try:
        photo = update.message.reply_to_message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_data = await file.download_as_bytearray()
        
        processed = await process_image(
            image_data,
            "convert",
            format=target_format
        )
        
        if processed:
            ext = 'jpg' if target_format == 'jpeg' else target_format
            await status_msg.delete()
            await update.message.reply_document(
                document=io.BytesIO(processed),
                filename=f"converted.{ext}",
                caption=f"✅ Converted to {target_format.upper()}"
            )
        else:
            await status_msg.edit_text("❌ Failed to convert image.")
    except Exception as e:
        logger.error(f"Image conversion error: {e}")
        await status_msg.edit_text("❌ Error converting image.")

async def resize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /resize command."""
    if len(context.args) < 2:
        await update.message.reply_text(
            "📏 Please provide width and height!\nExample: `/resize 800 600`",
            parse_mode='Markdown'
        )
        return
    
    try:
        width = int(context.args[0])
        height = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid dimensions!")
        return
    
    if width <= 0 or height <= 0:
        await update.message.reply_text("❌ Dimensions must be positive!")
        return
    
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text("❌ Please reply to an image!")
        return
    
    status_msg = await update.message.reply_text(
        f"📏 Resizing to {width}x{height}..."
    )
    
    try:
        photo = update.message.reply_to_message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_data = await file.download_as_bytearray()
        
        processed = await process_image(
            image_data,
            "resize",
            width=width,
            height=height
        )
        
        if processed:
            await status_msg.delete()
            await update.message.reply_document(
                document=io.BytesIO(processed),
                filename=f"resized_{width}x{height}.jpg",
                caption=f"✅ Resized to {width}x{height}"
            )
        else:
            await status_msg.edit_text("❌ Failed to resize image.")
    except Exception as e:
        logger.error(f"Image resize error: {e}")
        await status_msg.edit_text("❌ Error resizing image.")

async def compress_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /compress command."""
    quality = DEFAULT_QUALITY
    
    if context.args:
        try:
            quality = int(context.args[0])
            if quality < 1 or quality > 100:
                quality = DEFAULT_QUALITY
        except ValueError:
            pass
    
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text("❌ Please reply to an image!")
        return
    
    status_msg = await update.message.reply_text(
        f"🗜️ Compressing with quality {quality}%..."
    )
    
    try:
        photo = update.message.reply_to_message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_data = await file.download_as_bytearray()
        
        processed = await process_image(
            image_data,
            "compress",
            quality=quality
        )
        
        if processed:
            await status_msg.delete()
            await update.message.reply_document(
                document=io.BytesIO(processed),
                filename=f"compressed_q{quality}.jpg",
                caption=f"✅ Compressed (Quality: {quality}%)"
            )
        else:
            await status_msg.edit_text("❌ Failed to compress image.")
    except Exception as e:
        logger.error(f"Image compression error: {e}")
        await status_msg.edit_text("❌ Error compressing image.")

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /info command."""
    info_text = """
ℹ️ **Apeke Off Bot**

🤖 **Name:** Apeke Off Bot
🆔 **Username:** @apekeoffbot
📊 **Status:** 🟢 Online

**Features:**
• 🎨 AI Image Generation (FREE - Multiple Services)
• 🔄 Image Conversion (PNG, JPG, WEBP, BMP, GIF)
• 🔗 URL Shortening (TinyURL, is.gd)
• 📏 Image Resizing
• 🗜️ Image Compression

**Image Generation Sources:**
1. Hugging Face (if token set)
2. Pollinations.ai (FREE, no API key)
3. Lexica AI (FREE, no API key)

**About:**
Free and useful tools for Telegram users.
All image generation is provided by free AI services.

*Bot is active and ready to help!*
"""
    await update.message.reply_text(info_text, parse_mode='Markdown')

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "help":
        await help_command(update, context)
    elif query.data == "about":
        await info_command(update, context)

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages."""
    if update.message.text:
        await update.message.reply_text(
            f"💬 You said: {update.message.text}\n\nType /help for commands."
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Update {update} caused error {context.error}")

# ============= MAIN APPLICATION =============

def main():
    """Start the bot application."""
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("image", image_command))
    application.add_handler(CommandHandler("shorten", shorten_command))
    application.add_handler(CommandHandler("convert", convert_command))
    application.add_handler(CommandHandler("resize", resize_command))
    application.add_handler(CommandHandler("compress", compress_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    application.add_error_handler(error_handler)
    
    logger.info("🚀 Apeke Off Bot is starting...")
    logger.info("🔄 Running with long polling (Railway compatible)")
    logger.info("ℹ️ Image Generation: Multiple free services enabled")
    
    # Use polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
