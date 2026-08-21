import os
import typer
from dotenv import load_dotenv
from mandate.money import rupees, fmt
from mandate.downstream.razorpay import RazorpayDownstream

app = typer.Typer(no_args_is_help=True)


@app.command()
def check() -> None:
    """Prove end-to-end wiring: create one test-mode order and read it back."""
    load_dotenv()
    d = RazorpayDownstream(os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"])
    amount = rupees(1)
    order = d.create_order(amount, receipt="mandate_check_001", notes={"src": "mandate check"})
    typer.echo(f"created {order['id']} for {fmt(amount)}")
    back = d.fetch_order(order["id"])
    assert back["id"] == order["id"], "order did not read back"
    typer.echo(f"read back {back['id']} status={back['status']}")
    typer.echo("wiring OK")
