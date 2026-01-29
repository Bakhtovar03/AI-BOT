from aiogram.filters import BaseFilter
from aiogram.types import Message
import os
import redis.asyncio as redis

redis_host = os.getenv("REDIS_HOST", "redis")
redis_port = int(os.getenv("REDIS_PORT", 6379))

class IsAdmin(BaseFilter):
    def __init__(self,admin_list: list[int],redis_set=None):
        self.admin_list = set(admin_list)
        self.redis = redis.Redis(host=redis_host, port=redis_port)
        self.redis_set = redis_set
    async def __call__(self, message: Message) -> bool:
          if message.from_user.id in self.admin_list:
                return True
          elif self.redis_set:
              try:
                  is_admin = await self.redis.sismember(self.redis_set,message.from_user.id)
                  return is_admin
              except Exception as e:
                  print(f'Redis error: {e}')
                  return False

          return False


