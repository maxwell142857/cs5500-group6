import json
import os
from datetime import datetime, timedelta
from collections import deque

from database.utils import redis_client

class APIRateLimiter:
    def __init__(self, models_config, redis_client=None, backup_file="rate_limiter_backup.json"):
        self.models = models_config
        self.redis = redis_client
        self.backup_file = backup_file
        self.last_backup = datetime.now()
        self.backup_interval = timedelta(minutes=10)
        self.current_model_index = 0
        
        # Initialize a queue for model rotation to ensure we don't immediately reuse a model
        self.model_rotation_queue = deque(range(len(self.models)))
        
        # Try to restore data on startup if Redis is empty
        self.restore_from_backup()
    
    def get_current_model(self):
        """Get the current Gemini model"""
        return self.models[self.current_model_index]
    
    def check_and_increment(self, model_index=None):
        """Check rate limits with minimal Redis storage"""
        if model_index is not None:
            model = self.models[model_index]
        else:
            model = self.models[self.current_model_index]
            
        now = datetime.now()
        current_minute = now.strftime('%Y-%m-%d-%H-%M')
        current_day = now.strftime('%Y-%m-%d')
        
        minute_key = f"rate:{model['name']}:minute"
        day_key = f"rate:{model['name']}:day"
        last_minute_key = f"rate:{model['name']}:last_minute"
        last_day_key = f"rate:{model['name']}:last_day"
        
        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()
        
        # Get current counts and last timestamps
        pipe.get(minute_key)
        pipe.get(day_key)
        pipe.get(last_minute_key)
        pipe.get(last_day_key)
        minute_count_str, day_count_str, last_minute, last_day = pipe.execute()
        
        # Convert to integers (default to 0 if None)
        minute_count = int(minute_count_str) if minute_count_str else 0
        day_count = int(day_count_str) if day_count_str else 0
        
        # Reset minute counter if we're in a new minute
        if last_minute != current_minute:
            minute_count = 0
            pipe.set(last_minute_key, current_minute)
        
        # Reset day counter if we're in a new day
        if last_day != current_day:
            day_count = 0
            pipe.set(last_day_key, current_day)

        # Check limits
        if minute_count >= model['rpm_limit'] or day_count >= model['rpd_limit']:
            # Execute the pipeline to update timestamps even if we're over limit
            if last_minute != current_minute or last_day != current_day:
                pipe.execute()
            return False  # Limit exceeded
        
        # Increment counters
        pipe.incr(minute_key)
        pipe.incr(day_key)
        
        # Set expiry - 2 minutes for minute counter, 48 hours for day counter
        pipe.expire(minute_key, 120)
        pipe.expire(day_key, 172800)
        pipe.expire(last_minute_key, 120)
        pipe.expire(last_day_key, 172800)
        
        pipe.execute()
        
        # Create backup periodically
        if now - self.last_backup > self.backup_interval:
            self.create_backup()
            self.last_backup = now
            
        return True
    
    def rotate_model(self):
        """Rotate to the next available model"""
        # Try models in the rotation queue
        for _ in range(len(self.model_rotation_queue)):
            next_model_index = self.model_rotation_queue.popleft()
            self.model_rotation_queue.append(next_model_index)  # Put it at the end
            
            if self.check_and_increment(next_model_index):
                self.current_model_index = next_model_index
                print(f"Switched to model: {self.models[next_model_index]['name']}")
                return True
        
        # If all models are at their limit
        return False
    
    def create_backup(self):
        """Create a backup of the current rate limiting data with minimal storage"""
        try:
            backup_data = {
                "timestamp": datetime.now().isoformat(),
                "models": {}
            }
            
            for _, model in enumerate(self.models):
                model_name = model['name']
                
                # Get current counts
                minute_key = f"rate:{model_name}:minute"
                day_key = f"rate:{model_name}:day"
                last_minute_key = f"rate:{model_name}:last_minute"
                last_day_key = f"rate:{model_name}:last_day"
                
                minute_count = self.redis.get(minute_key)
                day_count = self.redis.get(day_key)
                last_minute = self.redis.get(last_minute_key)
                last_day = self.redis.get(last_day_key)
                
                backup_data["models"][model_name] = {
                    "minute_count": int(minute_count) if minute_count else 0,
                    "day_count": int(day_count) if day_count else 0,
                    "last_minute": last_minute if last_minute else None,
                    "last_day": last_day if last_day else None
                }
            
            # Add current model index
            backup_data["current_model_index"] = self.current_model_index
            
            # Write to file
            with open(self.backup_file, 'w') as f:
                json.dump(backup_data, f)
                
            print(f"Rate limiter backup created at {datetime.now().isoformat()}")
            
        except Exception as e:
            print(f"Error creating rate limiter backup: {e}")
    
    def restore_from_backup(self):
        """Restore rate limiting data from backup file with minimal storage"""
        try:
            # Check if Redis already has rate limiting data
            has_data = bool(self.redis.keys("rate:*"))
            
            if not has_data and os.path.exists(self.backup_file):
                with open(self.backup_file, 'r') as f:
                    backup_data = json.load(f)
                
                # Check if backup is not too old (within 1 day)
                backup_time = datetime.fromisoformat(backup_data["timestamp"])
                if datetime.now() - backup_time < timedelta(days=1):
                    pipe = self.redis.pipeline()
                    now = datetime.now()
                    current_minute = now.strftime('%Y-%m-%d-%H-%M')
                    current_day = now.strftime('%Y-%m-%d')
                    
                    # Restore for each model
                    for model_name, model_data in backup_data["models"].items():
                        # Only restore if still in same minute/day
                        if model_data["last_minute"] == current_minute:
                            pipe.set(f"rate:{model_name}:minute", model_data["minute_count"])
                            pipe.set(f"rate:{model_name}:last_minute", current_minute)
                            pipe.expire(f"rate:{model_name}:minute", 120)
                            pipe.expire(f"rate:{model_name}:last_minute", 120)
                        
                        if model_data["last_day"] == current_day:
                            pipe.set(f"rate:{model_name}:day", model_data["day_count"])
                            pipe.set(f"rate:{model_name}:last_day", current_day)
                            pipe.expire(f"rate:{model_name}:day", 172800)
                            pipe.expire(f"rate:{model_name}:last_day", 172800)
                    
                    # Set current model index
                    if "current_model_index" in backup_data:
                        self.current_model_index = backup_data["current_model_index"]
                    
                    pipe.execute()
                    print(f"Rate limiter data restored from backup created at {backup_data['timestamp']}")
                else:
                    print("Backup file too old, not restoring")
                    
        except Exception as e:
            print(f"Error restoring rate limiter from backup: {e}")