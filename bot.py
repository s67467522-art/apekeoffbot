#!/usr/bin/env python3
"""
Apeke Off Bot - A multifunctional Telegram bot
Deployed on Railway with GitHub integration
"""

import os
import io
import re
import json
import logging
import asyncio
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
HF_TOKEN = os.environ.get("HF_TOKEN", "")  # Optional for image generation
PORT = int(os.environ.get("PORT", 8443))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # For Railway deployment

if not TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN environment variable is not set!")

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============= CONSTANTS =============

SUPPORTED_FORMATS = ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif', 'tiff']
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB
DEFAULT_QUALITY = 50

# Command descriptions for /help
COMMAND_HELP = {
    'start': '🚀 Start the bot and see welcome message',
    'help': '📚 Show this help menu',
    'image': '🎨 Generate an image from text prompt\nUsage: /image beautiful sunset over mountains',
    'shorten': '🔗 Shorten a long URL\nUsage: /shorten https://example.com/very/long/url',
    'convert': '🔄 Convert image to different format\nUsage: /convert png (reply to an image)',
    'resize': '📏 Resize image to specific dimensions\nUsage: /resize 800 600 (reply to an image)',
    'compress': '🗜️ Compress image with quality setting\nUsage: /compress 70 (reply to an image)',
    'info': 'ℹ️ Get bot information and statistics',
}

# ============= API FUNCTIONS =============

async def generate_image(prompt: str) -> Optional[bytes]:
    """Generate image using Hugging Face's Stable Diffusion API (free tier)."""
    if not HF_TOKEN:
        logger.warning("HF_TOKEN not set. Image generation will be disabled.")
        return None
    
    try:
        API_URL = "https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5"
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        payload = {
            "inputs": prompt,
            "parameters": {
                "negative_prompt": "low quality, blurry, distorted",
                "num_inference_steps": 25,
                "guidance_scale": 7.5,
            }
        }
        
        # First attempt
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        
        # If model is loading, wait and retry
        if response.status_code == 503:
            logger.info("Model is loading, waiting 5 seconds...")
            await asyncio.sleep(5)
            response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        
        if response.status_code == 200:
            logger.info(f"Image generated successfully for prompt: {prompt[:50]}...")
            return response.content
        else:
            logger.error(f"Image generation failed: {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error("Image generation timed out")
        return None
    except Exception as e:
        logger.error(f"Error in generate_image: {e}")
        return None

async def shorten_url(long_url: str) -> Optional[str]:
    """Shorten URL using multiple free APIs with fallback."""
    # Validate URL
    try:
        result = urlparse(long_url)
        if not all([result.scheme, result.netloc]):
            return None
    except:
        return None
    
    # Try multiple shortener services
    services = [
        lambda url: f"https://tinyurl.com/api-create.php?url={url}",
        lambda url: f"https://is.gd/create.php?format=simple&url={url}",
        lambda url: f"https://api.shrtco.de/v2/shorten?url={url}",
    ]
    
    for service in services:
        try:
            response = requests.get(service(long_url), timeout=10)
            if response.status_code == 200:
                short_url = response.text.strip()
                # Handle JSON response from shrtco
                if "shrtco" in str(response.url):
                    data = response.json()
                    if data.get('ok'):
                        short_url = data['result']['full_short_link']
                    else:
                        continue
                
                if short_url and short_url.startswith('http'):
                    logger.info(f"URL shortened: {long_url} -> {short_url}")
                    return short_url
        except Exception as e:
            logger.warning(f"Shortener service failed: {e}")
            continue
    
    logger.error(f"All URL shorteners failed for: {long_url}")
    return None

async def process_image(image_data: bytes, operation: str, **kwargs) -> Optional[bytes]:
    """Process image with various operations."""
    try:
        # Validate image size
        if len(image_data) > MAX_IMAGE_SIZE:
            logger.error(f"Image too large: {len(image_data)} bytes")
            return None
            
        # Open image
        img = Image.open(io.BytesIO(image_data))
        output = io.BytesIO()
        
        if operation == "convert":
            target_format = kwargs.get('format', 'png').upper()
            if target_format not in [f.upper() for f in SUPPORTED_FORMATS]:
                return None
            
            # Handle special cases
            if target_format == 'JPG':
                target_format = 'JPEG'
            
            # Convert RGBA to RGB for JPEG
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
            quality = max(1, min(100, quality))  # Clamp between 1-100
            
            # For JPEG, use quality setting
            if img.format == 'JPEG':
                img.save(output, format='JPEG', quality=quality, optimize=True)
            else:
                # For other formats, convert to JPEG for compression
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

Hello {user.first_name}! I'm your all-in-one utility bot. Here's what I can do:

🎨 **Image Generation** - Create images from text descriptions
🔄 **Image Conversion** - Convert between formats (PNG, JPG, WEBP, etc.)
🔗 **URL Shortening** - Shorten long URLs instantly
📏 **Image Resizing** - Resize images to any dimensions
🗜️ **Image Compression** - Reduce image file sizes

📌 **Quick Start:**
Type /help to see all commands and examples

💡 **Pro Tip:** Reply to an image with /convert, /resize, or /compress to process it!

*Bot Status: 🟢 Online*
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
📚 **Apeke Off Bot - Command Reference**

**Image Generation:**
🎨 `/image <prompt>` - Generate an AI image
   Example: `/image a serene sunset over mountains`

**Image Processing (reply to an image):**
🔄 `/convert <format>` - Convert image format
   Example: `/convert png` (supported: png, jpg, webp, bmp, gif)
📏 `/resize <width> <height>` - Resize image
   Example: `/resize 800 600`
🗜️ `/compress <quality>` - Compress image (1-100)
   Example: `/compress 70`

**Other Tools:**
🔗 `/shorten <url>` - Shorten a long URL
   Example: `/shorten https://example.com/very/long/url`
ℹ️ `/info` - Show bot statistics
🆘 `/help` - Show this help menu

**Quick Tips:**
• Reply to an image with processing commands
• Use /help for more information anytime
• Images must be under 20MB
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /image command to generate images."""
    if not context.args:
        await update.message.reply_text(
            "🎨 **Please provide a prompt!**\n\n"
            "Usage: `/image your description here`\n"
            "Example: `/image a beautiful sunset over mountains`",
            parse_mode='Markdown'
        )
        return
    
    if not HF_TOKEN:
        await update.message.reply_text(
            "❌ **Image generation is currently disabled.**\n\n"
            "The bot owner needs to set up the Hugging Face API token.",
            parse_mode='Markdown'
        )
        return
    
    prompt = ' '.join(context.args)
    status_msg = await update.message.reply_text(
        f"🎨 **Generating image...**\n\n"
        f"Prompt: *{prompt}*\n"
        f"⏳ This may take 20-30 seconds...",
        parse_mode='Markdown'
    )
    
    try:
        image_data = await generate_image(prompt)
        
        if image_data:
            await status_msg.delete()
            await update.message.reply_photo(
                photo=io.BytesIO(image_data),
                caption=f"✅ **Generated:** {prompt}\n\n"
                        f"🎨 *Powered by Stable Diffusion*",
                parse_mode='Markdown'
            )
        else:
            await status_msg.edit_text(
                "❌ **Image generation failed.**\n\n"
                "The AI service might be overloaded. Please try again later."
            )
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await status_msg.edit_text(
            "❌ **Error generating image.**\n\n"
            "An unexpected error occurred. Please try again."
        )

async def shorten_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /shorten command."""
    if not context.args:
        await update.message.reply_text(
            "🔗 **Please provide a URL to shorten!**\n\n"
            "Usage: `/shorten https://example.com/very/long/url`",
            parse_mode='Markdown'
        )
        return
    
    long_url = context.args[0]
    status_msg = await update.message.reply_text(
        f"🔗 **Shortening URL...**\n\n"
        f"Original: `{long_url}`",
        parse_mode='Markdown'
    )
    
    try:
        short_url = await shorten_url(long_url)
        
        if short_url:
            await status_msg.edit_text(
                f"✅ **URL Shortened Successfully!**\n\n"
                f"🔗 **Original:** `{long_url}`\n"
                f"📎 **Short URL:** `{short_url}`",
                parse_mode='Markdown'
            )
        else:
            await status_msg.edit_text(
                "❌ **Failed to shorten URL.**\n\n"
                "Please check the URL and try again."
            )
    except Exception as e:
        logger.error(f"URL shortening error: {e}")
        await status_msg.edit_text(
            "❌ **Error shortening URL.**\n\n"
            "Please try again later."
        )

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /convert command to convert image formats."""
    if not context.args:
        await update.message.reply_text(
            "🔄 **Please specify a format!**\n\n"
            "Usage: `/convert png` (reply to an image)\n"
            f"Supported formats: {', '.join(SUPPORTED_FORMATS)}",
            parse_mode='Markdown'
        )
        return
    
    target_format = context.args[0].lower()
    if target_format not in SUPPORTED_FORMATS:
        await update.message.reply_text(
            f"❌ **Invalid format!**\n\n"
            f"Supported formats: {', '.join(SUPPORTED_FORMATS)}",
            parse_mode='Markdown'
        )
        return
    
    # Check for reply to an image
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ **Please reply to an image!**\n\n"
            "Send the /convert command as a reply to an image message.",
            parse_mode='Markdown'
        )
        return
    
    # Check if reply message contains an image
    if not update.message.reply_to_message.photo:
        await update.message.reply_text(
            "❌ **The replied message doesn't contain an image!**\n\n"
            "Please reply to a message that has an image.",
            parse_mode='Markdown'
        )
        return
    
    status_msg = await update.message.reply_text(
        f"🔄 **Converting image to {target_format.upper()}...**",
        parse_mode='Markdown'
    )
    
    try:
        # Get image
        photo = update.message.reply_to_message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_data = await file.download_as_bytearray()
        
        # Process image
        processed = await process_image(
            image_data,
            "convert",
            format=target_format
        )
        
        if processed:
            # Determine file extension
            ext = 'jpg' if target_format == 'jpeg' else target_format
            filename = f"converted.{ext}"
            
            await status_msg.delete()
            await update.message.reply_document(
                document=io.BytesIO(processed),
                filename=filename,
                caption=f"✅ **Converted to {target_format.upper()}**\n\n"
                        f"📏 Original size: {len(image_data) // 1024}KB\n"
                        f"📏 New size: {len(processed) // 1024}KB",
                parse_mode='Markdown'
            )
        else:
            await status_msg.edit_text(
                "❌ **Failed to convert image.**\n\n"
                "Please try again with a different format."
            )
    except Exception as e:
        logger.error(f"Image conversion error: {e}")
        await status_msg.edit_text(
            "❌ **Error converting image.**\n\n"
            "Please try again later."
        )

async def resize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /resize command."""
    if len(context.args) < 2:
        await update.message.reply_text(
            "📏 **Please specify width and height!**\n\n"
            "Usage: `/resize 800 600` (reply to an image)",
            parse_mode='Markdown'
        )
        return
    
    try:
        width = int(context.args[0])
        height = int(context.args[1])
    except ValueError:
        await update.message.reply_text(
            "❌ **Invalid dimensions!**\n\n"
            "Please provide numbers for width and height.",
            parse_mode='Markdown'
        )
        return
    
    if width <= 0 or height <= 0:
        await update.message.reply_text(
            "❌ **Dimensions must be positive numbers!**",
            parse_mode='Markdown'
        )
        return
    
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text(
            "❌ **Please reply to an image!**\n\n"
            "Send the /resize command as a reply to an image.",
            parse_mode='Markdown'
        )
        return
    
    status_msg = await update.message.reply_text(
        f"📏 **Resizing image to {width}x{height}...**",
        parse_mode='Markdown'
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
                caption=f"✅ **Resized to {width}x{height}**\n\n"
                        f"📏 Original size: {len(image_data) // 1024}KB\n"
                        f"📏 New size: {len(processed) // 1024}KB",
                parse_mode='Markdown'
            )
        else:
            await status_msg.edit_text(
                "❌ **Failed to resize image.**\n\n"
                "Please try again with different dimensions."
            )
    except Exception as e:
        logger.error(f"Image resize error: {e}")
        await status_msg.edit_text(
            "❌ **Error resizing image.**\n\n"
            "Please try again later."
        )

async def compress_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /compress command."""
    quality = DEFAULT_QUALITY
    
    if context.args:
        try:
            quality = int(context.args[0])
            if quality < 1 or quality > 100:
                await update.message.reply_text(
                    f"⚠️ **Quality must be between 1 and 100.**\n\n"
                    f"Using default quality: {DEFAULT_QUALITY}%",
                    parse_mode='Markdown'
                )
                quality = DEFAULT_QUALITY
        except ValueError:
            await update.message.reply_text(
                f"⚠️ **Invalid quality value.**\n\n"
                f"Using default quality: {DEFAULT_QUALITY}%",
                parse_mode='Markdown'
            )
    
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text(
            "❌ **Please reply to an image!**\n\n"
            "Send the /compress command as a reply to an image.",
            parse_mode='Markdown'
        )
        return
    
    status_msg = await update.message.reply_text(
        f"🗜️ **Compressing image with quality {quality}%...**",
        parse_mode='Markdown'
    )
    
    try:
        photo = update.message.reply_to_message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_data = await file.download_as_bytearray()
        
        original_size = len(image_data)
        processed = await process_image(
            image_data,
            "compress",
            quality=quality
        )
        
        if processed:
            new_size = len(processed)
            compression_ratio = (1 - new_size / original_size) * 100
            
            await status_msg.delete()
            await update.message.reply_document(
                document=io.BytesIO(processed),
                filename=f"compressed_q{quality}.jpg",
                caption=f"✅ **Image Compressed**\n\n"
                        f"🗜️ Quality: {quality}%\n"
                        f"📏 Original: {original_size // 1024}KB\n"
                        f"📏 Compressed: {new_size // 1024}KB\n"
                        f"💾 Saved: {compression_ratio:.1f}%",
                parse_mode='Markdown'
            )
        else:
            await status_msg.edit_text(
                "❌ **Failed to compress image.**\n\n"
                "Please try again with different settings."
            )
    except Exception as e:
        logger.error(f"Image compression error: {e}")
        await status_msg.edit_text(
            "❌ **Error compressing image.**\n\n"
            "Please try again later."
        )

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /info command."""
    start_time = datetime.now()
    info_text = f"""
ℹ️ **Bot Information**

🤖 **Name:** Apeke Off Bot
🆔 **Username:** @apekeoffbot
📊 **Status:** 🟢 Online

**Features:**
• 🎨 AI Image Generation
• 🔄 Image Conversion
• 🔗 URL Shortening
• 📏 Image Resizing
• 🗜️ Image Compression

**About:**
This bot was created to provide free and useful tools for Telegram users. All processing is done on secure servers with your privacy in mind.

**Support:**
For issues or suggestions, please contact the bot administrator.

*Bot started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}*
"""
    await update.message.reply_text(info_text, parse_mode='Markdown')

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline keyboards."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "help":
        await help_command(update, context)
    elif query.data == "about":
        await info_command(update, context)

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages (echo for testing)."""
    if update.message.text:
        await update.message.reply_text(
            f"💬 You said: {update.message.text}\n\n"
            f"Type /help to see available commands."
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the bot."""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ **An error occurred.**\n\n"
            "Please try again later or contact support.",
            parse_mode='Markdown'
        )

# ============= MAIN APPLICATION =============

def main():
    """Start the bot application."""
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("image", image_command))
    application.add_handler(CommandHandler("shorten", shorten_command))
    application.add_handler(CommandHandler("convert", convert_command))
    application.add_handler(CommandHandler("resize", resize_command))
    application.add_handler(CommandHandler("compress", compress_command))
    application.add_handler(CommandHandler("info", info_command))
    
    # Add callback query handler for inline keyboards
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # Add message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start bot
    logger.info("🚀 Apeke Off Bot is starting...")
    
    # Determine if using webhook or polling
    if WEBHOOK_URL:
        # Production mode with webhook (Railway)
        logger.info(f"🌐 Running with webhook on port {PORT}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
            allowed_updates=Update.ALL_TYPES
        )
    else:
        # Development mode with polling
        logger.info("🔄 Running with polling (development mode)")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
