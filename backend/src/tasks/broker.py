import dramatiq
from dramatiq.brokers.rabbitmq import RabbitmqBroker
from src.core.configs import configs

broker = RabbitmqBroker(
    url=configs.queue.amqp_url,
)
dramatiq.set_broker(broker)
