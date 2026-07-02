# Static Analysis Audit Report: Brokers Directory

This report presents a structural, SOLID, and DRY/KISS/YAGNI audit of the `brokers/` directory inside `INC_Trade`, compiled by the `deep-static-auditor` agent. The findings are based on static analysis checks (including Mypy type-checking and Ruff linting) and manual code craft inspection.

---
🔴 Critical: Dynamic Annotations NameError (Undefined Return Type)
File: brokers/paper/paper_gateway.py (lines 429-435)
Class / Method: PaperGateway.capabilities
Diagnosis: BrokerCapabilities is used as a return type annotation on the capabilities method signature but is imported only inside the method body, causing potential NameErrors or runtime type resolution failures.
Principle Violated: KISS
Prescription: Move the imports of type annotations to the top of the module or import them under a TYPE_CHECKING block.
Before (sketch):
```python
    def capabilities(self) -> BrokerCapabilities:
        from brokers.common.capabilities import BrokerCapabilities
        return BrokerCapabilities(...)
```
After (sketch):
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from brokers.common.capabilities import BrokerCapabilities

# Or import BrokerCapabilities directly at the module top level.
```
---

---
🔴 Critical: Severe Type Contract Mismatch
File: brokers/upstox/auth/token_manager.py (lines 280-304)
Class / Method: UpstoxTokenManager.perform_interactive_oauth
Diagnosis: The method signature specifies a return type of TokenSnapshot but actually returns a PkcePair, which violates type safety and will cause crashes in callers expecting a token snapshot.
Principle Violated: KISS / DRY
Prescription: Correct the return type annotation of the method to return PkcePair.
Before (sketch):
```python
    def perform_interactive_oauth(self, ...) -> TokenSnapshot:
        pkce = UpstoxPkceUtil.generate()
        return pkce  # returns PkcePair
```
After (sketch):
```python
    def perform_interactive_oauth(self, ...) -> PkcePair:
        pkce = UpstoxPkceUtil.generate()
        return pkce
```
---

---
🔴 Critical: Primitive Type Signature Error (Built-in any used as Type Hint)
File: brokers/upstox/auth/token_manager.py (lines 53, 96, 284)
Class / Method: UpstoxTokenManager.__init__ / UpstoxTokenManager.settings
Diagnosis: The type annotation uses the python built-in function type `any` instead of the capitalized type hint `Any` from `typing`, which breaks static analysis tools and causes type-checkers to treat the attribute as a function type.
Principle Violated: KISS
Prescription: Replace lowercase `any` type annotations with `Any` or `typing.Any` or specify the concrete type.
Before (sketch):
```python
    def __init__(self, settings: any) -> None:
        self._settings = settings

    @property
    def settings(self) -> any:
        return self._settings
```
After (sketch):
```python
    from typing import Any

    def __init__(self, settings: Any) -> None:
        self._settings = settings

    @property
    def settings(self) -> Any:
        return self._settings
```
---

---
🟠 High: Liskov Substitution Principle (LSP) Violation in Method Override
File: brokers/dhan/gateway.py (lines 468-476) and brokers/upstox/gateway.py (lines 255-263)
Class / Method: BrokerGateway.history / UpstoxBrokerGateway.history
Diagnosis: Subclasses override the history method of the MarketDataGateway interface but restrict the symbol argument type to str, violating LSP since the parent class allows both str and list[str].
Principle Violated: LSP
Prescription: Update the subclass signatures to accept str | list[str] to match the interface contract, and handle list inputs appropriately.
Before (sketch):
```python
    # Parent (MarketDataGateway):
    def history(self, symbol: str | list[str], ...) -> pd.DataFrame: ...

    # Child (BrokerGateway):
    def history(self, symbol: str, ...) -> pd.DataFrame: ...
```
After (sketch):
```python
    # Child (BrokerGateway):
    def history(self, symbol: str | list[str], ...) -> pd.DataFrame:
        if isinstance(symbol, list):
            # Batch fetch logic or delegate to history_batch
            ...
        # Single string fetch logic
```
---

---
🟠 High: Liskov Substitution Principle (LSP) Violation in Return Type
File: brokers/dhan/gateway.py (lines 659-700)
Class / Method: BrokerGateway.get_connection_status
Diagnosis: Overridden method returns a dictionary containing strings, floats, and None values (dict[str, bool | str | float | None]), violating the parent contract of ObservabilityProvider.get_connection_status which specifies a return type of dict[str, bool].
Principle Violated: LSP
Prescription: Conform to the parent method's return type signature by returning only booleans, or split additional metadata into a separate method.
Before (sketch):
```python
    # Parent (ObservabilityProvider):
    def get_connection_status(self) -> dict[str, bool]: ...

    # Child (BrokerGateway):
    def get_connection_status(self) -> dict[str, bool | str | float | None]:
        status = {"market_feed": True, "next_connect_allowed_at": 171991823}
        return status
```
After (sketch):
```python
    # Keep return type strictly dict[str, bool]
    def get_connection_status(self) -> dict[str, bool]:
        return {
            "market_feed": self._conn.market_feed.is_connected,
            "order_stream": self._conn.order_stream.is_connected,
        }
```
---

---
🟠 High: Inappropriate Intimacy / Dynamic Monkey-Patching in Factory
File: brokers/dhan/factory.py (lines 315-318, 166-168)
Class / Method: DhanConnectionFactory.create
Diagnosis: The factory class directly modifies private state on DhanConnection and AuthManager instances after instantiation (monkey-patching connection._auth = auth), which violates encapsulation and hides dependencies.
Principle Violated: DIP / SRP
Prescription: Inject the dependencies (auth and session_manager) directly through the DhanConnection constructor or public initialization methods.
Before (sketch):
```python
        connection = DhanConnection(client=client)
        connection._auth = auth
        connection._session_manager = DhanSessionManager(connection, auth)
```
After (sketch):
```python
        connection = DhanConnection(
            client=client,
            auth=auth,
            session_manager=DhanSessionManager(connection, auth)
        )
```
---

---
🟠 High: Shotgun Initialization / Builder Leaking Implementation Details
File: brokers/upstox/broker.py (lines 194-215)
Class / Method: UpstoxBrokerBuilder._init_basic_state
Diagnosis: The builder directly sets and modifies private properties (_capabilities, _capability_map, _status, _token_manager, _oms, etc.) on the UpstoxBroker instance from the outside, which leads to dynamic attribute warnings in type-checkers and bypasses encapsulation.
Principle Violated: SRP / DIP
Prescription: Move initialization of fields to UpstoxBroker.__init__ or have the builder pass a cleanly constructed configuration object to the broker.
Before (sketch):
```python
class UpstoxBroker:
    def __init__(self, settings: UpstoxConnectionSettings):
        builder = UpstoxBrokerBuilder(broker=self, settings=settings)
        builder.build()

class UpstoxBrokerBuilder:
    def _init_basic_state(self):
        self._broker._capabilities = set()
        self._broker._status = ConnectionStatus.DISCONNECTED
```
After (sketch):
```python
class UpstoxBroker:
    def __init__(self, settings: UpstoxConnectionSettings, capabilities: set[Capability], ...):
        self._settings = settings
        self._capabilities = capabilities
        self._status = ConnectionStatus.DISCONNECTED
```
---

---
🟡 Medium: Dead Code / Speculative Generality
File: brokers/dhan/async_http_client.py (all lines)
Class / Method: DhanAsyncHttpClient
Diagnosis: The entire DhanAsyncHttpClient class is written for async HTTP access to the Dhan API, but is never imported or used by any broker gateways or services in the repository, representing unused speculative code.
Principle Violated: YAGNI
Prescription: Remove the async_http_client.py file or refactor BrokerGateway to use it instead of wrapping synchronous HTTP calls with asyncio.to_thread.
Before (sketch):
```python
# brokers/dhan/async_http_client.py
class DhanAsyncHttpClient:
    # Completely implemented async client, but never imported or used.
```
After (sketch):
```python
# Delete the file brokers/dhan/async_http_client.py if it's not planned for use,
# or refactor the gateway to use it natively.
```
---

---
🟡 Medium: Primitive Obsession / Type Inference Smell
File: brokers/dhan/options.py (lines 233-241)
Class / Method: OptionsAdapter.get_expired_options_data
Diagnosis: Dict literal keys are dynamically accessed via string lookups on variables inferred to have strict primitive types (result["ce"]["timestamp"]), causing type checker warnings when type inference determines the values to be string types rather than nested dictionaries.
Principle Violated: KISS
Prescription: Use a strongly typed TypedDict or a domain DTO (data transfer object) using dataclasses or Pydantic to represent the CE/PE result structure instead of a raw dictionary.
Before (sketch):
```python
        result = {"status": "success", "ce": None, "pe": None}
        ...
        ce_count = len(result["ce"]["timestamp"]) if result["ce"] else 0
```
After (sketch):
```python
        class OptionsResult(TypedDict):
            status: str
            ce: dict[str, Any] | None
            pe: dict[str, Any] | None

        result: OptionsResult = {"status": "success", "ce": None, "pe": None}
```
---
