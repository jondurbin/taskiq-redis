from typing import Any, List, AsyncGenerator
from redis.asyncio import Sentinel, Redis
from taskiq.abc.broker import AsyncBroker
from taskiq.message import BrokerMessage


class BaseRedisSentinelBroker(AsyncBroker):
    """Base broker that works with Redis Sentinel."""

    def __init__(
        self,
        sentinel_hosts: List[Any],
        sentinel_id: str = "taskiq",
        queue_name: str = "taskiq",
        max_connection_pool_size: int = 2**31,
        **connection_kwargs: Any,
    ) -> None:
        """
        Constructs a new broker.

        :param sentinel_hosts: list of tuples with (ip, port) of sentinel hosts.
        :param sentinel_id: name of the sentinel instance.
        :param queue_name: name for a list in redis.
        :param max_connection_pool_size: maximum number of connections in pool.
        :param connection_kwargs: additional arguments for aio-redis ConnectionPool.
        """
        super().__init__()

        self.sentinel: Sentinel[bytes] = Sentinel(
            sentinel_hosts,
            max_connections=max_connection_pool_size,
            **connection_kwargs,
        )
        self.sentinel_id = sentinel_id
        self._master = None
        self.queue_name = queue_name

    async def master(self):
        if not self._master:
            self._master = await self.sentinel.master_for(self.sentinel_id)
        return self._master

    async def shutdown(self) -> None:
        """Closes redis connection pool."""
        await self.sentinel = None  # type: ignore[attr-defined]
        await super().shutdown()


class ListQueueSentinelBroker(BaseRedisSentinelBroker):
    """Broker that works with Redis Sentinel and distributes tasks between workers."""

    async def kick(self, message: BrokerMessage) -> None:
        """
        Put a message in a list.

        This method appends a message to the list of all messages.

        :param message: message to append.
        """
        redis = await self.master()
        await redis.lpush(self.queue_name, message.message)  # type: ignore[attr-defined]

    async def listen(self) -> AsyncGenerator[bytes, None]:
        """
        Listen redis queue for new messages.

        This function listens to the queue
        and yields new messages if they have BrokerMessage type.

        :yields: broker messages.
        """
        redis_brpop_data_position = 1
        while True:
            redis = await self.master()
            value = await redis.brpop([self.queue_name])  # type: ignore[attr-defined]
            yield value[redis_brpop_data_position]
