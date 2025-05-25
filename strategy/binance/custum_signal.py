import zmq
import msgspec
from zmq.asyncio import Context
from decimal import Decimal
from nexustrader.core.log import SpdLog
from nexustrader.constants import settings
from nexustrader.config import (
    Config,
    PublicConnectorConfig,
    PrivateConnectorConfig,
    BasicConfig,
    ZeroMQSignalConfig,
)
from nexustrader.strategy import Strategy
from nexustrader.constants import ExchangeType, OrderSide
from nexustrader.exchange.binance import BinanceAccountType
from nexustrader.engine import Engine
from nexustrader.core.entity import RateLimit
from collections import defaultdict

SpdLog.initialize(level="DEBUG", production_mode=True, file_name="custum_signal.log")

BINANCE_API_KEY = settings.BINANCE.FUTURE.TESTNET_1.API_KEY
BINANCE_SECRET = settings.BINANCE.FUTURE.TESTNET_1.SECRET

context = Context()
socket = context.socket(zmq.SUB)
socket.connect("ipc:///tmp/zmq_data_test")
socket.setsockopt(zmq.SUBSCRIBE, b"")


class Demo(Strategy):
    def __init__(self):
        super().__init__()
        self.symbols = ["BTCUSDT-PERP.BINANCE"]
        self.signal = True
        self.multiplier = 1
        self.prev_target = defaultdict(Decimal)
        self.orders = {}

    def on_start(self):
        self.subscribe_bookl1(symbols=self.symbols, ready=False)

    def cal_diff(self, symbol, target_position) -> Decimal:
        """
        target_position: 10, current_position: 0, diff: 10 reduce_only: false
        target_position: 10, current_position: 10, diff: 0
        target_position: 10, current_position: -10, diff: 20
        target_position: 10, current_position: 20, diff: -10 reduce_only: true
        target_position: -10, current_position: -20, diff: 10
        """
        position = self.cache.get_position(symbol).value_or(None)
        current_amount = position.signed_amount if position else Decimal("0")
        diff = target_position - current_amount

        reduce_only = False

        if diff != 0:
            if (
                abs(current_amount) > abs(target_position)
                and current_amount * target_position >= 0
            ):
                reduce_only = True
            self.log.info(
                f"symbol: {symbol}, current {current_amount} -> target {target_position}, reduce_only: {reduce_only}"
            )
        return diff, reduce_only

    def on_custom_signal(self, signal):
        signal = msgspec.json.decode(signal)
        for pos in signal:
            if not self.ready:
                self.log.info("Data not ready, skip")
                continue

            symbol = pos["instrumentID"].replace("USDT.BBP", "USDT-PERP.BINANCE")

            if symbol not in self.symbols:
                self.log.info(f"symbol: {symbol} not in self.symbols, skip")
                continue

            target_position = (
                pos["position"] * self.market(symbol).precision.amount * self.multiplier
            )
            target_position = self.amount_to_precision(symbol, target_position)

            uuid = self.orders.get(symbol, None)

            if uuid:
                order = self.cache.get_order(uuid)
                is_opened = order.bind_optional(lambda order: order.is_opened).value_or(
                    False
                )
                is_failed = order.bind_optional(lambda order: order.is_failed).value_or(
                    False
                )
                if is_opened:
                    if self.prev_target[symbol] != target_position:
                        self.cancel_twap(
                            symbol=symbol,
                            uuid=uuid,
                            account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
                        )
                        self.log.info(
                            f"symbol: {symbol}, canceled {uuid}, prev_target: {self.prev_target[symbol]} -> new_target: {target_position}"
                        )
                        uuid = None
                    else:
                        self.log.info(
                            f"symbol: {symbol}, target not changed, skip, prev_target: {self.prev_target[symbol]}, new_target: {target_position}"
                        )
                else:
                    if is_failed:
                        self.log.info(f"symbol: {symbol}, order {uuid} failed")
                    uuid = None

            if uuid is None:
                diff, reduce_only = self.cal_diff(symbol, target_position)
                if diff != 0:
                    uuid = self.create_twap(
                        symbol=symbol,
                        side=OrderSide.BUY if diff > 0 else OrderSide.SELL,
                        amount=abs(diff),
                        duration=65,
                        wait=5,
                        account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
                        reduce_only=reduce_only,
                    )
                    self.orders[symbol] = uuid

            self.prev_target[symbol] = target_position


config = Config(
    strategy_id="binance_twap",
    user_id="user_test",
    strategy=Demo(),
    basic_config={
        ExchangeType.BINANCE: BasicConfig(
            api_key=BINANCE_API_KEY,
            secret=BINANCE_SECRET,
            testnet=True,
        )
    },
    public_conn_config={
        ExchangeType.BINANCE: [
            PublicConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
            ),
        ]
    },
    private_conn_config={
        ExchangeType.BINANCE: [
            PrivateConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
                rate_limit=RateLimit(
                    max_rate=20,  # 20 orders per second
                    time_period=1,
                ),
            )
        ]
    },
    zero_mq_signal_config=ZeroMQSignalConfig(
        socket=socket,
    ),
)

engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
