from app.services.platforms.instagram_composite import InstagramCompositeAdapter
from app.services.platforms.instagram_production import InstagramProductionAdapter
from app.services.platforms.registry import get_platform_adapter


class Driver:
    def __init__(self) -> None:
        self.current_url = "about:blank"
        self.visited: list[str] = []

    def get(self, url: str) -> None:
        self.visited.append(url)
        self.current_url = url

    def get_cookie(self, name: str):
        if name == "ds_user_id":
            return {"value": "880081"}
        if name == "sessionid":
            return {"value": "session"}
        return None


driver = Driver()
adapter = get_platform_adapter("instagram")
assert isinstance(adapter, InstagramProductionAdapter)
assert isinstance(adapter, InstagramCompositeAdapter)
login = adapter.check_login(driver)
assert driver.visited == ["https://www.instagram.com/"]
assert login["logged_in"] is True
assert login["actor_id"] == "880081"

# Once already on the Instagram origin, identity inspection must not reload it.
driver.visited.clear()
login = adapter.check_login(driver)
assert driver.visited == []
assert login["logged_in"] is True

print("phase8 instagram origin identity ok")
