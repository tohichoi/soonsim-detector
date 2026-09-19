"""Rich console status dashboard."""

import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


class Dashboard:
    """Renders real-time telemetry dashboard using Rich."""

    def __init__(self):
        self.console = Console()
        self.start_time = time.time()

    def generate_table(self, stats: dict) -> Panel:
        """Generate formatted status table panel."""
        uptime = time.strftime("%H:%M:%S", time.gmtime(time.time() - self.start_time))
        table = Table(show_header=True, header_style="bold magenta", expand=True)

        table.add_column("Metric", style="cyan", width=24)
        table.add_column("Status / Value", style="white")

        table.add_row("System Uptime", uptime)
        table.add_row("Stream Status", "[green]CONNECTED[/green]" if stats.get("connected") else "[red]CONNECTING[/red]")
        table.add_row("Processing FPS", f"{stats.get('fps', 0.0):.1f}")
        table.add_row("Inference Skip", f"{stats.get('skip_ratio', 0.0):.1f}%")
        table.add_row("Inference Latency", f"{stats.get('avg_latency_ms', 0.0):.1f} ms")
        table.add_row("Frame Index", str(stats.get("frame_idx", 0)))
        table.add_row("Zone Event Status", f"[{stats.get('status_color', 'white')}]{stats.get('status', 'IDLE')}[/]")
        table.add_row("Dog on Pad", "[bold green]YES[/bold green]" if stats.get("dog_in_zone") else "[dim]NO[/dim]")
        table.add_row("Ring Buffer Size", f"{stats.get('buffer_size', 0)} frames")
        table.add_row("Total Alerts Sent", str(stats.get("alerts_count", 0)))
        table.add_row("Last Alert Time", stats.get("last_alert_time", "None"))

        return Panel(table, title="[bold blue]Soonsim Detector - Live Telemetry[/bold blue]", border_style="blue")
