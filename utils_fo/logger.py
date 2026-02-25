import os
import logging

class Logger:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._instance._initialize_logger()
        return cls._instance
    
    def _initialize_logger(self):
        self.logger = logging.getLogger('cocobot')
        self.logger.setLevel(logging.INFO)
        
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        # Add UTF-8 encoding to file handlers
        fh = logging.FileHandler('logs/bot.log', encoding='utf-8')
        fh.setLevel(logging.INFO)
        
        error_fh = logging.FileHandler('logs/error.log', encoding='utf-8')
        error_fh.setLevel(logging.ERROR)
        
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        error_fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        self.logger.addHandler(fh)
        self.logger.addHandler(error_fh)
        self.logger.addHandler(ch)
    
    @staticmethod
    def get_logger():
        return Logger()._instance.logger

    def log_request(self, command, card_info):
        masked_card = f"{card_info[:6]}XXXXXX{card_info[-4:]}" if len(card_info) > 10 else "INVALID_CARD"
        self.logger.info(f"Request received - Command: {command} | Card: {masked_card}")
    
    def log_response(self, command, success, message):
        level = logging.INFO if success else logging.ERROR
        self.logger.log(level, f"Response sent - Command: {command} | Success: {success} | Message: {message}")
