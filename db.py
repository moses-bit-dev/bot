import psycopg2

def setup_database(self):
        """Initialize PostgreSQL database and create tables"""
        try:
            conn = psycopg2.connect(
                host=self.config['localhost'],
                database=self.config['dexbot'],
                user=self.config['dexbot_user'],
                password=self.config['Smart123']
            )
            cursor = conn.cursor()
            
            # Create tables
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tokens (
                    pair_address TEXT PRIMARY KEY,
                    chain_id TEXT,
                    base_token TEXT,
                    quote_token TEXT,
                    creator_address TEXT,
                    created_at BIGINT,
                    first_seen TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS price_history (
                    id SERIAL PRIMARY KEY,
                    pair_address TEXT REFERENCES tokens(pair_address),
                    price_usd REAL,
                    volume_24h REAL,
                    liquidity_usd REAL,
                    timestamp TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id SERIAL PRIMARY KEY,
                    pair_address TEXT REFERENCES tokens(pair_address),
                    event_type TEXT,
                    price_change REAL,
                    timestamp TIMESTAMP
                )
            ''')
            
            conn.commit()
            logging.info("PostgreSQL tables initialized")
            return conn
            
        except Exception as e:
            logging.error(f"Database setup failed: {str(e)}")
            raise