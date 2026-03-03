import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from .config import REGION_DATA

console = Console()


def display_region_menu():
    """Prints the region selection menu using Rich panels."""
    table = Table(box=box.SIMPLE_HEAD, show_header=False)
    for key, val in REGION_DATA.items():
        table.add_row(f"[bold cyan]{key}[/]", val["name"])
    table.add_row("[bold cyan]4[/]", "CUSTOM SEARCH (Radius Calculation)")

    console.print(
        Panel(
            table,
            title="[bold white]SELECT REGION[/]",
            expand=False,
            border_style="blue",
        )
    )


def get_user_choice():
    """Prompts user for region choice."""
    return input("Enter number: ").strip()


def get_user_zip():
    """Prompts user for center zip code."""
    return input("Enter Center Zip Code: ").strip()


def wait_for_user_to_confirm_prices(zip_code):
    """Instructions for manual intervention during scraping."""
    console.print(
        Panel(
            f"1. If Cloudflare checks you, click the box.\n"
            f"2. Wait for the list of stations to appear.\n"
            f"3. Press [bold green]ENTER[/] here once the prices are visible...",
            title=f"👉 ACTION REQUIRED for [bold yellow]{zip_code}[/]",
            border_style="yellow",
            expand=False,
        )
    )
    input()


def display_results(df):
    """
    Prints the collected gas price data in both grouped and sorted views using Rich tables.
    """
    # 1. Grouped View
    console.print(Panel("📍 VIEW 1: GROUPED BY CITY", style="bold blue", expand=False))

    grouped = df.sort_values(by=["City", "Net"])
    for city, group in grouped.groupby("City"):
        table = Table(title=f"City: [bold yellow]{city}[/]", box=box.ROUNDED)
        table.add_column("Station", style="cyan")
        table.add_column("Net", justify="right", style="bold green")
        table.add_column("Base", justify="right")
        table.add_column("Discount", style="magenta")
        table.add_column("Address", style="dim")

        for _, row in group.iterrows():
            table.add_row(
                row["Station"],
                f"${row['Net']:.2f}",
                f"${row['Base']:.2f}",
                row["Discount"],
                row["Address"],
            )
        console.print(table)
        console.print()

    # 2. Overall Cheapest View
    console.print(
        Panel("🏆 VIEW 2: CHEAPEST OVERALL (SORTED)", style="bold gold1", expand=False)
    )

    df_sorted = df.sort_values(by="Net", ascending=True)
    table = Table(box=box.DOUBLE_EDGE)
    table.add_column("Rank", justify="center")
    table.add_column("Station", style="cyan")
    table.add_column("Net", justify="right", style="bold green")
    table.add_column("Base", justify="right")
    table.add_column("Discount", style="magenta")
    table.add_column("City", style="yellow")
    table.add_column("Address", style="dim")

    for idx, (_, row) in enumerate(df_sorted.iterrows(), 1):
        table.add_row(
            str(idx),
            row["Station"],
            f"${row['Net']:.2f}",
            f"${row['Base']:.2f}",
            row["Discount"],
            row["City"],
            row["Address"],
        )
    console.print(table)
    console.print()
