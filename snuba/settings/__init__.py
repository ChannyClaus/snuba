import os
from typing import Any, Mapping, MutableMapping, Sequence, Set

from snuba.settings.validation import _validate_settings

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s %(message)s"

TESTING = False
DEBUG = True

PORT = 1218

ENABLE_DEV_FEATURES = os.environ.get("ENABLE_DEV_FEATURES", False)

DEFAULT_DATASET_NAME = "events"
DISABLED_DATASETS: Set[str] = {"metrics"}

# Clickhouse Options
CLICKHOUSE_MAX_POOL_SIZE = 25

CLUSTERS: Sequence[Mapping[str, Any]] = [
    {
        "host": os.environ.get("CLICKHOUSE_HOST", "localhost"),
        "port": int(os.environ.get("CLICKHOUSE_PORT", 9000)),
        "user": os.environ.get("CLICKHOUSE_USER", "default"),
        "password": os.environ.get("CLICKHOUSE_PASSWORD", ""),
        "database": os.environ.get("CLICKHOUSE_DATABASE", "default"),
        "http_port": int(os.environ.get("CLICKHOUSE_HTTP_PORT", 8123)),
        "storage_sets": {
            "cdc",
            "discover",
            "events",
            "events_ro",
            "metrics",
            "migrations",
            "outcomes",
            "querylog",
            "sessions",
            "transactions",
        },
        "single_node": True,
    },
]


# Dogstatsd Options
DOGSTATSD_HOST = "localhost"
DOGSTATSD_PORT = 8125
DOGSTATSD_SAMPLING_RATES = {
    "subscriptions.receive_latency": 0.1,
    "subscriptions.process_message": 0.1,
}

# Redis Options
USE_REDIS_CLUSTER = os.environ.get("USE_REDIS_CLUSTER", "0") != "0"

REDIS_CLUSTER_STARTUP_NODES = None
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")
REDIS_DB = int(os.environ.get("REDIS_DB", 1))

USE_RESULT_CACHE = True

# Query Recording Options
RECORD_QUERIES = False

# Runtime Config Options
CONFIG_MEMOIZE_TIMEOUT = 10

# Sentry Options
SENTRY_DSN = None

# Snuba Options

SNAPSHOT_LOAD_PRODUCT = "snuba"

SNAPSHOT_CONTROL_TOPIC_INIT_TIMEOUT = 30
BULK_CLICKHOUSE_BUFFER = 10000
BULK_BINARY_LOAD_CHUNK = 2 ** 22  # 4 MB

# Processor/Writer Options

BROKER_CONFIG: Mapping[str, Any] = {
    # See snuba/utils/streams/backends/kafka.py for the supported options
    "bootstrap.servers": os.environ.get("DEFAULT_BROKERS", "localhost:9092"),
}

# Mapping of default Kafka topic name to custom names
KAFKA_TOPIC_MAP: Mapping[str, str] = {}

# Mapping of default Kafka topic name to broker config
KAFKA_BROKER_CONFIG: Mapping[str, Mapping[str, Any]] = {}

DEFAULT_MAX_BATCH_SIZE = 50000
DEFAULT_MAX_BATCH_TIME_MS = 2 * 1000
DEFAULT_QUEUED_MAX_MESSAGE_KBYTES = 10000
DEFAULT_QUEUED_MIN_MESSAGES = 10000
DISCARD_OLD_EVENTS = True
CLICKHOUSE_HTTP_CHUNK_SIZE = 8192
HTTP_WRITER_BUFFER_SIZE = 1

DEFAULT_RETENTION_DAYS = 90
RETENTION_OVERRIDES: Mapping[int, int] = {}

MAX_PREWHERE_CONDITIONS = 1

STATS_IN_RESPONSE = False

PAYLOAD_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

REPLACER_MAX_BLOCK_SIZE = 512
REPLACER_MAX_MEMORY_USAGE = 10 * (1024 ** 3)  # 10GB
# TLL of Redis key that denotes whether a project had replacements
# run recently. Useful for decidig whether or not to add FINAL clause
# to queries.
REPLACER_KEY_TTL = 12 * 60 * 60
REPLACER_MAX_GROUP_IDS_TO_EXCLUDE = 256
REPLACER_IMMEDIATE_OPTIMIZE = False

TURBO_SAMPLE_RATE = 0.1

PROJECT_STACKTRACE_BLACKLIST: Set[int] = set()
PRETTY_FORMAT_EXPRESSIONS = True

TOPIC_PARTITION_COUNTS: Mapping[str, int] = {}  # (topic name, # of partitions)

ERRORS_ROLLOUT_ALL: bool = True

COLUMN_SPLIT_MIN_COLS = 6
COLUMN_SPLIT_MAX_LIMIT = 1000
COLUMN_SPLIT_MAX_RESULTS = 5000

# Migrations in skipped groups will not be run
SKIPPED_MIGRATION_GROUPS: Set[str] = {"metrics", "querylog", "spans_experimental"}

MAX_RESOLUTION_FOR_JITTER = 60

# These contexts will not be stored in the transactions table
# Example: {123: {"context1", "context2"}}
# where 123 is the project id.
TRANSACT_SKIP_CONTEXT_STORE: Mapping[int, Set[str]] = {}


def _load_settings(obj: MutableMapping[str, Any] = locals()) -> None:
    """Load settings from the path provided in the SNUBA_SETTINGS environment
    variable if provided. Users can provide a short name like `test` that will
    be expanded to `settings_test.py` in the main Snuba directory, or they can
    provide a full absolute path such as `/foo/bar/my_settings.py`."""

    import importlib
    import importlib.util
    import os

    settings = os.environ.get("SNUBA_SETTINGS")

    if settings:
        if settings.startswith("/"):
            if not settings.endswith(".py"):
                settings += ".py"

            # Code below is adapted from https://stackoverflow.com/a/41595552/90297S
            settings_spec = importlib.util.spec_from_file_location(
                "snuba.settings.custom", settings
            )
            settings_module = importlib.util.module_from_spec(settings_spec)
            assert isinstance(settings_spec.loader, importlib.abc.Loader)
            settings_spec.loader.exec_module(settings_module)
        else:
            module_format = (
                ".%s" if settings.startswith("settings_") else ".settings_%s"
            )
            settings_module = importlib.import_module(
                module_format % settings, "snuba.settings"
            )

        for attr in dir(settings_module):
            if attr.isupper():
                obj[attr] = getattr(settings_module, attr)


_load_settings()
_validate_settings(locals())
