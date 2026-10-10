from pydantic import BaseModel


class ConnectionProtocol(BaseModel):
    name: str
    is_asynchronous: bool


SYNCHRONOUS_REST_HTTP = ConnectionProtocol(name="sync_rest_http", is_asynchronous=False)
SYNCHRONOUS_GRPC = ConnectionProtocol(name="sync_grpc", is_asynchronous=False)
SYNCHRONOUS_DATABASE_TCP = ConnectionProtocol(
    name="sync_database_tcp", is_asynchronous=False
)
ASYNCHRONOUS_MESSAGE_QUEUE = ConnectionProtocol(
    name="async_message_queue", is_asynchronous=True
)
