from app.main import app
from app.models.asset_pool import Asset
from app.schemas.asset_pool import TextAssetCreate
from app.services.resource_pool import parse_proxy_import_text
from app.api.asset_pool import _parse_text_asset_csv


paths = app.openapi()["paths"]
required = {
    ("/api/proxy-pool", "post"),
    ("/api/proxy-pool/import", "post"),
    ("/api/account-pool", "post"),
    ("/api/account-pool/import", "post"),
    ("/api/asset-pool", "get"),
    ("/api/asset-pool/text", "post"),
    ("/api/asset-pool/media", "post"),
    ("/api/asset-pool/text/import", "post"),
    ("/api/asset-pool/media/import", "post"),
    ("/api/asset-pool/batch/delete", "post"),
}
for path, method in required:
    assert path in paths, path
    assert method in paths[path], (path, method)

proxy = parse_proxy_import_text("128.241.28.247:37263:LR1LbJaq:AqkY3X3y6U")[0]
assert proxy.host == "128.241.28.247"
assert proxy.port == 37263
assert proxy.username == "LR1LbJaq"
assert proxy.password == "AqkY3X3y6U"

text = TextAssetCreate(name="产品 A 文案", platform="facebook", text="Summer sale")
assert text.platform == "facebook"
assert text.text == "Summer sale"

rows = _parse_text_asset_csv(
    '名称,平台,文案\n产品A-01,facebook,"Summer sale"\n产品A-02,generic,"Second copy"\n'
)
assert rows == [
    ("产品A-01", "facebook", "Summer sale"),
    ("产品A-02", "generic", "Second copy"),
]

assert Asset.__tablename__ == "assets"
assert not hasattr(Asset, "jobs")

print("phase10 unified resource entry ok")
