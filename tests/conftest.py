import subprocess
import pytest
import re


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """
    Automatically runs Ruff cyclomatic complexity check and prints a clean summary table.
    """
    terminalreporter.section("Cyclomatic Complexity Summary")

    try:
        # Run ruff with max-complexity=0 to catch all functions
        res = subprocess.run(
            [
                "ruff",
                "check",
                "--select",
                "C901",
                "--config",
                "lint.mccabe.max-complexity=0",
                "src/",
            ],
            capture_output=True,
            text=True,
        )

        # Regex to find: `func_name` is too complex (N > 0)
        pattern = re.compile(r"`(.+)` is too complex \((\d+) > 0\)")
        matches = pattern.findall(res.stdout)

        if not matches:
            terminalreporter.write("No functions found to analyze.\n")
            return

        # Convert to list of (name, complexity) and sort by complexity descending
        report_data = []
        for name, score in matches:
            report_data.append((name, int(score)))

        report_data.sort(key=lambda x: x[1], reverse=True)

        # Print Table Header
        header = f"{'Function Name':<40} {'Complexity':<10}"
        terminalreporter.write(header + "\n")
        terminalreporter.write("-" * len(header) + "\n")

        # Print Rows
        for name, score in report_data:
            # Highlight if > 5
            status = "!" if score > 5 else " "
            row = f"{name:<40} {score:<10} {status}"
            terminalreporter.write(row + "\n")

        terminalreporter.write(f"\n(!) High complexity detected (Target: 5)\n")

    except FileNotFoundError:
        terminalreporter.write(
            "⚠️  Ruff not found in PATH. Cannot generate complexity report.\n"
        )
    except Exception as e:
        terminalreporter.write(f"⚠️  Error running complexity report: {e}\n")
