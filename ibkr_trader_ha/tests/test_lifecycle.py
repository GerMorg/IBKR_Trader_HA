from app.execution.lifecycle import map_broker_order_state
from app.domain.states import OrderState


def test_broker_status_mapping() -> None:
    assert map_broker_order_state("Submitted") == OrderState.LIVE
    assert map_broker_order_state("PreSubmitted") == OrderState.ACKNOWLEDGED
    assert map_broker_order_state("PartialFill", "2", "1") == OrderState.PARTIALLY_FILLED
    assert map_broker_order_state("Filled", "3", "0") == OrderState.FILLED
    assert map_broker_order_state("Rejected") == OrderState.REJECTED


def test_unknown_status_never_becomes_filled() -> None:
    assert map_broker_order_state("mystery", "0", "0") == OrderState.UNKNOWN_RECONCILING
