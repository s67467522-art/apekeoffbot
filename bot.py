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
import random
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

# ============= WORKING IMAGE GENERATION FUNCTIONS =============

async def generate_image_pollinations(prompt: str) -> Optional[bytes]:
    """Generate image using Pollinations.ai (Completely Free, No API Key)."""
    try:
        # Clean the prompt for URL
        clean_prompt = prompt.replace(' ', '%20').replace('&', '%26')
        
        # Pollinations.ai API - free and reliable
        url = f"https://image.pollinations.ai/prompt/{clean_prompt}"
        params = {
            "width": 512,
            "height": 512,
            "nologo": "true",
            "seed": random.randint(1, 999999)
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        logger.info(f"Generating image with Pollinations: {prompt[:50]}...")
        response = requests.get(url, params=params, headers=headers, timeout=45)
        
        if response.status_code == 200 and response.content:
            # Check if we got an image (not HTML)
            content_type = response.headers.get('content-type', '')
            if 'image' in content_type:
                logger.info("✅ Image generated with Pollinations.ai")
                return response.content
            else:
                logger.warning(f"Pollinations returned non-image content: {content_type}")
                return None
        else:
            logger.error(f"Pollinations.ai failed: {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        logger.error("Pollinations.ai timeout")
        return None
    except Exception as e:
        logger.error(f"Error in generate_image_pollinations: {e}")
        return None

async def generate_image_artificial(prompt: str) -> Optional[bytes]:
    """Generate image using Artificial API (Free)."""
    try:
        # Artificial API - another free image generation service
        url = "https://api.artificialstudio.ai/generate"
        payload = {
            "prompt": prompt,
            "width": 512,
            "height": 512,
            "steps": 20
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
        
        logger.info(f"Generating image with Artificial Studio: {prompt[:50]}...")
        response = requests.post(url, json=payload, headers=headers, timeout=45)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('image'):
                # The image is base64 encoded
                image_data = base64.b64decode(data['image'])
                logger.info("✅ Image generated with Artificial Studio")
                return image_data
        return None
    except Exception as e:
        logger.error(f"Error in generate_image_artificial: {e}")
        return None

async def generate_image_lexica(prompt: str) -> Optional[bytes]:
    """Generate image using Lexica API (Free)."""
    try:
        url = "https://lexica.art/api/infinite-prompt"
        payload = {"prompt": prompt}
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
        
        logger.info(f"Generating image with Lexica: {prompt[:50]}...")
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('images') and len(data['images']) > 0:
                image_url = data['images'][0]['url']
                # Download the actual image
                img_response = requests.get(image_url, timeout=30)
                if img_response.status_code == 200:
                    logger.info("✅ Image generated with Lexica")
                    return img_response.content
        return None
    except Exception as e:
        logger.error(f"Error in generate_image_lexica: {e}")
        return None

async def generate_image_huggingface(prompt: str) -> Optional[bytes]:
    """Generate image using Hugging Face (if token available)."""
    if not HF_TOKEN:
        return None
    
    try:
        # Try different models
        models = [
            "black-forest-labs/FLUX.1-dev",
            "runwayml/stable-diffusion-v1-5",
            "stabilityai/stable-diffusion-2-1"
        ]
        
        for model in models:
            try:
                API_URL = f"https://api-inference.huggingface.co/models/{model}"
                headers = {"Authorization": f"Bearer {HF_TOKEN}"}
                payload = {
                    "inputs": prompt,
                    "parameters": {
                        "negative_prompt": "low quality, blurry, distorted",
                        "num_inference_steps": 20,
                    }
                }
                
                response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    logger.info(f"✅ Image generated with Hugging Face: {model}")
                    return response.content
                elif response.status_code == 503:
                    # Model loading - wait and retry once
                    await asyncio.sleep(10)
                    response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
                    if response.status_code == 200:
                        logger.info(f"✅ Image generated with Hugging Face (after wait): {model}")
                        return response.content
                else:
                    logger.warning(f"Hugging Face model {model} failed: {response.status_code}")
                    continue
            except Exception as e:
                logger.warning(f"Error with Hugging Face model {model}: {e}")
                continue
        
        return None
    except Exception as e:
        logger.error(f"Error in generate_image_huggingface: {e}")
        return None

async def generate_image(prompt: str) -> Optional[bytes]:
    """Generate image using multiple services with fallback."""
    
    # Try services in order of reliability
    services = [
        ("Pollinations.ai", generate_image_pollinations),
        ("Hugging Face", generate_image_huggingface),
        ("Lexica", generate_image_lexica),
        ("Artificial Studio", generate_image_artificial)
    ]
    
    for name, service_func in services:
        try:
            logger.info(f"🔄 Trying {name}...")
            result = await service_func(prompt)
            if result:
                return result
            # Small delay between attempts
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Service {name} error: {e}")
            continue
    
    logger.error("❌ All image generation services failed")
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

🎨 **Image Generation** - Create images from text (FREE!)
🔄 **Image Conversion** - Convert between formats
🔗 **URL Shortening** - Shorten long URLs
📏 **Image Resizing** - Resize images
🗜️ **Image Compression** - Reduce file sizes

⚠️ **Note:** Image generation uses multiple free services.
If one fails, I'll automatically try another!

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
   Example: `/image a majestic lion with golden mane`
   Example: `/image a beautiful sunset over mountains`

**Image Processing (reply to image):**
🔄 `/convert <format>` - Convert format (png, jpg, webp, etc.)
📏 `/resize <width> <height>` - Resize image
🗜️ `/compress <quality>` - Compress image (1-100)

**Other Tools:**
🔗 `/shorten <url>` - Shorten URL
ℹ️ `/info` - Bot statistics
🆘 `/help` - Show this menu

**Tips for better results:**
• Be specific: "lion with golden mane in sunset"
• Add style: "photorealistic", "digital art"
• Use quality keywords: "4k", "high quality"

*I automatically try multiple image generation services!*
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /image command."""
    if not context.args:
        await update.message.reply_text(
            "🎨 **Please provide a prompt!**\n\n"
            "Example: `/image a lion with golden mane`\n"
            "Example: `/image a beautiful sunset, photorealistic`\n\n"
            "💡 **Pro Tip:** Be specific and include style keywords!",
            parse_mode='Markdown'
        )
        return
    
    prompt = ' '.join(context.args)
    status_msg = await update.message.reply_text(
        f"🎨 **Generating image...**\n\n"
        f"📝 *Prompt:* {prompt}\n"
        f"⏳ Trying multiple AI services...",
        parse_mode='Markdown'
    )
    
    try:
        # Try to generate the image
        image_data = await generate_image(prompt)
        
        if image_data:
            await status_msg.delete()
            await update.message.reply_photo(
                photo=io.BytesIO(image_data),
                caption=f"✅ **Generated:** {prompt}\n\n"
                        f"⚡ *Powered by AI*",
                parse_mode='Markdown'
            )
        else:
            await status_msg.edit_text(
                "❌ **Failed to generate image.**\n\n"
                "All AI services are currently busy or rate-limited.\n\n"
                "**What to try:**\n"
                "• Wait 1-2 minutes and try again\n"
                "• Use a simpler prompt (e.g., 'a lion')\n"
                "• Try different keywords\n\n"
                "🔄 The bot automatically retries with multiple services!"
            )
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await status_msg.edit_text(
            "❌ **Error generating image.**\n\n"
            "Please try again in a few minutes."
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
• 🎨 AI Image Generation (Multiple FREE services)
• 🔄 Image Conversion (PNG, JPG, WEBP, BMP, GIF)
• 🔗 URL Shortening (TinyURL, is.gd)
• 📏 Image Resizing
• 🗜️ Image Compression

**Image Services Used:**
• Pollinations.ai (FREE, no API key)
• Hugging Face (if token set)
• Lexica (FREE, no API key)
• Artificial Studio (FREE, no API key)

**Status:** ✅ Active and ready!
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
    logger.info("ℹ️ Multiple image generation services enabled")
    
    # Use polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
