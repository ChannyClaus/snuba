from dataclasses import replace

from snuba.clickhouse.processors import QueryProcessor
from snuba.clickhouse.query import Query
from snuba.request.request_settings import RequestSettings


class ConsistencyEnforcerProcessor(QueryProcessor):
    """
    This processor modifies the query to ensure that deduplication/merge happens when the query
    is run. This is done by setting the FINAL mode in clickhouse query.

    This should only be used for tables whose data is mutable and have less amount of data entries
    like the CDC tables.
    """

    def process_query(self, query: Query, request_settings: RequestSettings) -> None:
        query.set_from_clause(replace(query.get_from_clause(), final=True))
