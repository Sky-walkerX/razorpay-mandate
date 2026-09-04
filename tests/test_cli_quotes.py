from pathlib import Path
from typer.testing import CliRunner

from mandate.cli import app

runner = CliRunner()


def test_quote_cli_e2e(tmp_path: Path):
    keys_dir = tmp_path / "keys"
    keyring_file = keys_dir / "merchants.json"

    # 1. Generate keypair for merchant 'blinkit'
    res = runner.invoke(
        app,
        ["quote-keygen", "--merchant", "blinkit", "--out-dir", str(keys_dir), "--keyring", str(keyring_file)],
    )
    assert res.exit_code == 0, res.output
    assert "Generated Ed25519 quote keypair" in res.output
    assert (keys_dir / "merchant_blinkit_private.key").exists()
    assert (keys_dir / "merchant_blinkit_public.key").exists()
    assert keyring_file.exists()

    priv_key = (keys_dir / "merchant_blinkit_private.key").read_text().strip()

    # 2. Sign a quote
    sign_res = runner.invoke(
        app,
        [
            "quote-sign",
            "--merchant", "blinkit",
            "--sku", "sku_milk_01",
            "--price", "4800",
            "--key", priv_key,
            "--ttl", "600",
        ],
    )
    assert sign_res.exit_code == 0, sign_res.output
    raw_quote = sign_res.output.strip()
    assert "." in raw_quote

    # 3. Verify the valid quote
    ver_res = runner.invoke(
        app,
        [
            "quote-verify",
            "--quote", raw_quote,
            "--merchant", "blinkit",
            "--sku", "sku_milk_01",
            "--keyring", str(keyring_file),
        ],
    )
    assert ver_res.exit_code == 0, ver_res.output
    assert "Quote VALID" in ver_res.output
    assert "4800 paise" in ver_res.output

    # 4. Verify mismatch merchant fails
    fail_res = runner.invoke(
        app,
        [
            "quote-verify",
            "--quote", raw_quote,
            "--merchant", "zepto",
            "--sku", "sku_milk_01",
            "--keyring", str(keyring_file),
        ],
    )
    assert fail_res.exit_code != 0
    assert "quote.merchant_mismatch" in fail_res.output

