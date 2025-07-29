import time
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from loguru import logger


class RichLog:
    def __init__(self, header) -> None:
        self.header_style = '[bold white on blue]'
        self.request_style = '[bold green]'
        self.log_style = '[italic white]'
        self._log = []
        self._request = ''
        self._log_height = 0
        self._console = Console()
        self._layout = Layout()
        self._layout.split_column(
            Layout(name='header', size=3), Layout(name='request', size=3), Layout(name='log', ratio=1)
        )
        self._live = Live(self._layout, console=self._console, screen=True)
        self._layout['header'].update(Panel(self._format_text(header, self.header_style), height=3, expand=True))
        self._live.start()

    def stop(self) -> None:
        self._live.stop()

    def _format_text(self, text, style) -> str:
        return f'{style}{text}[/]'

    def print_request(self, text: str) -> None:
        self._request = text
        self._update_screen()

    def print_log(self, text: str) -> None:
        self._log.append(text)
        self._log = self._log[-100:]
        self._update_screen()

    @property
    def visible_lines(self):
        # — подсчитываем, сколько строк помещается в области логов
        self._log_height = self._layout['log'].size or (self._console.size.height - 6)
        max_lines = max(0, self._log_height - 2)  # вычитаем 2 строки для рамки
        visible_lines = self._log[-max_lines:]
        return visible_lines

    def _update_screen(self):
        # — обновляем статус
        self._layout['request'].update(
            Panel(self._format_text(self._request, self.request_style), title='Status', height=3, expand=True)
        )

        # — парсим разметку из Loguru, не накладываем своего стиля
        log_render = Text.from_ansi('\n'.join(self.visible_lines))
        # — обновляем панель с логом
        self._layout['log'].update(
            Panel(
                # self._format_text('\n'.join(self.visible_lines), self.log_style),
                log_render,
                title='Log',
                height=self._log_height,
                expand=True,
                padding=(0, 1),
            )
        )

        self._live.update(self._layout)


if __name__ == '__main__':
    logger.remove()
    rich_log = RichLog(__file__)
    logger.add(
            lambda msg: rich_log.print_log(msg.strip()), level='DEBUG', colorize=True
        )
    try:
        for i in range(200):
            rich_log.print_request(f'Request {i}')
            # rich_log.print_log(f'Line {i}')
            logger.debug(f'Line {i}')
            time.sleep(0.3)
    finally:
        rich_log.stop()
