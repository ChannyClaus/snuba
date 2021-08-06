import logging
from typing import List, Mapping

from snuba.clickhouse.columns import Array, String
from snuba.datasets.entities.factory import get_entity
from snuba.datasets.entity import Entity
from snuba.query import ProcessableQuery
from snuba.query.data_source import DataSource
from snuba.query.data_source.join import JoinClause
from snuba.query.data_source.simple import Entity as QueryEntity
from snuba.query.exceptions import InvalidExpressionException
from snuba.query.expressions import Expression, FunctionCall
from snuba.query.parser.validation import ExpressionValidator
from snuba.query.validation import FunctionCallValidator, InvalidFunctionCall
from snuba.query.validation.functions import AllowedFunctionValidator
from snuba.query.validation.signature import Any, Column, SignatureValidator

logger = logging.getLogger(__name__)


default_validators: Mapping[str, FunctionCallValidator] = {
    # like and notLike need to take care of Arrays as well since
    # Arrays are exploded into strings if they are part of the arrayjoin
    # clause.
    # TODO: provide a more restrictive support for arrayjoin.
    "like": SignatureValidator([Column({Array, String}), Any()]),
    "notLike": SignatureValidator([Column({Array, String}), Any()]),
}
global_validators: List[FunctionCallValidator] = [AllowedFunctionValidator()]


class FunctionCallsValidator(ExpressionValidator):
    """
    Applies all function validators on the provided expression.
    The individual function validators are divided in two mappings:
    a default one applied to all queries and one a mapping per dataset.
    """

    def validate(self, exp: Expression, data_source: DataSource) -> None:
        if not isinstance(exp, FunctionCall):
            return

        # If the data_source is a JoinClause it will have mutiple
        # entities so we want to make sure we validate them all.
        entities: List[Entity] = []

        if isinstance(data_source, QueryEntity):
            entity = get_entity(data_source.key)
            entities.append(entity)

        elif isinstance(data_source, JoinClause):
            alias_map = data_source.get_alias_node_map()
            for _, node in alias_map.items():
                assert isinstance(node.data_source, QueryEntity)  # mypy
                entities.append(get_entity(node.data_source.key))

        elif isinstance(data_source, ProcessableQuery):
            entity = get_entity(data_source.get_from_clause().key)
            entities.append(entity)

        else:
            return

        for entity in entities:
            validators = global_validators.copy()
            entity_validator = entity.get_function_call_validators().get(
                exp.function_name
            ) or default_validators.get(exp.function_name)

            if entity_validator:
                validators.append(entity_validator)

            try:
                for validator in validators:
                    validator.validate(
                        exp.function_name, exp.parameters, entity.get_data_model()
                    )
            except InvalidFunctionCall as exception:
                raise InvalidExpressionException(
                    exp,
                    f"Illegal call to function {exp.function_name}: {str(exception)}",
                    report=False,
                ) from exception
