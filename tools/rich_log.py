import time
from loguru import logger
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.text import Text


class RichLog:
    def __init__(self, header, header_style='bold white on blue') -> None:
        self.header_style = header_style
        self.request_style = 'bold bright_green'
        self.log_style = 'italic white'
        self._log = []
        self._request = ''
        self._console = Console()
        self._layout = Layout()
        self._layout.split_column(
            Layout(name='header', size=3),
            Layout(name='request', size=3),
            Layout(name='progress', size=1),
            Layout(name='log', ratio=1),
        )
        self._progress = Progress(
            TextColumn('[bold blue]До запроса: {task.fields[remaining]}с'),
            BarColumn(bar_width=None, complete_style='bright_green'),
            TextColumn('[progress.percentage]{task.percentage:>3.0f}%'),
            console=self._console,
            expand=True,
        )

        self._live = Live(self._layout, console=self._console, screen=True)
        self._layout['header'].update(
            Panel(Align(header, style=self.header_style, align='center'), height=3, expand=True)
        )
        self._layout['progress'].update(Padding(self._progress, (0, 2)))
        self._live.start()

    @property
    def visible_log(self) -> Text:
        #    ширина терминала − 2(border) − 2(padding по горизонтали)
        console_width = self._console.size.width - 4
        # — подсчитываем, сколько строк помещается в области логов
        log_height = self._layout['log'].size or (self._console.size.height - 6)
        max_lines = max(0, log_height - 2)  # вычитаем 2 строки для рамки
        wrapped_lines = []
        for msg in self._log:
            text_obj = Text.from_ansi(msg)
            # text_obj = Text(msg, style=self.log_style)
            lines = text_obj.wrap(self._console, console_width)
            wrapped_lines.extend(lines)
        visible_lines = wrapped_lines[-max_lines:]

        log_visible = Text()
        for line in visible_lines:
            log_visible.append(line)
            log_visible.append('\n')
        return log_visible

    def _update_screen(self) -> None:
        self._layout['request'].update(
            Panel(Text(self._request, style=self.request_style), title='Status', height=3, expand=True)
        )
        self._layout['log'].update(Panel(self.visible_log, title='Log', expand=True, padding=(0, 1)))
        self._live.update(self._layout)

    def print_request(self, text: str) -> None:
        self._request = text
        self._update_screen()

    def print_log(self, text: str) -> None:
        self._log.append(text.strip())
        self._log = self._log[-100:]
        self._update_screen()

    def sleep(self, duration: float) -> None:
        task = self._progress.add_task('sleeping', total=duration, remaining=int(duration))

        quantifier = 0.5
        elapsed = 0
        while elapsed < duration:
            remaining = max(0, duration - elapsed)
            self._progress.update(task, completed=elapsed, remaining=int(remaining))
            elapsed += quantifier
            time.sleep(quantifier)

        self._progress.update(task, completed=duration, remaining=0)
        self._progress.remove_task(task)

    def stop(self) -> None:
        self._live.stop()


if __name__ == '__main__':
    logger.remove()
    rich_log = RichLog(__file__)
    logger.add(lambda msg: rich_log.print_log(msg.strip()), level='DEBUG', colorize=True)
    try:
        for i in range(200):
            rich_log.print_request(f'Request {i}')
            logger.debug(f'Line {i}')
            rich_log.sleep(2)
    finally:
        rich_log.stop()
