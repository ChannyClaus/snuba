import logging
import json
from syslog import LOG_CRIT
from typing import Optional, Sequence

import click
from confluent_kafka import KafkaError, KafkaException

from snuba.datasets.table_storage import KafkaTopicSpec
from snuba.environment import setup_logging
from snuba.migrations.connect import check_clickhouse_connections
from snuba.migrations.runner import Runner
from snuba.utils.streams.configuration_builder import get_default_kafka_configuration
from snuba.utils.streams.topics import Topic


@click.command()
@click.option(
    "--bootstrap-server", multiple=True, help="Kafka bootstrap server to use.",
)
@click.option("--kafka/--no-kafka", default=True)
@click.option(
    "--kafka-override-config", default=None,
    help="Path to the JSON-formatted configuration file used to \
    override the connection to Kafka cluster"
)
@click.option("--migrate/--no-migrate", default=True)
@click.option("--force", is_flag=True)
@click.option("--log-level", help="Logging level to use.")
def bootstrap(
    *,
    bootstrap_server: Sequence[str],
    kafka: bool,
    migrate: bool,
    force: bool,
    kafka_override_config: Optional[str] = None,
    log_level: Optional[str] = None,
) -> None:
    """
    Warning: Not intended to be used in production yet.
    """
    if not force:
        raise click.ClickException("Must use --force to run")

    setup_logging(log_level)

    logger = logging.getLogger("snuba.bootstrap")

    import time

    if kafka:
        logger.debug("Using Kafka with %r", bootstrap_server)
        from confluent_kafka.admin import AdminClient, NewTopic

        override_params = {
            # Same as above: override socket timeout as we expect Kafka
            # to not getting ready for a while
            "socket.timeout.ms": 1000,
        }
        if kafka_override_config is not None:
            with open(kafka_override_config) as kafka_config_fh:
                logger.debug("Loading the Kafka configuration override from '%s'...")
                override_params.update(json.load(kafka_config_fh))

        if logger.getEffectiveLevel() != logging.DEBUG:
            # Override rdkafka loglevel to be critical unless we are
            # debugging as we expect failures when trying to connect
            # (Kafka may not be up yet)
            override_params["log_level"] = LOG_CRIT

        attempts = 0
        while True:
            try:
                logger.info("Attempting to connect to Kafka (attempt %d)...", attempts)
                client = AdminClient(
                    get_default_kafka_configuration(
                        bootstrap_servers=bootstrap_server,
                        override_params=override_params,
                    )
                )
                client.list_topics(timeout=1)
                break
            except KafkaException as err:
                logger.debug(
                    "Connection to Kafka failed (attempt %d)", attempts, exc_info=err
                )
                attempts += 1
                if attempts == 60:
                    raise
                time.sleep(1)

        logger.info("Connected to Kafka on attempt %d", attempts)

        topics = {}

        for topic in Topic:
            topic_spec = KafkaTopicSpec(topic)
            logger.debug("Adding topic %s to creation list", topic_spec.topic_name)
            topics[topic_spec.topic_name] = NewTopic(
                topic_spec.topic_name,
                num_partitions=topic_spec.partitions_number,
                replication_factor=topic_spec.replication_factor,
                config=topic_spec.topic_creation_config,
            )

        logger.info("Creating Kafka topics...")
        for topic, future in client.create_topics(
            list(topics.values()), operation_timeout=1
        ).items():
            try:
                future.result()
                logger.info("Topic %s created", topic)
            except KafkaException as err:
                if err.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                    logger.error("Failed to create topic %s", topic, exc_info=err)

    if migrate:
        check_clickhouse_connections()
        Runner().run_all(force=True)
