import json
import logging
from typing import Optional, Sequence

import click
from confluent_kafka import KafkaError, Message, Producer

from snuba import settings
from snuba.datasets.storages import StorageKey
from snuba.datasets.storages.factory import CDC_STORAGES, get_cdc_storage
from snuba.environment import setup_logging, setup_sentry
from snuba.snapshots.postgres_snapshot import PostgresSnapshot
from snuba.stateful_consumer.control_protocol import SnapshotLoaded, TransactionData
from snuba.utils.streams.configuration_builder import build_kafka_producer_configuration


@click.command()
@click.option("--control-topic", help="Topic to produce messages onto.")
@click.option(
    "--bootstrap-server", multiple=True, help="Kafka bootstrap server to use.",
)
@click.option(
    "--kafka-override-config", default=None,
    help="Path to the JSON-formatted configuration file used to \
    override the connection to Kafka cluster"
)
@click.option(
    "--storage",
    "storage_name",
    type=click.Choice([storage_key.value for storage_key in CDC_STORAGES.keys()]),
    help="The CDC storage to confirm load",
)
@click.option(
    "--source",
    help="Source of the dump. Depending on the storage it may have different meaning.",
)
@click.option("--log-level", help="Logging level to use.")
def confirm_load(
    *,
    control_topic: Optional[str],
    bootstrap_server: Sequence[str],
    storage_name: str,
    source: str,
    kafka_override_config: Optional[str] = None,
    log_level: Optional[str] = None,
) -> None:
    """
    Confirms the snapshot has been loaded by sending the
    snapshot-loaded message on the control topic.
    """

    setup_logging(log_level)
    setup_sentry()

    logger = logging.getLogger("snuba.loaded-snapshot")
    logger.info(
        "Sending load completion message for storage %s, from source %s",
        storage_name,
        source,
    )

    storage_key = StorageKey(storage_name)
    storage = get_cdc_storage(storage_key)

    stream_loader = storage.get_table_writer().get_stream_loader()

    control_topic = control_topic or storage.get_default_control_topic()

    snapshot_source = PostgresSnapshot.load(
        product=settings.SNAPSHOT_LOAD_PRODUCT, path=source,
    )

    descriptor = snapshot_source.get_descriptor()

    if kafka_override_config is not None:
        with open(kafka_override_config) as kafka_config_fh:
            logger.debug("Loading the Kafka configuration override from '%s'...")
            override_params.update(json.load(kafka_config_fh))

    producer = Producer(
        build_kafka_producer_configuration(
            stream_loader.get_default_topic_spec().topic,
            bootstrap_servers=bootstrap_server,
            override_params={
                "partitioner": "consistent",
                "message.max.bytes": 50000000,  # 50MB, default is 1MB
            },
        )
    )

    msg = SnapshotLoaded(
        id=descriptor.id,
        transaction_info=TransactionData(
            xmin=descriptor.xmin, xmax=descriptor.xmax, xip_list=descriptor.xip_list,
        ),
    )
    json_string = json.dumps(msg.to_dict())

    def delivery_callback(error: KafkaError, message: Message) -> None:
        if error is not None:
            raise error
        else:
            logger.info("Message sent %r", message.value())

    producer.produce(
        control_topic, value=json_string, on_delivery=delivery_callback,
    )

    producer.flush()
