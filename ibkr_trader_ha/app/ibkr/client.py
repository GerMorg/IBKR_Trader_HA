from __future__ import annotations

from decimal import Decimal
import threading
import time
from typing import Any


class IBKRUnavailable(RuntimeError):
    pass


class IBKRClient:
    """Broker boundary. Native ibapi objects never leave this class."""

    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        account: str = "",
        base_currency: str = "EUR",
        connect_timeout: float = 20.0,
        request_timeout: float = 15.0,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.client_id = int(client_id)
        self.account = account
        self.base_currency = str(base_currency).upper()
        self.connect_timeout = float(connect_timeout)
        self.request_timeout = float(request_timeout)
        self.app: Any = None
        self.NativeContract: Any = None
        self.NativeOrder: Any = None
        self.ExecutionFilter: Any = None
        self.thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._req = 1000
        self._order_id = -1
        self._connected = threading.Event()
        self._account_rows: dict[str, dict[str, str]] = {}
        self._positions: dict[int, dict[str, Any]] = {}
        self._orders: dict[int, dict[str, Any]] = {}
        self._executions: dict[str, dict[str, Any]] = {}
        self._contracts: dict[int, list[dict[str, Any]]] = {}
        self._scans: dict[int, list[dict[str, Any]]] = {}
        self._history: dict[int, list[dict[str, Any]]] = {}
        self._market: dict[int, dict[str, Any]] = {}
        self._option_chains: dict[int, list[dict[str, Any]]] = {}
        self._states: dict[int, dict[str, Any]] = {}
        self._events: dict[tuple[str, int], threading.Event] = {}
        self._errors: list[tuple[int, int, str]] = []
        self.last_heartbeat = 0.0
        self._heartbeat_seen = threading.Event()

    def _build_app(self) -> Any:
        try:
            from ibapi.client import EClient
            from ibapi.contract import Contract as NativeContract
            from ibapi.execution import ExecutionFilter
            from ibapi.order import Order as NativeOrder
            from ibapi.wrapper import EWrapper
        except ImportError as exc:
            raise IBKRUnavailable("IBKR_API_NOT_INSTALLED") from exc
        parent = self

        class App(EWrapper, EClient):
            def __init__(self) -> None:
                EWrapper.__init__(self)
                EClient.__init__(self, self)

            def connectAck(self) -> None:
                parent._connected.set()

            def nextValidId(self, orderId: int) -> None:
                parent._order_id = max(parent._order_id, int(orderId))

            def currentTime(self, tm: int) -> None:
                parent.last_heartbeat = float(tm)
                parent._heartbeat_seen.set()

            def connectionClosed(self) -> None:
                parent._connected.clear()

            def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson: str = "") -> None:
                parent._errors.append((int(reqId), int(errorCode), str(errorString)))
                if int(errorCode) in {1100, 1300}:
                    parent._connected.clear()

            def accountSummary(self, reqId: int, account: str, tag: str, value: str, currency: str) -> None:
                if parent.account and account != parent.account:
                    return
                parent._account_rows.setdefault(str(currency).upper(), {})[tag] = value

            def accountSummaryEnd(self, reqId: int) -> None:
                parent._event("account", reqId).set()

            def position(self, account: str, contract: Any, pos: float, avgCost: float) -> None:
                if parent.account and account != parent.account:
                    return
                parent._positions[int(contract.conId)] = {
                    "account": account,
                    "con_id": int(contract.conId),
                    "symbol": str(contract.symbol),
                    "local_symbol": str(contract.localSymbol),
                    "sec_type": str(contract.secType),
                    "currency": str(contract.currency),
                    "exchange": str(contract.exchange),
                    "quantity": str(pos),
                    "average_cost": str(avgCost),
                }

            def positionEnd(self) -> None:
                for key, event in list(parent._events.items()):
                    if key[0] == "positions":
                        event.set()

            def openOrder(self, orderId: int, contract: Any, order: Any, orderState: Any) -> None:
                parent._orders[int(orderId)] = {
                    "order_id": int(orderId),
                    "con_id": int(contract.conId),
                    "symbol": str(contract.localSymbol or contract.symbol),
                    "action": str(order.action),
                    "order_type": str(order.orderType),
                    "quantity": str(order.totalQuantity),
                    "status": str(orderState.status),
                    "filled": str(getattr(orderState, "filled", 0)),
                    "remaining": str(getattr(orderState, "remaining", 0)),
                    "perm_id": int(getattr(order, "permId", 0) or 0),
                    "order_ref": str(getattr(order, "orderRef", "")),
                }
                parent._states[int(orderId)] = {
                    "status": str(orderState.status),
                    "filled": str(getattr(orderState, "filled", 0)),
                    "remaining": str(getattr(orderState, "remaining", 0)),
                    "avg_fill_price": str(getattr(orderState, "avgFillPrice", 0)),
                    "init_margin_change": str(getattr(orderState, "initMarginChange", "")),
                    "maint_margin_change": str(getattr(orderState, "maintMarginChange", "")),
                    "equity_with_loan_value": str(getattr(orderState, "equityWithLoanValue", "")),
                    "commission": str(getattr(orderState, "commission", "")),
                }

            def openOrderEnd(self) -> None:
                for key, event in list(parent._events.items()):
                    if key[0] == "orders":
                        event.set()

            def orderStatus(
                self, orderId: int, status: str, filled: float, remaining: float,
                avgFillPrice: float, permId: int, parentId: int, lastFillPrice: float,
                clientId: int, whyHeld: str, mktCapPrice: float,
            ) -> None:
                parent._states[int(orderId)] = {
                    **parent._states.get(int(orderId), {}),
                    "status": str(status),
                    "filled": str(filled),
                    "remaining": str(remaining),
                    "avg_fill_price": str(avgFillPrice),
                    "perm_id": int(permId),
                    "last_fill_price": str(lastFillPrice),
                    "why_held": str(whyHeld or ""),
                }

            def execDetails(self, reqId: int, contract: Any, execution: Any) -> None:
                parent._executions[str(execution.execId)] = {
                    "execution_id": str(execution.execId),
                    "order_id": int(execution.orderId),
                    "con_id": int(contract.conId),
                    "symbol": str(contract.localSymbol or contract.symbol),
                    "side": str(execution.side),
                    "quantity": str(execution.shares),
                    "price": str(execution.price),
                    "time": str(execution.time),
                    "exchange": str(execution.exchange),
                }

            def commissionReport(self, report: Any) -> None:
                execution_id = str(getattr(report, "execId", "") or "")
                if not execution_id:
                    return
                parent._executions.setdefault(execution_id, {})["commission"] = str(
                    getattr(report, "commission", "")
                )
                parent._executions[execution_id]["commission_currency"] = str(
                    getattr(report, "currency", "")
                )

            def execDetailsEnd(self, reqId: int) -> None:
                parent._event("executions", reqId).set()

            def contractDetails(self, reqId: int, details: Any) -> None:
                parent._contracts.setdefault(reqId, []).append(parent._contract_row(details))

            def contractDetailsEnd(self, reqId: int) -> None:
                parent._event("contracts", reqId).set()

            def scannerData(self, reqId: int, rank: int, details: Any, distance: str, benchmark: str, projection: str, legsStr: str) -> None:
                parent._scans.setdefault(reqId, []).append({
                    **parent._contract_row(details),
                    "rank": int(rank),
                    "distance": str(distance),
                    "benchmark": str(benchmark),
                    "projection": str(projection),
                    "legs": str(legsStr),
                })

            def scannerDataEnd(self, reqId: int) -> None:
                parent._event("scanner", reqId).set()

            def historicalData(self, reqId: int, bar: Any) -> None:
                parent._history.setdefault(reqId, []).append({
                    "date": str(bar.date),
                    "open": str(bar.open),
                    "high": str(bar.high),
                    "low": str(bar.low),
                    "close": str(bar.close),
                    "volume": str(bar.volume),
                    "count": int(bar.barCount),
                    "wap": str(bar.average),
                })

            def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:
                parent._event("history", reqId).set()

            def tickPrice(self, reqId: int, tickType: int, price: float, attrib: Any) -> None:
                parent._market.setdefault(reqId, {})[str(tickType)] = float(price)

            def tickSize(self, reqId: int, tickType: int, size: int) -> None:
                parent._market.setdefault(reqId, {})[str(tickType)] = float(size)

            def tickGeneric(self, reqId: int, tickType: int, value: float) -> None:
                parent._market.setdefault(reqId, {})[str(tickType)] = float(value)

            def tickString(self, reqId: int, tickType: int, value: str) -> None:
                parent._market.setdefault(reqId, {})[str(tickType)] = str(value)

            def tickOptionComputation(self, reqId: int, tickType: int, tickAttrib: int, impliedVol: float, delta: float, optPrice: float, pvDividend: float, gamma: float, vega: float, theta: float, undPrice: float, *args: Any) -> None:
                parent._market[reqId] = {
                    **parent._market.get(reqId, {}),
                    "implied_volatility": impliedVol,
                    "delta": delta,
                    "gamma": gamma,
                    "vega": vega,
                    "theta": theta,
                    "option_price": optPrice,
                    "underlying_price": undPrice,
                }

            def tickSnapshotEnd(self, reqId: int) -> None:
                parent._event("market", reqId).set()

            def securityDefinitionOptionParameter(self, reqId: int, exchange: str, underlyingConId: int, tradingClass: str, multiplier: str, expirations: set[str], strikes: set[float]) -> None:
                parent._option_chains.setdefault(reqId, []).append({
                    "exchange": exchange,
                    "underlying_con_id": int(underlyingConId),
                    "trading_class": tradingClass,
                    "multiplier": multiplier,
                    "expirations": sorted(str(x) for x in expirations),
                    "strikes": sorted(float(x) for x in strikes),
                })

            def securityDefinitionOptionParameterEnd(self, reqId: int) -> None:
                parent._event("options", reqId).set()

        parent.NativeContract = NativeContract
        parent.NativeOrder = NativeOrder
        parent.ExecutionFilter = ExecutionFilter
        return App()

    @staticmethod
    def _contract_row(details: Any) -> dict[str, Any]:
        c = details.contract
        return {
            "con_id": int(c.conId),
            "symbol": str(c.symbol),
            "local_symbol": str(c.localSymbol),
            "sec_type": str(c.secType),
            "exchange": str(c.exchange),
            "primary_exchange": str(getattr(c, "primaryExchange", "")),
            "currency": str(c.currency),
            "trading_class": str(getattr(c, "tradingClass", "")),
            "multiplier": str(getattr(c, "multiplier", "1") or "1"),
            "min_tick": str(getattr(details, "minTick", 0.01) or 0.01),
            "market_rule_ids": str(getattr(details, "marketRuleIds", "")),
            "contract_month": str(getattr(c, "lastTradeDateOrContractMonth", "")),
            "under_con_id": int(getattr(c, "underConId", 0) or 0),
            "strike": str(getattr(c, "strike", 0) or 0),
            "right": str(getattr(c, "right", "")),
            "trading_hours": str(getattr(details, "tradingHours", "")),
            "liquid_hours": str(getattr(details, "liquidHours", "")),
            "time_zone_id": str(getattr(details, "timeZoneId", "UTC") or "UTC"),
            "order_types": str(getattr(details, "orderTypes", "")),
            "long_name": str(getattr(details, "longName", "")),
            "category": str(getattr(details, "category", "")),
            "subcategory": str(getattr(details, "subcategory", "")),
            "min_size": str(getattr(details, "minSize", 0) or 0),
            "size_increment": str(getattr(details, "sizeIncrement", 0) or 0),
        }

    def _event(self, kind: str, req_id: int) -> threading.Event:
        return self._events.setdefault((kind, req_id), threading.Event())

    def _next_req(self) -> int:
        with self._lock:
            self._req += 1
            return self._req

    def _wait(self, kind: str, req_id: int) -> None:
        if not self._event(kind, req_id).wait(self.request_timeout):
            raise IBKRUnavailable(f"{kind.upper()}_TIMEOUT")

    def _require(self) -> None:
        if self.app is None or not bool(self.app.isConnected()):
            raise IBKRUnavailable("IBKR_NOT_CONNECTED")

    def connect(self) -> None:
        if self.app is not None and self.app.isConnected():
            return
        self.app = self._build_app()
        self.app.connect(self.host, self.port, self.client_id)
        self.thread = threading.Thread(target=self.app.run, name="ibkr-api", daemon=True)
        self.thread.start()
        deadline = time.monotonic() + self.connect_timeout
        while time.monotonic() < deadline:
            if self.app.isConnected() and self._order_id >= 0:
                self.last_heartbeat = time.time()
                return
            time.sleep(0.1)
        raise IBKRUnavailable("IBKR_CONNECT_FAILED")

    def heartbeat(self) -> bool:
        self._require()
        self._heartbeat_seen.clear()
        try:
            self.app.reqCurrentTime()
        except Exception as exc:
            self._errors.append((-1, 0, f"reqCurrentTime:{type(exc).__name__}"))
            return False
        if not self._heartbeat_seen.wait(self.request_timeout):
            return False
        return True

    def errors(self) -> list[tuple[int, int, str]]:
        return list(self._errors)

    def disconnect(self) -> None:
        if self.app is not None:
            try:
                self.app.disconnect()
            finally:
                self._connected.clear()

    def account_summary(self) -> dict[str, str]:
        self._require()
        req = self._next_req()
        self._account_rows.clear()
        try:
            self.app.reqAccountSummary(
                req, self.account or "All",
                "AccountType,NetLiquidation,TotalCashValue,BuyingPower,"
                "EquityWithLoanValue,GrossPositionValue,InitMarginReq,MaintMarginReq,"
                "AvailableFunds,ExcessLiquidity,Leverage,DayTradesRemaining",
            )
            self._wait("account", req)
            preferred = self._account_rows.get("BASE") or self._account_rows.get(self.base_currency)
            if preferred is None and self._account_rows:
                preferred = next(iter(self._account_rows.values()))
            return dict(preferred or {})
        finally:
            try:
                self.app.cancelAccountSummary(req)
            except Exception as exc:
                self._errors.append((req, 0, f"cancelAccountSummary:{type(exc).__name__}"))
            self._events.pop(("account", req), None)

    def positions(self) -> list[dict[str, Any]]:
        self._require()
        req = self._next_req()
        self._positions.clear()
        try:
            self.app.reqPositions()
            self._wait("positions", req)
            return list(self._positions.values())
        finally:
            try:
                self.app.cancelPositions()
            except Exception as exc:
                self._errors.append((req, 0, f"cancelPositions:{type(exc).__name__}"))
            self._events.pop(("positions", req), None)

    def open_orders(self) -> list[dict[str, Any]]:
        self._require()
        req = self._next_req()
        self._orders.clear()
        try:
            self.app.reqOpenOrders()
            self._wait("orders", req)
            return list(self._orders.values())
        finally:
            self._events.pop(("orders", req), None)

    def executions(self) -> list[dict[str, Any]]:
        self._require()
        req = self._next_req()
        try:
            self.app.reqExecutions(req, self.ExecutionFilter())
            self._wait("executions", req)
            return list(self._executions.values())
        finally:
            self._events.pop(("executions", req), None)

    def contract_details(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        self._require()
        req = self._next_req()
        self._contracts[req] = []
        try:
            self.app.reqContractDetails(req, self._make_contract(query))
            self._wait("contracts", req)
            return list(self._contracts[req])
        finally:
            self._events.pop(("contracts", req), None)
            self._contracts.pop(req, None)

    def scanner(self, instrument: str, location: str, scan_code: str, rows: int = 50) -> list[dict[str, Any]]:
        self._require()
        from ibapi.scanner import ScannerSubscription
        req = self._next_req()
        self._scans[req] = []
        subscription = ScannerSubscription()
        subscription.numberOfRows = min(50, max(1, int(rows)))
        subscription.instrument = instrument
        subscription.locationCode = location
        subscription.scanCode = scan_code
        try:
            self.app.reqScannerSubscription(req, subscription, [], [])
            self._wait("scanner", req)
            return list(self._scans[req])
        finally:
            try:
                self.app.cancelScannerSubscription(req)
            except Exception as exc:
                self._errors.append((req, 0, f"cancelScannerSubscription:{type(exc).__name__}"))
            self._events.pop(("scanner", req), None)
            self._scans.pop(req, None)

    def market_snapshot(self, query: dict[str, Any], asset_class: str = "") -> dict[str, Any]:
        self._require()
        req = self._next_req()
        self._market[req] = {}
        generic = "236,233"
        if asset_class == "ETF":
            generic += ",578"
        try:
            self.app.reqMktData(req, self._make_contract(query), generic, True, False, [])
            self._wait("market", req)
            return dict(self._market.get(req, {}))
        finally:
            try:
                self.app.cancelMktData(req)
            except Exception as exc:
                self._errors.append((req, 0, f"cancelMktData:{type(exc).__name__}"))
            self._events.pop(("market", req), None)
            self._market.pop(req, None)

    def historical_data(self, query: dict[str, Any], duration: str = "30 D", bar_size: str = "1 hour", what_to_show: str = "TRADES", use_rth: bool = True) -> list[dict[str, Any]]:
        self._require()
        req = self._next_req()
        self._history[req] = []
        security_type = str(query.get("security_type", query.get("sec_type", ""))).upper()
        what = "MIDPOINT" if security_type == "CASH" else what_to_show
        try:
            self.app.reqHistoricalData(req, self._make_contract(query), "", duration, bar_size, what, 1 if use_rth else 0, 2, False, [])
            self._wait("history", req)
            return list(self._history[req])
        finally:
            self._events.pop(("history", req), None)
            self._history.pop(req, None)

    def option_chain(self, underlying_con_id: int, symbol: str, underlying_sec_type: str = "STK") -> list[dict[str, Any]]:
        self._require()
        req = self._next_req()
        self._option_chains[req] = []
        try:
            self.app.reqSecDefOptParams(req, symbol, "", underlying_sec_type, int(underlying_con_id))
            self._wait("options", req)
            return list(self._option_chains[req])
        finally:
            self._events.pop(("options", req), None)
            self._option_chains.pop(req, None)

    def what_if(self, query: dict[str, Any], order: dict[str, Any]) -> dict[str, Any]:
        self._require()
        order_id = self._allocate_order_id()
        self._states[order_id] = {}
        native = self._make_order(order, what_if=True)
        self.app.placeOrder(order_id, self._make_contract(query), native)
        deadline = time.monotonic() + self.request_timeout
        while time.monotonic() < deadline:
            state = self._states.get(order_id, {})
            if state.get("init_margin_change") or state.get("status"):
                return dict(state)
            time.sleep(0.05)
        raise IBKRUnavailable("IBKR_WHATIF_TIMEOUT")

    def place_order(self, query: dict[str, Any], order: dict[str, Any]) -> int:
        self._require()
        order_id = self._allocate_order_id()
        self.app.placeOrder(order_id, self._make_contract(query), self._make_order(order, what_if=False))
        return order_id

    def order_status(self, broker_order_id: int) -> dict[str, Any]:
        return dict(self._states.get(int(broker_order_id), {}))

    def cancel_order(self, broker_order_id: int) -> None:
        self._require()
        self.app.cancelOrder(int(broker_order_id), "")

    def _allocate_order_id(self) -> int:
        with self._lock:
            if self._order_id <= 0:
                raise IBKRUnavailable("IBKR_ORDER_ID_NOT_READY")
            result = self._order_id
            self._order_id += 1
            return result

    def _make_contract(self, query: dict[str, Any]) -> Any:
        c = self.NativeContract()
        c.conId = int(query.get("con_id", 0) or 0)
        c.symbol = str(query.get("symbol", ""))
        c.localSymbol = str(query.get("local_symbol", ""))
        c.secType = str(query.get("security_type", query.get("sec_type", "STK")))
        c.exchange = str(query.get("exchange", "SMART"))
        c.primaryExchange = str(query.get("primary_exchange", ""))
        c.currency = str(query.get("currency", "USD"))
        c.tradingClass = str(query.get("trading_class", ""))
        c.lastTradeDateOrContractMonth = str(query.get("expiry", query.get("contract_month", "")))
        c.strike = float(query.get("strike", 0) or 0)
        c.right = str(query.get("right", ""))
        c.multiplier = str(query.get("multiplier", "") or "")
        return c

    def _make_order(self, data: dict[str, Any], what_if: bool) -> Any:
        o = self.NativeOrder()
        o.action = str(data["side"]).upper()
        o.orderType = str(data["order_type"]).upper()
        o.totalQuantity = float(Decimal(str(data["quantity"])))
        o.tif = str(data.get("tif", "DAY"))
        o.orderRef = str(data.get("order_ref", ""))[:80]
        o.transmit = not what_if
        o.whatIf = bool(what_if)
        if data.get("limit_price") is not None:
            o.lmtPrice = float(Decimal(str(data["limit_price"])))
        if data.get("stop_price") is not None:
            o.auxPrice = float(Decimal(str(data["stop_price"])))
        return o
