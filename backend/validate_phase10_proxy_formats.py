from app.services.resource_pool import parse_proxy_import_text


def main() -> None:
    rows = parse_proxy_import_text(
        "128.241.28.247:37263:LR1LbJaq:AqkY3X3y6U\n"
        "1.2.3.4:1080\n"
        "socks5://demo:secret@5.6.7.8:1080\n"
    )
    assert len(rows) == 3
    first = rows[0]
    assert first.host == "128.241.28.247"
    assert first.port == 37263
    assert first.username == "LR1LbJaq"
    assert first.password == "AqkY3X3y6U"
    print("phase10 SOCKS5 import formats ok")


if __name__ == "__main__":
    main()
