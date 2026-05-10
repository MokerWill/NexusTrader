from nexustrader.exchange.binance.constants import BinanceAccountType
from nexustrader.exchange.binance.websockets import BinanceKlineDirectWSClient


class DummyTaskManager:
    pass


def _client(account_type: BinanceAccountType, custom_url: str | None = None):
    return BinanceKlineDirectWSClient(
        account_type=account_type,
        handler=lambda *_args, **_kwargs: None,
        task_manager=DummyTaskManager(),
        custom_url=custom_url,
    )


def test_binance_usdm_kline_uses_routed_market_stream_url_by_default():
    client = _client(BinanceAccountType.USD_M_FUTURE)

    assert client._base_url == "wss://fstream.binance.com/market/stream?streams="


def test_binance_usdm_kline_routes_custom_legacy_root_url():
    client = _client(
        BinanceAccountType.USD_M_FUTURE,
        custom_url="wss://fstream.binance.com",
    )

    assert client._base_url == "wss://fstream.binance.com/market/stream?streams="


def test_binance_usdm_kline_routes_custom_legacy_stream_url():
    client = _client(
        BinanceAccountType.USD_M_FUTURE,
        custom_url="wss://fstream.binance.com/stream?streams=",
    )

    assert client._base_url == "wss://fstream.binance.com/market/stream?streams="


def test_binance_usdm_kline_keeps_custom_market_stream_url():
    client = _client(
        BinanceAccountType.USD_M_FUTURE,
        custom_url="wss://fstream.binance.com/market/stream?streams=",
    )

    assert client._base_url == "wss://fstream.binance.com/market/stream?streams="


def test_binance_spot_kline_keeps_spot_combined_stream_url():
    client = _client(BinanceAccountType.SPOT)

    assert client._base_url == "wss://stream.binance.com:9443/stream?streams="
