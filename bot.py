
import requests
import psycopg2
import time
from datetime import datetime
import json
import logging
import os
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from threading import Thread
from telegram import Bot, Update
from telegram.ext import CommandHandler, Updater, Dispatcher

# Set up logging
logging.basicConfig(
    filename='dexscreener_bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class DexScreenerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DexScreener Bot")
        self.root.geometry("1000x700")
        
        # Initialize bot
        self.bot = DexScreenerBot(ui_callback=self.update_ui)
        
        # UI Elements
        self.setup_ui()
        
    def setup_ui(self):
        """Initialize all UI components"""
        # Control Frame
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(fill=tk.X)
        
        ttk.Button(control_frame, text="Start Bot", command=self.start_bot).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Stop Bot", command=self.stop_bot).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Show Stats", command=self.show_stats).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Check Tokens", command=self.check_tokens).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Config", command=self.show_config).pack(side=tk.LEFT, padx=5)
        
        # Log Display
        self.log_area = scrolledtext.ScrolledText(self.root, state='disabled', height=20)
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Stats Frame
        stats_frame = ttk.Frame(self.root)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.stats_label = ttk.Label(stats_frame, text="Tokens: 0 | Events: 0 | Last Updated: Never")
        self.stats_label.pack()
        
        # Token Table
        columns = ("Pair Address", "Chain", "Base Token", "Quote Token")
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings", height=10)
        for col in columns:
            self.tree.heading(col, text=col)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
    def update_ui(self, message):
        """Update UI with new messages"""
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.configure(state='disabled')
        self.log_area.see(tk.END)
        self.root.update()
        
    def start_bot(self):
        """Start the bot in a separate thread"""
        self.update_ui("🚀 Starting DexScreener Bot...")
        Thread(target=self.bot.run, daemon=True).start()
        
    def stop_bot(self):
        """Stop the bot"""
        self.bot.stop()
        self.update_ui("🛑 Bot stopped")
        
    def show_stats(self):
        """Display database statistics"""
        try:
            stats = self.bot.get_stats()
            self.stats_label.config(
                text=f"Tokens: {stats['token_count']} | Events: {stats['event_count']} | Last Updated: {stats['last_update']}"
            )
            self.update_ui(f"📊 Stats updated at {datetime.now()}")
        except Exception as e:
            self.update_ui(f"❌ Error getting stats: {str(e)}")
            
    def check_tokens(self):
        """Display tokens in the table"""
        try:
            self.tree.delete(*self.tree.get_children())
            tokens = self.bot.get_recent_tokens()
            for token in tokens:
                self.tree.insert("", tk.END, values=token)
            self.update_ui(f"🔍 Loaded {len(tokens)} tokens")
        except Exception as e:
            self.update_ui(f"❌ Error loading tokens: {str(e)}")
            
    def show_config(self):
        """Display current configuration"""
        config = self.bot.get_config_summary()
        messagebox.showinfo("Configuration", "\n".join(f"{k}: {v}" for k, v in config.items()))

class DexScreenerBot:
    def __init__(self, config_path='config.json', ui_callback=None):
        self.base_url = "https://api.dexscreener.com/latest/dex"
        self.rugcheck_url = "https://api.rugcheck.xyz/v1/tokens"
        self.pocket_universe_url = "https://api.pocketuniverse.app/v1/"
        self.toxi_sol_url = "https://api.toxisol.com/v1/"
        self.running = False
        self.ui_callback = ui_callback
        self.telegram_updater = None
        
        self.load_config(config_path)
        self.db_connection = self.setup_database()
        self.setup_telegram()
        
    def log(self, message):
        """Log messages to both file and UI"""
        logging.info(message)
        if self.ui_callback:
            self.ui_callback(message)

    def load_config(self, config_path):
        """Load configuration from JSON file"""
        default_config = {
            "pump_threshold": 100,
            "rug_threshold": -90,
            "min_liquidity": 1000,
            "min_volume": 5000,
            "blacklisted_coins": [],
            "blacklisted_devs": [],
            "chains": ["ethereum", "bsc", "polygon"],
            "pocket_universe_api_key": "",
            "rugcheck_api_key": "",
            "telegram_bot_token": "",
            "telegram_chat_id": "",
            "toxi_sol_api_key": "",
            "fake_volume_threshold": 5,
            "selected_tokens": [],
            "db_host": "localhost",
            "db_name": "dexbot",
            "db_user": "dexbot_user",
            "db_password": "your_password",
            "scan_interval": 300
        }
        
        if not os.path.exists(config_path):
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=4)
            self.log(f"Created default config file at {config_path}")
        
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Assign config values to instance variables
        for key, value in self.config.items():
            setattr(self, key, value)

   
    def setup_telegram(self):
        """Set up Telegram bot commands"""
        if not self.telegram_bot_token:
            self.log("⚠️ Telegram bot token not configured")
            return
            
        try:
            self.telegram_updater = Updater(token=self.telegram_bot_token, use_context=True)
            dp = self.telegram_updater.dispatcher
            
            dp.add_handler(CommandHandler("start", self.telegram_start))
            dp.add_handler(CommandHandler("stats", self.telegram_stats))
            dp.add_handler(CommandHandler("tokens", self.telegram_tokens))
            dp.add_handler(CommandHandler("config", self.telegram_config))
            
            self.telegram_updater.start_polling()
            self.log("Telegram bot started")
        except Exception as e:
            self.log(f"Telegram setup failed: {str(e)}")

    # Telegram Command Handlers
    def telegram_start(self, update: Update, context):
        update.message.reply_text("🚀 DexScreenerBot is running!\n"
                                "/stats - Show stats\n"
                                "/tokens - List tracked tokens\n"
                                "/config - Show configuration")
        
    def telegram_stats(self, update: Update, context):
        stats = self.get_stats()
        update.message.reply_text(
            f"📊 Stats:\n"
            f"Tokens: {stats['token_count']}\n"
            f"Events: {stats['event_count']}\n"
            f"Last Updated: {stats['last_update']}"
        )
        
    def telegram_tokens(self, update: Update, context):
        tokens = self.get_recent_tokens(limit=10)
        if not tokens:
            update.message.reply_text("No tokens tracked yet")
            return
            
        message = "🔍 Recent Tokens:\n" + "\n".join(
            f"{t[2]}/{t[3]} ({t[1]})" for t in tokens
        )
        update.message.reply_text(message[:4000])  # Telegram message limit
        
    def telegram_config(self, update: Update, context):
        config = self.get_config_summary()
        update.message.reply_text(
            "⚙️ Configuration:\n" + "\n".join(f"{k}: {v}" for k, v in config.items())
        )

    # Database Operations
    def save_token(self, pair_data):
        """Save new token to database"""
        try:
            cursor = self.db_connection.cursor()
            cursor.execute('''
                INSERT INTO tokens (
                    pair_address, chain_id, base_token, quote_token, 
                    creator_address, created_at, first_seen
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (pair_address) DO NOTHING
            ''', (
                pair_data['pairAddress'],
                pair_data['chainId'],
                pair_data['baseToken']['symbol'],
                pair_data['quoteToken']['symbol'],
                pair_data.get('creatorAddress', ''),
                pair_data.get('pairCreatedAt'),
                datetime.now().isoformat()
            ))
            self.db_connection.commit()
        except Exception as e:
            self.log(f"Error saving token: {str(e)}")
            self.db_connection.rollback()

    def save_price_history(self, pair_address, pair_data):
        """Save price history to database"""
        try:
            cursor = self.db_connection.cursor()
            cursor.execute('''
                INSERT INTO price_history (
                    pair_address, price_usd, volume_24h, liquidity_usd, timestamp
                )
                VALUES (%s, %s, %s, %s, %s)
            ''', (
                pair_address,
                float(pair_data['priceUsd']),
                float(pair_data['volume']['h24']),
                float(pair_data['liquidity']['usd']),
                datetime.now().isoformat()
            ))
            self.db_connection.commit()
        except Exception as e:
            self.log(f"Error saving price history: {str(e)}")
            self.db_connection.rollback()

    def record_event(self, pair_address, event_type, price_change):
        """Record significant events"""
        try:
            cursor = self.db_connection.cursor()
            cursor.execute('''
                INSERT INTO events (
                    pair_address, event_type, price_change, timestamp
                )
                VALUES (%s, %s, %s, %s)
            ''', (
                pair_address,
                event_type,
                price_change,
                datetime.now().isoformat()
            ))
            self.db_connection.commit()
            self.log(f"Recorded {event_type} event for {pair_address}")
        except Exception as e:
            self.log(f"Error recording event: {str(e)}")
            self.db_connection.rollback()

    # Data Fetching Methods
    def get_stats(self):
        """Get database statistics"""
        cursor = self.db_connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM tokens")
        token_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM events")
        event_count = cursor.fetchone()[0]
        cursor.execute("SELECT MAX(timestamp) FROM price_history")
        last_update = cursor.fetchone()[0] or "Never"
        
        return {
            "token_count": token_count,
            "event_count": event_count,
            "last_update": last_update
        }

    def get_recent_tokens(self, limit=20):
        """Get recently tracked tokens"""
        cursor = self.db_connection.cursor()
        cursor.execute('''
            SELECT pair_address, chain_id, base_token, quote_token 
            FROM tokens 
            ORDER BY first_seen DESC 
            LIMIT %s
        ''', (limit,))
        return cursor.fetchall()

    def get_config_summary(self):
        """Get important configuration values"""
        return {
            "Chains": ", ".join(self.chains),
            "Pump Threshold": f"{self.pump_threshold}%",
            "Rug Threshold": f"{self.rug_threshold}%",
            "Min Liquidity": f"${self.min_liquidity}",
            "Min Volume": f"${self.min_volume}",
            "Blacklisted Coins": len(self.blacklisted_coins),
            "Telegram Alerts": "Enabled" if self.telegram_bot_token else "Disabled"
        }

    # Core Bot Functionality
    def fetch_new_pairs(self):
        """Fetch newly created trading pairs"""
        try:
            response = requests.get(f"{self.base_url}/pairs")
            if response.status_code == 200:
                pairs = response.json().get('pairs', [])
                return [pair for pair in pairs if self.apply_filters(pair)]
            else:
                self.log(f"API error: {response.status_code}")
                return []
        except Exception as e:
            self.log(f"Error fetching pairs: {str(e)}")
            return []

    def apply_filters(self, pair_data):
        """Apply filters to pair data"""
        try:
            # Chain filter
            if pair_data['chainId'].lower() not in [c.lower() for c in self.chains]:
                return False
                
            # Blacklist filters
            base_symbol = pair_data['baseToken']['symbol']
            quote_symbol = pair_data['quoteToken']['symbol']
            creator = pair_data.get('creatorAddress', '').lower()
            
            if (base_symbol in self.blacklisted_coins or 
                quote_symbol in self.blacklisted_coins or
                creator in self.blacklisted_devs):
                return False
                
            # Liquidity and volume filters
            liquidity = float(pair_data['liquidity']['usd'])
            volume = float(pair_data['volume']['h24'])
            
            if liquidity < self.min_liquidity or volume < self.min_volume:
                return False
                
            return True
            
        except Exception as e:
            self.log(f"Filter error: {str(e)}")
            return False

    def analyze_price_change(self, pair_address):
        """Analyze price changes for pumps/rugs"""
        try:
            cursor = self.db_connection.cursor()
            cursor.execute('''
                SELECT price_usd, timestamp 
                FROM price_history 
                WHERE pair_address = %s 
                ORDER BY timestamp DESC 
                LIMIT 2
            ''', (pair_address,))
            
            prices = cursor.fetchall()
            if len(prices) < 2:
                return
                
            current_price, _ = prices[0]
            previous_price, _ = prices[1]
            
            if previous_price == 0:
                return
                
            price_change = ((current_price - previous_price) / previous_price) * 100
            
            if price_change >= self.pump_threshold:
                self.record_event(pair_address, "PUMP", price_change)
                self.log(f"🚀 Pump detected: {price_change:.2f}%")
                
            elif price_change <= self.rug_threshold:
                self.record_event(pair_address, "RUG", price_change)
                self.log(f"💣 Rug detected: {price_change:.2f}%")
                
        except Exception as e:
            self.log(f"Price analysis error: {str(e)}")

    def run(self):
        """Main bot execution loop"""
        self.running = True
        self.log("Starting DexScreener Bot...")
        
        while self.running:
            try:
                # Fetch and process new pairs
                new_pairs = self.fetch_new_pairs()
                for pair in new_pairs:
                    self.save_token(pair)
                    self.save_price_history(pair['pairAddress'], pair)
                
                # Analyze known pairs
                cursor = self.db_connection.cursor()
                cursor.execute("SELECT pair_address FROM tokens")
                for (pair_address,) in cursor.fetchall():
                    pair_data = self.fetch_pair_data(pair_address)
                    if pair_data:
                        self.save_price_history(pair_address, pair_data)
                        self.analyze_price_change(pair_address)
                
                time.sleep(self.scan_interval)
                
            except Exception as e:
                self.log(f"Bot error: {str(e)}")
                time.sleep(60)  # Wait before retrying

    def stop(self):
        """Stop the bot gracefully"""
        self.running = False
        if self.telegram_updater:
            self.telegram_updater.stop()
        if self.db_connection:
            self.db_connection.close()
        self.log("Bot stopped successfully")

if __name__ == "__main__":
    root = tk.Tk()
    app = DexScreenerApp(root)
    root.mainloop()